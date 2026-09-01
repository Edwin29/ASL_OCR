"""SQLite source of truth for the single-sender delivery outbox."""

from __future__ import annotations

import contextlib
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .delivery_domain import PreparedDelivery, inventory_json, prepared_from_row
from .protocols import FatalPortError, RecoverablePortError


MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS delivery_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_outbox (
    outbox_id TEXT PRIMARY KEY,
    scan_session_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence > 0),
    device_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    spread_id TEXT NOT NULL,
    source_frame_id TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    inventory_json TEXT NOT NULL,
    file_count INTEGER NOT NULL CHECK(file_count > 0),
    total_file_bytes INTEGER NOT NULL CHECK(total_file_bytes >= 0),
    upload_digest TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','sending','retrying','acked','rejected')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
    receipt_id TEXT NULL,
    server_accepted_at TEXT NULL,
    last_http_status INTEGER NULL,
    last_error_code TEXT NULL,
    last_error_detail TEXT NULL,
    cleanup_error TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    terminal_at TEXT NULL,
    UNIQUE(scan_session_id, sequence),
    UNIQUE(scan_session_id, idempotency_key),
    UNIQUE(artifact_id)
);

CREATE INDEX IF NOT EXISTS delivery_pending_idx
    ON delivery_outbox(scan_session_id, status, sequence);
