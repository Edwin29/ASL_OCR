"""Transactional Server S0 catalog, scan, and persistent reading services."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from document_parser.accessibility import BraillePresenter, NavigationState
from document_parser.datapack.loader import Datapack, load_datapack
from document_parser.server.session import DatapackSession
from document_parser.server.s0_domain import (
    CatalogRecord,
    DatapackState,
    ReadingSessionRecord,
    ReadingState,
    S0ConflictError,
    S0NotFoundError,
    S0ValidationError,
    ScanSessionRecord,
    ScanState,
    require_id,
    require_nonnegative_int,
    require_positive_int,
)
from document_parser.server.s0_store import S0Store
from document_parser.server.wire import command_from_wire, result_to_wire


CURSOR_VERSION = 1
_AUDIO_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_AUDIO_MAX_BYTES = 4 * 1024 * 1024
_AUDIO_MAX_DURATION_MS = 120_000


@dataclass(frozen=True, slots=True)
class AudioResource:
    path: Path
    content_length: int
    sha256: str
    duration_ms: int
    sample_rate: int
    channels: int
    sample_width: int


class S0ControlPlane:
    def __init__(
        self,
        store: S0Store,
        *,
        now: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
        display_timezone: str = "Asia/Seoul",
    ) -> None:
        self.store = store
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4().hex}")
        self._display_timezone = ZoneInfo(display_timezone)
        self._datapack_cache: dict[tuple[str, int, str], Datapack] = {}
        self._cache_lock = threading.RLock()

    def bootstrap_existing_datapacks(self) -> tuple[dict[str, object], ...]:
        """Import valid legacy directories as revision 1 without modifying them."""

        results: list[dict[str, object]] = []
        root = self.store.datapacks_root
        for candidate in sorted(root.iterdir(), key=lambda path: path.name):
            if not candidate.is_dir() or candidate.name.startswith("_") or not _safe_storage_key(candidate.name):
                continue
            try:
                datapack = load_datapack(candidate, root / "_system")
                manifest_path = candidate / "manifest.json"
                manifest_hash = _sha256_file(manifest_path)
                manifest_id = require_id("manifest.book_id", str(datapack.manifest.get("book_id", "")))
                if manifest_id != candidate.name or datapack.book_id != candidate.name:
                    raise S0ConflictError(
                        "CATALOG_IDENTITY_MISMATCH",
                        "directory, manifest, and loaded datapack IDs must match",
                        {"storage_key": candidate.name, "manifest_id": manifest_id},
                    )
                title = str(datapack.manifest.get("title") or candidate.name).strip()
                if not title:
                    raise S0ValidationError("INVALID_TITLE", "datapack title must be non-empty")
                outcome = self._import_ready_datapack(candidate.name, title, manifest_hash)
                results.append({"datapack_id": candidate.name, "status": outcome})
            except S0ConflictError:
                raise
            except Exception as exc:  # invalid legacy directory remains untouched and non-READY
                results.append(
                    {
                        "datapack_id": candidate.name,
                        "status": "invalid",
                        "error": type(exc).__name__,
                    }
                )
        return tuple(results)

    def list_datapacks(self, device_id: str) -> tuple[CatalogRecord, ...]:
        device_id = require_id("device_id", device_id)
        now = self._timestamp()
        with self.store.transaction() as connection:
            self._touch_device(connection, device_id, now)
            rows = connection.execute(
                """
                SELECT datapack_id, title, status, current_revision, title_audio_ref,
                       created_at, updated_at
                  FROM datapacks
                 ORDER BY updated_at DESC, datapack_id ASC
                """
            ).fetchall()
        return tuple(_catalog_record(row) for row in rows)

    def create_datapack(self, device_id: str, operation_id: str) -> CatalogRecord:
        device_id = require_id("device_id", device_id)
        operation_id = require_id("operation_id", operation_id)
        request = {"device_id": device_id}
        request_hash = _json_sha256(request)
        now = self._timestamp()
        with self.store.transaction() as connection:
            self._touch_device(connection, device_id, now)
            replay = self._receipt(connection, "catalog_create", device_id, operation_id, request_hash)
            if replay is not None:
                return _catalog_record_from_dict(replay["catalog"])
            datapack_id = require_id("datapack_id", self._id_factory("datapack"))
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM datapacks WHERE created_by_device_id=?",
                    (device_id,),
                ).fetchone()[0]
            ) + 1
            display = self._now().astimezone(self._display_timezone)
            title = f"새 데이터팩 {display:%Y-%m-%d %H:%M} #{count:02d}"
            connection.execute(
                """
                INSERT INTO datapacks(
                    datapack_id, storage_key, title, status, current_revision,
                    created_by_device_id, created_at, updated_at
                ) VALUES (?, ?, ?, 'draft', NULL, ?, ?, ?)
                """,
                (datapack_id, datapack_id, title, device_id, now, now),
            )
            record = CatalogRecord(
                datapack_id,
                title,
                DatapackState.DRAFT,
                None,
                None,
                now,
                now,
            )
            response = {"catalog": _catalog_to_dict(record)}
            self._put_receipt(
                connection,
                "catalog_create",
                device_id,
                operation_id,
                request_hash,
                response,
                now,
            )
        return record

    def open_scan(
        self,
        device_id: str,
        datapack_id: str,
        operation_id: str,
    ) -> ScanSessionRecord:
        device_id = require_id("device_id", device_id)
        datapack_id = require_id("datapack_id", datapack_id)
        operation_id = require_id("operation_id", operation_id)
        request_hash = _json_sha256({"device_id": device_id, "datapack_id": datapack_id})
        now = self._timestamp()
        with self.store.transaction() as connection:
            self._touch_device(connection, device_id, now)
            replay = self._receipt(connection, "scan_open", device_id, operation_id, request_hash)
            if replay is not None:
                return _scan_record_from_dict(replay["scan_session"])
            datapack = connection.execute(
                "SELECT status, current_revision FROM datapacks WHERE datapack_id=?",
                (datapack_id,),
            ).fetchone()
            if datapack is None:
                raise S0NotFoundError("DATAPACK_NOT_FOUND", "unknown datapack_id")
            if datapack["status"] not in {DatapackState.DRAFT.value, DatapackState.READY.value}:
                raise S0ConflictError(
                    "DATAPACK_NOT_SCANNABLE",
                    "datapack is not in DRAFT or READY state",
                    {"status": datapack["status"]},
                )
            active = connection.execute(
                """
                SELECT * FROM scan_sessions
                 WHERE datapack_id=? AND status IN ('open','sealing')
                """,
                (datapack_id,),
            ).fetchone()
            if active is not None:
                if active["device_id"] != device_id:
                    raise S0ConflictError(
                        "DATAPACK_SCAN_BUSY",
                        "another device owns the active scan session",
                    )
                record = _scan_record(active)
            else:
                scan_session_id = require_id(
                    "scan_session_id", self._id_factory("scan")
                )
                connection.execute(
                    """
                    INSERT INTO scan_sessions(
                        scan_session_id, datapack_id, device_id, base_revision,
                        status, open_operation_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
                    """,
                    (
                        scan_session_id,
                        datapack_id,
                        device_id,
                        datapack["current_revision"],
                        operation_id,
                        now,
                        now,
                    ),
                )
                record = ScanSessionRecord(
                    scan_session_id,
                    datapack_id,
                    device_id,
                    datapack["current_revision"],
                    ScanState.OPEN,
                    None,
                    now,
                    now,
                )
            self._put_receipt(
                connection,
                "scan_open",
                device_id,
                operation_id,
                request_hash,
                {"scan_session": _scan_to_dict(record)},
                now,
            )
        return record

    def get_scan(self, scan_session_id: str) -> ScanSessionRecord:
        scan_session_id = require_id("scan_session_id", scan_session_id)
        with self.store.readonly() as connection:
            row = connection.execute(
                "SELECT * FROM scan_sessions WHERE scan_session_id=?",
                (scan_session_id,),
            ).fetchone()
        if row is None:
            raise S0NotFoundError("SCAN_SESSION_NOT_FOUND", "unknown scan_session_id")
        return _scan_record(row)

    def request_seal(
        self,
        scan_session_id: str,
        through_sequence: int,
    ) -> ScanSessionRecord:
        scan_session_id = require_id("scan_session_id", scan_session_id)
        through_sequence = require_nonnegative_int("through_sequence", through_sequence)
        now = self._timestamp()
        with self.store.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM scan_sessions WHERE scan_session_id=?",
                (scan_session_id,),
            ).fetchone()
            if row is None:
                raise S0NotFoundError("SCAN_SESSION_NOT_FOUND", "unknown scan_session_id")
            status = ScanState(row["status"])
            if status is ScanState.SEALING:
                if row["through_sequence"] != through_sequence:
                    raise S0ConflictError(
                        "SEAL_CUTOFF_CONFLICT",
                        "scan session is already sealing with a different cutoff",
                        {"existing_through_sequence": row["through_sequence"]},
                    )
                return _scan_record(row)
            if status is not ScanState.OPEN:
                raise S0ConflictError(
                    "SCAN_SESSION_NOT_OPEN",
                    "only an OPEN scan session can be sealed",
                    {"status": status.value},
                )
            seal_operation_id = f"seal:{through_sequence}"
            connection.execute(
                """
                UPDATE scan_sessions
                   SET status='sealing', through_sequence=?, seal_operation_id=?, updated_at=?
                 WHERE scan_session_id=?
                """,
                (through_sequence, seal_operation_id, now, scan_session_id),
            )
            connection.execute(
                "UPDATE datapacks SET status='finalizing', updated_at=? WHERE datapack_id=?",
                (now, row["datapack_id"]),
            )
            updated = connection.execute(
                "SELECT * FROM scan_sessions WHERE scan_session_id=?",
                (scan_session_id,),
            ).fetchone()
        return _scan_record(updated)

    def open_reading(
        self,
        device_id: str,
        datapack_id: str,
        viewport_size: int,
        operation_id: str,
    ) -> dict[str, object]:
        device_id = require_id("device_id", device_id)
        datapack_id = require_id("datapack_id", datapack_id)
        operation_id = require_id("operation_id", operation_id)
        viewport_size = require_positive_int("viewport_size", viewport_size)
        request_hash = _json_sha256(
            {
                "device_id": device_id,
                "datapack_id": datapack_id,
                "viewport_size": viewport_size,
            }
        )
        now = self._timestamp()
        with self.store.transaction() as connection:
            self._touch_device(connection, device_id, now)
            replay = self._receipt(connection, "reading_open", device_id, operation_id, request_hash)
            if replay is not None:
                return replay
            revision_row = self._ready_revision(connection, datapack_id)
            revision = int(revision_row["revision"])
            datapack = self._load_datapack(
                datapack_id,
                revision,
                revision_row["root_relative_path"],
                revision_row["manifest_sha256"],
            )
            existing = connection.execute(
                """
                SELECT * FROM reading_sessions
                 WHERE device_id=? AND datapack_id=? AND revision=?
                   AND viewport_size=? AND status='open'
                 ORDER BY created_at DESC LIMIT 1
                """,
                (device_id, datapack_id, revision, viewport_size),
            ).fetchone()
            if existing is None:
                reading_session_id = require_id(
                    "reading_session_id", self._id_factory("reading")
                )
                connection.execute(
                    """
                    INSERT INTO reading_sessions(
                        reading_session_id, device_id, datapack_id, revision,
                        viewport_size, status, open_operation_id, created_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
                    """,
                    (
                        reading_session_id,
                        device_id,
                        datapack_id,
                        revision,
                        viewport_size,
                        operation_id,
                        now,
                        now,
                    ),
                )
                reading = ReadingSessionRecord(
                    reading_session_id,
                    device_id,
                    datapack_id,
                    revision,
                    viewport_size,
                    ReadingState.OPEN,
                    now,
                    now,
                )
            else:
                reading = _reading_record(existing)
            state, has_progress = self._load_progress(
                connection, device_id, datapack_id, revision, datapack
            )
            session = DatapackSession(
                datapack,
                initial_state=state,
                braille_presenter=BraillePresenter(viewport_size=viewport_size),
            )
            response = self._reading_response(reading, session)
            if not has_progress:
                self._save_progress(connection, reading, datapack, session.state, now)
            self._put_receipt(
                connection,
                "reading_open",
                device_id,
                operation_id,
                request_hash,
                response,
                now,
            )
        return response

    def get_reading(self, reading_session_id: str) -> dict[str, object]:
        reading_session_id = require_id("reading_session_id", reading_session_id)
        now = self._timestamp()
        with self.store.transaction() as connection:
            reading = self._reading_session(connection, reading_session_id)
            datapack, state = self._datapack_and_state(connection, reading)
            session = DatapackSession(
                datapack,
                initial_state=state,
                braille_presenter=BraillePresenter(viewport_size=reading.viewport_size),
            )
            connection.execute(
                "UPDATE reading_sessions SET last_seen_at=? WHERE reading_session_id=?",
                (now, reading_session_id),
            )
            response = self._reading_response(reading, session)
        return response

    def send_reading_command(
        self,
        reading_session_id: str,
        command_id: str,
        button: str,
        action: str,
    ) -> dict[str, object]:
        reading_session_id = require_id("reading_session_id", reading_session_id)
        command_id = require_id("command_id", command_id)
        payload = {"button": button, "action": action}
        try:
            command = command_from_wire(payload)
        except ValueError as exc:
            raise S0ValidationError("INVALID_READING_COMMAND", str(exc)) from exc
        request_hash = _json_sha256(payload)
        now = self._timestamp()
        with self.store.transaction() as connection:
            replay = self._receipt(
                connection,
                "reading_command",
                reading_session_id,
                command_id,
                request_hash,
            )
            if replay is not None:
                return replay
            reading = self._reading_session(connection, reading_session_id)
            datapack, state = self._datapack_and_state(connection, reading)
            # This object is deliberately local to the transaction. If commit
            # fails, its advanced state is discarded rather than cached.
            session = DatapackSession(
                datapack,
                initial_state=state,
                braille_presenter=BraillePresenter(viewport_size=reading.viewport_size),
            )
            result = session.handle_button(command)
            response = self._reading_response(reading, session, result)
            self._save_progress(connection, reading, datapack, session.state, now)
            connection.execute(
                "UPDATE reading_sessions SET last_seen_at=? WHERE reading_session_id=?",
                (now, reading_session_id),
            )
            self._put_receipt(
                connection,
                "reading_command",
                reading_session_id,
                command_id,
                request_hash,
                response,
                now,
            )
        return response

    def get_audio_resource(
        self,
        reading_session_id: str,
        audio_id: str,
    ) -> AudioResource:
        """Resolve one opaque audio ID inside a reading session's pinned revision."""

        reading_session_id = require_id("reading_session_id", reading_session_id)
        token = _audio_token(audio_id)
        now = self._timestamp()
        with self.store.transaction() as connection:
            reading = self._reading_session(connection, reading_session_id)
            revision = connection.execute(
                """
                SELECT * FROM datapack_revisions
                 WHERE datapack_id=? AND revision=? AND status IN ('ready','superseded')
                """,
                (reading.datapack_id, reading.revision),
            ).fetchone()
            if revision is None:
                raise S0ConflictError(
                    "READING_REVISION_UNAVAILABLE", "reading revision is unavailable"
                )
            datapack = self._load_datapack(
                reading.datapack_id,
                reading.revision,
                revision["root_relative_path"],
                revision["manifest_sha256"],
            )
            revision_root = (
                self.store.datapacks_root / Path(revision["root_relative_path"])
            ).resolve()
            system_root = (self.store.datapacks_root / "_system").resolve()
            connection.execute(
                "UPDATE reading_sessions SET last_seen_at=? WHERE reading_session_id=?",
                (now, reading_session_id),
            )

        expected_ref = f"s0-audio:{token}"
        for entry in datapack.audio_by_text.values():
            audio_path = entry.get("wav")
            if not isinstance(audio_path, str):
                continue
            path = Path(audio_path).resolve()
            if not (_path_within(path, revision_root) or _path_within(path, system_root)):
                raise S0ConflictError(
                    "AUDIO_PATH_INVALID", "audio path escapes the reading revision"
                )
            if self._opaque_audio_ref(str(path), reading_session_id) != expected_ref:
                continue
            return _inspect_audio_resource(path)
        raise S0NotFoundError("AUDIO_RESOURCE_NOT_FOUND", "unknown audio resource")

    def invalidate_datapack_cache(self, datapack_id: str) -> None:
        datapack_id = require_id("datapack_id", datapack_id)
        with self._cache_lock:
            stale = [key for key in self._datapack_cache if key[0] == datapack_id]
            for key in stale:
                self._datapack_cache.pop(key, None)

    def _import_ready_datapack(self, datapack_id: str, title: str, manifest_hash: str) -> str:
        now = self._timestamp()
        with self.store.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM datapacks WHERE datapack_id=?", (datapack_id,)
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO datapacks(
                        datapack_id, storage_key, title, status, current_revision,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'ready', 1, ?, ?)
                    """,
                    (datapack_id, datapack_id, title, now, now),
                )
                connection.execute(
                    """
                    INSERT INTO datapack_revisions(
                        datapack_id, revision, status, root_relative_path,
                        manifest_sha256, created_at, published_at
                    ) VALUES (?, 1, 'ready', ?, ?, ?, ?)
                    """,
                    (datapack_id, datapack_id, manifest_hash, now, now),
                )
                return "imported"
            revision = connection.execute(
                """
                SELECT manifest_sha256 FROM datapack_revisions
                 WHERE datapack_id=? AND revision=?
                """,
                (datapack_id, existing["current_revision"]),
            ).fetchone()
            if revision is None or revision["manifest_sha256"] != manifest_hash:
                raise S0ConflictError(
                    "CATALOG_RECONCILIATION_CONFLICT",
                    "existing catalog identity has a different manifest hash",
                    {"datapack_id": datapack_id},
                )
            return "unchanged"

    def _ready_revision(self, connection, datapack_id: str):
        datapack = connection.execute(
            "SELECT status, current_revision FROM datapacks WHERE datapack_id=?",
            (datapack_id,),
        ).fetchone()
        if datapack is None:
            raise S0NotFoundError("DATAPACK_NOT_FOUND", "unknown datapack_id")
        if datapack["status"] is not None and datapack["status"] != DatapackState.READY.value:
            raise S0ConflictError(
                "DATAPACK_NOT_READY",
                "reading requires a READY datapack",
                {"status": datapack["status"]},
            )
        revision = connection.execute(
            """
            SELECT * FROM datapack_revisions
             WHERE datapack_id=? AND revision=? AND status='ready'
            """,
            (datapack_id, datapack["current_revision"]),
        ).fetchone()
        if revision is None:
            raise S0ConflictError(
                "CURRENT_REVISION_INVALID",
                "current revision does not resolve to a READY revision",
            )
        return revision

    def _reading_session(self, connection, reading_session_id: str) -> ReadingSessionRecord:
        row = connection.execute(
            "SELECT * FROM reading_sessions WHERE reading_session_id=?",
            (reading_session_id,),
        ).fetchone()
        if row is None:
            raise S0NotFoundError("READING_SESSION_NOT_FOUND", "unknown reading_session_id")
        record = _reading_record(row)
        if record.status is not ReadingState.OPEN:
            raise S0ConflictError("READING_SESSION_NOT_OPEN", "reading session is not OPEN")
        return record

    def _datapack_and_state(self, connection, reading: ReadingSessionRecord):
        revision = connection.execute(
            """
            SELECT * FROM datapack_revisions
             WHERE datapack_id=? AND revision=? AND status IN ('ready','superseded')
            """,
            (reading.datapack_id, reading.revision),
        ).fetchone()
        if revision is None:
            raise S0ConflictError("READING_REVISION_UNAVAILABLE", "reading revision is unavailable")
        datapack = self._load_datapack(
            reading.datapack_id,
            reading.revision,
            revision["root_relative_path"],
            revision["manifest_sha256"],
        )
        state, _has_progress = self._load_progress(
            connection,
            reading.device_id,
            reading.datapack_id,
            reading.revision,
            datapack,
        )
        return datapack, state

    def _load_progress(self, connection, device_id, datapack_id, revision, datapack):
        row = connection.execute(
            "SELECT * FROM reading_progress WHERE device_id=? AND datapack_id=?",
            (device_id, datapack_id),
        ).fetchone()
        if row is None:
            return NavigationState(datapack.document["document_id"], 0, 0), False
        if int(row["cursor_version"]) != CURSOR_VERSION:
            raise S0ConflictError(
                "READING_CURSOR_VERSION_UNSUPPORTED",
                "stored cursor version is not supported",
            )
        try:
            cursor = json.loads(row["cursor_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise S0ConflictError("READING_CURSOR_INVALID", "stored cursor JSON is invalid") from exc
        return _cursor_to_state(cursor, datapack, int(row["revision_seen"]), revision), True

    def _save_progress(self, connection, reading, datapack, state, now):
        cursor = _state_to_cursor(datapack, state)
        connection.execute(
            """
            INSERT INTO reading_progress(
                device_id, datapack_id, revision_seen, cursor_json,
                cursor_version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id, datapack_id) DO UPDATE SET
                revision_seen=excluded.revision_seen,
                cursor_json=excluded.cursor_json,
                cursor_version=excluded.cursor_version,
                updated_at=excluded.updated_at
            """,
            (
                reading.device_id,
                reading.datapack_id,
                reading.revision,
                _canonical_json(cursor),
                CURSOR_VERSION,
                now,
            ),
        )

    def _load_datapack(self, datapack_id, revision, relative_root, manifest_hash):
        relative = Path(relative_root)
        if relative.is_absolute() or ".." in relative.parts:
            raise S0ConflictError("DATAPACK_PATH_INVALID", "revision root escapes datapacks root")
        root = (self.store.datapacks_root / relative).resolve()
        if self.store.datapacks_root != root and self.store.datapacks_root not in root.parents:
            raise S0ConflictError("DATAPACK_PATH_INVALID", "revision root escapes datapacks root")
        if _sha256_file(root / "manifest.json") != manifest_hash:
            raise S0ConflictError("DATAPACK_MANIFEST_CHANGED", "revision manifest hash mismatch")
        key = (datapack_id, revision, manifest_hash)
        with self._cache_lock:
            cached = self._datapack_cache.get(key)
            if cached is not None:
                return cached
            loaded = load_datapack(root, self.store.datapacks_root / "_system")
            if loaded.book_id != datapack_id:
                raise S0ConflictError("DATAPACK_IDENTITY_MISMATCH", "loaded datapack ID mismatch")
            self._datapack_cache[key] = loaded
            return loaded

    def _reading_response(self, reading, session, result=None):
        wire = result_to_wire(
            result
            or {
                "state": session.state,
                "braille_frame": session.braille_frame,
                "audio": session.audio,
            }
        )
        audio = wire.get("audio")
        if isinstance(audio, dict) and isinstance(audio.get("audio_ref"), str):
            audio["audio_ref"] = self._opaque_audio_ref(
                audio["audio_ref"], reading.reading_session_id
            )
        return {
            "reading_session_id": reading.reading_session_id,
            "datapack_id": reading.datapack_id,
            "revision": reading.revision,
            "cursor": _state_to_cursor(session.datapack, session.state),
            "state": wire["state"],
            "braille_frame": wire["braille_frame"],
            "audio": wire["audio"],
        }

    def _opaque_audio_ref(self, audio_path: str, reading_session_id: str) -> str:
        path = Path(audio_path).resolve()
        try:
            relative = path.relative_to(self.store.datapacks_root)
        except ValueError as exc:
            raise S0ConflictError("AUDIO_PATH_INVALID", "audio path escapes datapacks root") from exc
        digest = hashlib.sha256(
            f"{reading_session_id}\0{relative.as_posix()}".encode("utf-8")
        ).hexdigest()[:32]
        return f"s0-audio:{digest}"

    def _touch_device(self, connection, device_id, now):
        connection.execute(
            """
            INSERT INTO devices(device_id, first_seen_at, last_seen_at)
            VALUES (?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET last_seen_at=excluded.last_seen_at
            """,
            (device_id, now, now),
        )

    def _receipt(self, connection, scope_type, scope_id, command_id, request_hash):
        row = connection.execute(
            """
            SELECT request_sha256, response_json FROM command_receipts
             WHERE scope_type=? AND scope_id=? AND command_id=?
            """,
            (scope_type, scope_id, command_id),
        ).fetchone()
        if row is None:
            return None
        if row["request_sha256"] != request_hash:
            raise S0ConflictError(
                "IDEMPOTENCY_KEY_REUSED",
                "command ID was already used with a different request",
            )
        return json.loads(row["response_json"])

    def _put_receipt(
        self,
        connection,
        scope_type,
        scope_id,
        command_id,
        request_hash,
        response,
        now,
    ):
        connection.execute(
            """
            INSERT INTO command_receipts(
                scope_type, scope_id, command_id, request_sha256, response_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (scope_type, scope_id, command_id, request_hash, _canonical_json(response), now),
        )

    def _timestamp(self) -> str:
        return self._now().astimezone(timezone.utc).isoformat(timespec="microseconds")


def _state_to_cursor(datapack: Datapack, state: NavigationState) -> dict[str, object]:
    pages = datapack.document.get("pages")
    if not isinstance(pages, list) or not 0 <= state.page_index < len(pages):
        raise S0ConflictError("READING_CURSOR_INVALID", "page index is outside the document")
    page = pages[state.page_index]
    items = page.get("focus_items") if isinstance(page, dict) else None
    if not isinstance(items, list) or not 0 <= state.node_index < len(items):
        raise S0ConflictError("READING_CURSOR_INVALID", "node index is outside the page")
    item = items[state.node_index]
    page_id = page.get("page_id")
    item_id = item.get("id") if isinstance(item, dict) else None
    if not isinstance(page_id, str) or not page_id or not isinstance(item_id, str) or not item_id:
        raise S0ConflictError("READING_CURSOR_INVALID", "stable page/item anchor is missing")
    return {
        "document_id": state.document_id,
        "page_id": page_id,
        "focus_item_id": item_id,
        "page_index": state.page_index,
        "node_index": state.node_index,
        "mode": state.mode,
        "table_row": state.table_row,
        "table_column": state.table_column,
        "braille_offset": state.braille_offset,
        "math_span_index": state.math_span_index,
        "generation": state.generation,
    }


def _cursor_to_state(
    cursor: dict[str, object],
    datapack: Datapack,
    revision_seen: int,
    current_revision: int,
) -> NavigationState:
    if not isinstance(cursor, dict) or cursor.get("document_id") != datapack.document.get("document_id"):
        raise S0ConflictError("READING_CURSOR_INVALID", "cursor document identity mismatch")
    page_id = cursor.get("page_id")
    item_id = cursor.get("focus_item_id")
    pages = datapack.document.get("pages")
    if not isinstance(page_id, str) or not isinstance(item_id, str) or not isinstance(pages, list):
        raise S0ConflictError("READING_CURSOR_INVALID", "cursor stable anchors are invalid")
    page_index = next(
        (index for index, page in enumerate(pages) if isinstance(page, dict) and page.get("page_id") == page_id),
        None,
    )
    if page_index is None:
        raise S0ConflictError("READING_CURSOR_INVALID", "stored page anchor no longer exists")
    items = pages[page_index].get("focus_items")
    node_index = next(
        (index for index, item in enumerate(items or []) if isinstance(item, dict) and item.get("id") == item_id),
        None,
    )
    if node_index is None:
        raise S0ConflictError("READING_CURSOR_INVALID", "stored focus item anchor no longer exists")
    if revision_seen == current_revision and (
        cursor.get("page_index") != page_index or cursor.get("node_index") != node_index
    ):
        raise S0ConflictError("READING_CURSOR_INVALID", "same-revision index/anchor mismatch")
    mode = cursor.get("mode")
    if mode not in {"DOCUMENT", "TABLE"}:
        raise S0ConflictError("READING_CURSOR_INVALID", "cursor mode is invalid")
    integers: dict[str, int] = {}
    for name in ("braille_offset", "math_span_index", "generation"):
        value = cursor.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise S0ConflictError("READING_CURSOR_INVALID", f"cursor {name} is invalid")
        integers[name] = value
    table_row = cursor.get("table_row")
    table_column = cursor.get("table_column")
    for name, value in (("table_row", table_row), ("table_column", table_column)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise S0ConflictError("READING_CURSOR_INVALID", f"cursor {name} is invalid")
    return NavigationState(
        document_id=str(cursor["document_id"]),
        page_index=page_index,
        node_index=node_index,
        mode=mode,
        table_row=table_row,
        table_column=table_column,
        braille_offset=integers["braille_offset"],
        math_span_index=integers["math_span_index"],
        generation=integers["generation"],
    )


def _catalog_record(row) -> CatalogRecord:
    return CatalogRecord(
        row["datapack_id"],
        row["title"],
        DatapackState(row["status"]),
        row["current_revision"],
        row["title_audio_ref"],
        row["created_at"],
        row["updated_at"],
    )


def _scan_record(row) -> ScanSessionRecord:
    return ScanSessionRecord(
        row["scan_session_id"],
        row["datapack_id"],
        row["device_id"],
        row["base_revision"],
        ScanState(row["status"]),
        row["through_sequence"],
        row["created_at"],
        row["updated_at"],
    )


def _reading_record(row) -> ReadingSessionRecord:
    return ReadingSessionRecord(
        row["reading_session_id"],
        row["device_id"],
        row["datapack_id"],
        int(row["revision"]),
        int(row["viewport_size"]),
        ReadingState(row["status"]),
        row["created_at"],
        row["last_seen_at"],
    )


def _catalog_to_dict(record: CatalogRecord) -> dict[str, object]:
    return {
        "datapack_id": record.datapack_id,
        "title": record.title,
        "status": record.status.value,
        "revision": record.current_revision,
        "title_audio_ref": record.title_audio_ref,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _scan_to_dict(record: ScanSessionRecord) -> dict[str, object]:
    return {
        "scan_session_id": record.scan_session_id,
        "datapack_id": record.datapack_id,
        "device_id": record.device_id,
        "base_revision": record.base_revision,
        "status": record.status.value,
        "through_sequence": record.through_sequence,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _catalog_record_from_dict(value: object) -> CatalogRecord:
    if not isinstance(value, dict):
        raise RuntimeError("stored catalog receipt is invalid")
    return CatalogRecord(
        str(value["datapack_id"]),
        str(value["title"]),
        DatapackState(str(value["status"])),
        value.get("revision") if isinstance(value.get("revision"), int) else None,
        value.get("title_audio_ref") if isinstance(value.get("title_audio_ref"), str) else None,
        str(value["created_at"]),
        str(value["updated_at"]),
    )


def _scan_record_from_dict(value: object) -> ScanSessionRecord:
    if not isinstance(value, dict):
        raise RuntimeError("stored scan receipt is invalid")
    return ScanSessionRecord(
        str(value["scan_session_id"]),
        str(value["datapack_id"]),
        str(value["device_id"]),
        value.get("base_revision") if isinstance(value.get("base_revision"), int) else None,
        ScanState(str(value["status"])),
        value.get("through_sequence") if isinstance(value.get("through_sequence"), int) else None,
        str(value["created_at"]),
        str(value["updated_at"]),
    )


def _safe_storage_key(value: str) -> bool:
    return bool(value and value not in {".", ".."} and Path(value).name == value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audio_token(value: object) -> str:
    if not isinstance(value, str):
        raise S0NotFoundError("AUDIO_RESOURCE_NOT_FOUND", "unknown audio resource")
    token = value.removeprefix("s0-audio:")
    if _AUDIO_ID_RE.fullmatch(token) is None:
        raise S0NotFoundError("AUDIO_RESOURCE_NOT_FOUND", "unknown audio resource")
    return token


def _path_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _inspect_audio_resource(path: Path) -> AudioResource:
    if not path.is_file():
        raise S0NotFoundError("AUDIO_RESOURCE_NOT_FOUND", "unknown audio resource")
    content_length = path.stat().st_size
    if content_length <= 0 or content_length > _AUDIO_MAX_BYTES:
        raise S0ConflictError(
            "AUDIO_RESOURCE_SIZE_INVALID", "audio resource exceeds the supported size"
        )
    try:
        with wave.open(str(path), "rb") as audio:
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            sample_rate = audio.getframerate()
            frame_count = audio.getnframes()
    except (OSError, EOFError, wave.Error) as exc:
        raise S0ConflictError(
            "AUDIO_RESOURCE_DECODE_FAILED", "audio resource is not a valid WAV"
        ) from exc
    duration_ms = round(frame_count * 1000 / sample_rate) if sample_rate > 0 else 0
    if (
        channels not in {1, 2}
        or sample_width != 2
        or not 8_000 <= sample_rate <= 48_000
        or frame_count <= 0
        or duration_ms <= 0
        or duration_ms > _AUDIO_MAX_DURATION_MS
    ):
        raise S0ConflictError(
            "AUDIO_RESOURCE_FORMAT_INVALID", "audio resource format is unsupported"
        )
    return AudioResource(
        path=path,
        content_length=content_length,
        sha256=_sha256_file(path),
        duration_ms=duration_ms,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
