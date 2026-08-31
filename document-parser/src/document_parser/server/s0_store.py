"""SQLite repository and migration runner for Server S0."""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from document_parser.server.s0_domain import S0TemporaryError
from document_parser.server.s0_migrations import MIGRATIONS


class S0Store:
    def __init__(
        self,
        database_path: str | Path,
        datapacks_root: str | Path,
        *,
        busy_timeout_ms: int = 3000,
    ) -> None:
        self.database_path = Path(database_path).resolve()
        self.datapacks_root = Path(datapacks_root).resolve()
        if busy_timeout_ms <= 0:
            raise ValueError("busy_timeout_ms must be positive")
        self.busy_timeout_ms = busy_timeout_ms
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.datapacks_root.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                self.database_path,
                timeout=self.busy_timeout_ms / 1000.0,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            connection.execute("PRAGMA journal_mode=WAL")
            return connection
        except sqlite3.Error as exc:
            raise _database_error(exc) from exc

    def migrate(self) -> None:
        connection = self.connect()
        try:
            has_migrations = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            applied = (
                {int(row[0]) for row in connection.execute("SELECT version FROM schema_migrations")}
                if has_migrations
                else set()
            )
            known = {version for version, _sql in MIGRATIONS}
            unknown = applied - known
            if unknown:
                raise RuntimeError(f"database has unknown future migration(s): {sorted(unknown)}")
            for version, sql in MIGRATIONS:
                if version in applied:
                    continue
                now = _utc_now()
                script = (
                    "BEGIN IMMEDIATE;\n"
                    + sql
                    + f"\nINSERT INTO schema_migrations(version, applied_at) VALUES ({version}, '{now}');\n"
                    + "COMMIT;"
                )
                try:
                    connection.executescript(script)
                except sqlite3.Error:
                    with contextlib.suppress(sqlite3.Error):
                        connection.execute("ROLLBACK")
                    raise
        except sqlite3.Error as exc:
            raise _database_error(exc) from exc
        finally:
            connection.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except sqlite3.Error as exc:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise _database_error(exc) from exc
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @contextlib.contextmanager
    def readonly(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        except sqlite3.Error as exc:
            raise _database_error(exc) from exc
        finally:
            connection.close()

    def health(self) -> dict[str, object]:
        with self.transaction() as connection:
            version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            connection.execute("SELECT COUNT(*) FROM datapacks").fetchone()
        return {"database": "ok", "schema_version": int(version or 0), "writable": True}


def _database_error(exc: sqlite3.Error) -> S0TemporaryError:
    message = str(exc)
    code = "DATABASE_BUSY" if "locked" in message.lower() or "busy" in message.lower() else "DATABASE_ERROR"
    return S0TemporaryError(code, message)


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