"""


class DeliveryStore:
    def __init__(self, path: Path, *, timestamp: Callable[[], str] | None = None) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._timestamp = timestamp or _utc_now
        self._migrate()
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE delivery_outbox
                   SET status='retrying', updated_at=?, last_error_code='PROCESS_RESTART',
                       last_error_detail='sending attempt interrupted by process restart'
                 WHERE status='sending'
                """,
                (self._timestamp(),),
            )

    def connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            return connection
        except sqlite3.Error as exc:
            raise RecoverablePortError(f"cannot open delivery outbox: {exc}") from exc

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise FatalPortError(f"delivery outbox identity collision: {exc}") from exc
        except sqlite3.Error as exc:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise RecoverablePortError(f"delivery outbox database failure: {exc}") from exc
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @contextmanager
    def readonly(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        except sqlite3.Error as exc:
            raise RecoverablePortError(f"delivery outbox database failure: {exc}") from exc
        finally:
            connection.close()

    def find_position(self, scan_session_id: str, sequence: int) -> sqlite3.Row | None:
        with self.readonly() as connection:
            return connection.execute(
                "SELECT * FROM delivery_outbox WHERE scan_session_id=? AND sequence=?",
                (scan_session_id, sequence),
            ).fetchone()

    def enqueue(self, prepared: PreparedDelivery) -> sqlite3.Row:
        existing = self.find_position(prepared.scan_session_id, prepared.sequence)
        if existing is not None:
            self._require_same(existing, prepared)
            return existing
        now = self._timestamp()
        outbox_id = f"outbox-{uuid.uuid4().hex}"
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO delivery_outbox(
                    outbox_id, scan_session_id, sequence, device_id, artifact_id,
                    spread_id, source_frame_id, manifest_path, manifest_sha256,
                    inventory_json, file_count, total_file_bytes, upload_digest,
                    idempotency_key, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (
                    outbox_id,
                    prepared.scan_session_id,
                    prepared.sequence,
                    prepared.device_id,
                    prepared.artifact_id,
                    prepared.spread_id,
                    prepared.source_frame_id,
                    prepared.manifest_path,
                    prepared.manifest_sha256,
                    inventory_json(prepared.files),
                    len(prepared.files),
                    prepared.total_file_bytes,
                    prepared.upload_digest,
                    prepared.idempotency_key,
                    now,
                    now,
                ),
            )
        row = self.find_position(prepared.scan_session_id, prepared.sequence)
        assert row is not None
        return row

    def list_scan(self, scan_session_id: str) -> tuple[sqlite3.Row, ...]:
        with self.readonly() as connection:
            return tuple(
                connection.execute(
                    "SELECT * FROM delivery_outbox WHERE scan_session_id=? ORDER BY sequence",
                    (scan_session_id,),
                ).fetchall()
            )

    def next_nonterminal(self, scan_session_id: str) -> sqlite3.Row | None:
        with self.readonly() as connection:
            return connection.execute(
                """
                SELECT * FROM delivery_outbox
                 WHERE scan_session_id=? AND status IN ('queued','retrying')
                 ORDER BY sequence LIMIT 1
                """,
                (scan_session_id,),
            ).fetchone()

    def claim(self, outbox_id: str) -> sqlite3.Row | None:
        now = self._timestamp()
        with self.transaction() as connection:
            changed = connection.execute(
                """
                UPDATE delivery_outbox
                   SET status='sending', attempt_count=attempt_count+1,
                       updated_at=?, last_error_code=NULL, last_error_detail=NULL
                 WHERE outbox_id=? AND status IN ('queued','retrying')
                """,
                (now, outbox_id),
            ).rowcount
            if changed != 1:
                return None
            return connection.execute(
                "SELECT * FROM delivery_outbox WHERE outbox_id=?", (outbox_id,)
            ).fetchone()

    def retry(
        self,
        outbox_id: str,
        *,
        code: str,
        detail: str,
        http_status: int | None = None,
    ) -> None:
        self._transition(
            outbox_id,
            "retrying",
            http_status=http_status,
            error_code=code,
            error_detail=detail,
        )

    def reject(self, outbox_id: str, *, code: str, detail: str, http_status: int) -> None:
        self._transition(
            outbox_id,
            "rejected",
            http_status=http_status,
            error_code=code,
            error_detail=detail,
            terminal=True,
        )

    def acknowledge(
        self,
        outbox_id: str,
        *,
        receipt_id: str,
        accepted_at: str,
        http_status: int,
    ) -> None:
        now = self._timestamp()
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE delivery_outbox
                   SET status='acked', receipt_id=?, server_accepted_at=?,
                       last_http_status=?, last_error_code=NULL, last_error_detail=NULL,
                       updated_at=?, terminal_at=?
                 WHERE outbox_id=? AND status='sending'
                """,
                (receipt_id, accepted_at, http_status, now, now, outbox_id),
            )

    def set_cleanup_error(self, outbox_id: str, detail: str | None) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE delivery_outbox SET cleanup_error=?, updated_at=? WHERE outbox_id=?",
                (detail, self._timestamp(), outbox_id),
            )

    def prepared(self, row: sqlite3.Row) -> PreparedDelivery:
        return prepared_from_row(row)

    def _transition(
        self,
        outbox_id: str,
        status: str,
        *,
        http_status: int | None,
        error_code: str,
        error_detail: str,
        terminal: bool = False,
    ) -> None:
        now = self._timestamp()
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE delivery_outbox
                   SET status=?, last_http_status=?, last_error_code=?, last_error_detail=?,
                       updated_at=?, terminal_at=?
                 WHERE outbox_id=? AND status='sending'
                """,
                (status, http_status, error_code, error_detail, now, now if terminal else None, outbox_id),
            )

    @staticmethod
    def _require_same(row: sqlite3.Row, prepared: PreparedDelivery) -> None:
        expected = (
            ("artifact_id", prepared.artifact_id),
            ("manifest_sha256", prepared.manifest_sha256),
            ("upload_digest", prepared.upload_digest),
            ("idempotency_key", prepared.idempotency_key),
        )
        if any(row[field] != value for field, value in expected):
            raise FatalPortError("delivery position already belongs to different content")

    def _migrate(self) -> None:
        connection = self.connect()
        try:
            connection.executescript(MIGRATION_1)
            connection.execute(
                "INSERT OR IGNORE INTO delivery_schema_migrations(version, applied_at) VALUES (1, ?)",
                (self._timestamp(),),
            )
            connection.commit()
        except sqlite3.Error as exc:
            raise RecoverablePortError(f"cannot migrate delivery outbox: {exc}") from exc
        finally:
            connection.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
