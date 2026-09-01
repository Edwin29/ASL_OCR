"""Durable Server V4 bundle writer and S1 handoff service."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable

from document_parser.server.s0_domain import (
    S0ConflictError,
    S0Error,
    S0NotFoundError,
    S0TemporaryError,
    require_id,
)
from document_parser.server.s0_store import S0Store
from document_parser.server.s1_domain import VerifiedSpreadInput
from document_parser.server.v4_domain import (
    FileDeclaration,
    PreparedUpload,
    V4BundleRejectedError,
    V4CapacityError,
    V4Config,
    V4Result,
    prepare_upload,
    safe_relative_path,
)


_SERVER_UPLOAD_DIR_RE = re.compile(r"^upload-[0-9a-f]{32}$")


class V4UploadService:
    def __init__(
        self,
        store: S0Store,
        s1_pipeline: Any,
        config: V4Config,
        *,
        timestamp: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.s1 = s1_pipeline
        self.config = config
        self._timestamp = timestamp or _utc_now
        self._admission_lock = threading.Lock()
        self._admitted_requests = 0
        self._admitted_bytes = 0
        for root in (config.staging_root, config.received_root, config.quarantine_root):
            resolved = root.resolve()
            datapacks = store.datapacks_root.resolve()
            if resolved != datapacks and datapacks not in resolved.parents:
                raise ValueError("V4 storage roots must be inside datapacks root")
            root.mkdir(parents=True, exist_ok=True)
        if config.staging_root.stat().st_dev != config.received_root.stat().st_dev:
            raise ValueError("V4 staging and received roots must share a filesystem")

    @contextmanager
    def admit_http_request(self, content_length: int):
        with self._admission_lock:
            if self._admitted_requests >= self.config.max_concurrent_upload_writers:
                raise V4CapacityError("UPLOAD_CAPACITY_BUSY", "upload writer capacity is busy")
            if self._admitted_bytes + content_length > self.config.max_staging_bytes:
                raise V4CapacityError(
                    "UPLOAD_STORAGE_QUOTA",
                    "upload staging quota is exhausted",
                    http_status=507,
                )
            self._admitted_requests += 1
            self._admitted_bytes += content_length
        try:
            yield
        finally:
            with self._admission_lock:
                self._admitted_requests -= 1
                self._admitted_bytes -= content_length

    def accept_upload(
        self,
        *,
        scan_session_id: str,
        idempotency_key: str,
        upload_digest: str,
        metadata_bytes: bytes,
        manifest_bytes: bytes,
        files: Iterable[tuple[str, BinaryIO]],
    ) -> V4Result:
        scan_session_id = require_id("scan_session_id", scan_session_id)
        idempotency_key = require_id("Idempotency-Key", idempotency_key)
        prepared = prepare_upload(
            scan_session_id,
            metadata_bytes,
            manifest_bytes,
            upload_digest,
            self.config,
        )
        previous = self._existing_attempt(prepared, idempotency_key)
        if previous is not None:
            return previous
        existing = self._reconcile_existing_spread(prepared, idempotency_key)
        if existing is not None:
            return existing
        upload_id, staging = self._claim(prepared, idempotency_key)
        try:
            self._write_staging(staging, prepared, files)
            bundle_key = self._promote(upload_id, staging)
            now = self._timestamp()
            with self.store.transaction() as connection:
                connection.execute(
                    """
                    UPDATE spread_upload_attempts
                       SET status='promoted', staging_relative_path=NULL,
                           bundle_relative_path=?, received_file_count=?, received_total_bytes=?,
                           lease_owner=NULL, lease_until=NULL, updated_at=?
                     WHERE upload_id=? AND status='receiving'
                    """,
                    (
                        bundle_key,
                        len(prepared.files),
                        prepared.metadata.total_file_bytes,
                        now,
                        upload_id,
                    ),
                )
            return self._handoff(upload_id, prepared, bundle_key, http_status=201)
        except S0Error as exc:
            if exc.retryable:
                self._abandon_receiving(upload_id, staging, exc)
            else:
                self._reject(upload_id, staging, exc)
            raise
        except OSError as exc:
            error = S0TemporaryError("UPLOAD_STORAGE_TEMPORARY", "temporary upload storage failure")
            self._abandon_receiving(upload_id, staging, error)
            raise error from exc
        except BaseException:
            self._abandon_receiving(
                upload_id,
                staging,
                S0TemporaryError("UPLOAD_INTERRUPTED", "upload was interrupted"),
            )
            raise

    def recover(self) -> dict[str, int]:
        abandoned = self._recover_receiving_after_restart()
        quarantined = self._quarantine_untracked_final_directories()
        promoted = 0
        with self.store.readonly() as connection:
            rows = connection.execute(
                "SELECT * FROM spread_upload_attempts WHERE status='promoted' ORDER BY created_at, upload_id"
            ).fetchall()
        for row in rows:
            try:
                prepared = self._prepared_from_row(row)
                bundle_key = str(row["bundle_relative_path"])
                bundle = self.config.received_root / Path(bundle_key)
                if not bundle.is_dir():
                    raise S0ConflictError(
                        "UPLOAD_PROMOTION_LOST", "promoted upload directory is missing"
                    )
                self._handoff(str(row["upload_id"]), prepared, bundle_key, http_status=201)
                promoted += 1
            except S0Error as exc:
                if not exc.retryable:
                    self._store_terminal_error(str(row["upload_id"]), exc)
            except OSError:
                # The promoted row remains authoritative and will be retried after
                # the storage condition is repaired.
                continue
        return {"abandoned": abandoned, "accepted": promoted, "quarantined": quarantined}

    def cleanup_partial_orphans(self, *, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.config.partial_orphan_ttl_seconds)
        with self.store.readonly() as connection:
            referenced = {
                str(row[0])
                for row in connection.execute(
                    "SELECT staging_relative_path FROM spread_upload_attempts WHERE staging_relative_path IS NOT NULL"
                )
            }
        removed = 0
        for path in self.config.staging_root.iterdir():
            if path.name in referenced or path.is_symlink() or not path.is_dir():
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified <= cutoff:
                try:
                    shutil.rmtree(path)
                except OSError:
                    continue
                else:
                    removed += 1
        return removed

    def _quarantine_untracked_final_directories(self) -> int:
        v4_root = self.config.received_root / "v4"
        if not v4_root.is_dir():
            return 0
        with self.store.readonly() as connection:
            referenced = {
                str(row[0])
                for row in connection.execute(
                    "SELECT bundle_relative_path FROM spread_upload_attempts "
                    "WHERE bundle_relative_path IS NOT NULL"
                )
            }
        quarantined = 0
        for source in v4_root.iterdir():
            relative = (Path("v4") / source.name).as_posix()
            if (
                relative in referenced
                or _SERVER_UPLOAD_DIR_RE.fullmatch(source.name) is None
                or _is_link_like(source)
                or not source.is_dir()
            ):
                continue
            destination = self.config.quarantine_root / source.name
            if destination.exists():
                continue
            try:
                os.replace(source, destination)
                _fsync_directory(v4_root)
                _fsync_directory(self.config.quarantine_root)
            except OSError:
                continue
            quarantined += 1
        return quarantined

    def _existing_attempt(self, prepared: PreparedUpload, key: str) -> V4Result | None:
        with self.store.readonly() as connection:
            row = connection.execute(
                "SELECT * FROM spread_upload_attempts WHERE scan_session_id=? AND idempotency_key=?",
                (prepared.scan_session_id, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_sha256"] != prepared.upload_digest:
            raise S0ConflictError("IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was reused with different content")
        if row["status"] in {"accepted", "rejected"}:
            if row["response_json"] is None or row["response_http_status"] is None:
                raise S0TemporaryError("UPLOAD_JOURNAL_INCOMPLETE", "terminal upload response is missing")
            return V4Result(json.loads(row["response_json"]), int(row["response_http_status"]), replayed=True)
        if row["status"] == "promoted":
            return self._handoff(
                str(row["upload_id"]),
                prepared,
                str(row["bundle_relative_path"]),
                http_status=201,
                replayed=True,
            )
        if row["status"] == "receiving":
            inferred_key = (Path("v4") / str(row["upload_id"])).as_posix()
            inferred_final = self.config.received_root / Path(inferred_key)
            if inferred_final.is_dir():
                now = self._timestamp()
                with self.store.transaction() as connection:
                    connection.execute(
                        """
                        UPDATE spread_upload_attempts
                           SET status='promoted', staging_relative_path=NULL,
                               bundle_relative_path=?, received_file_count=declared_file_count,
                               received_total_bytes=declared_total_bytes,
                               lease_owner=NULL, lease_until=NULL, updated_at=?
                         WHERE upload_id=? AND status='receiving'
                        """,
                        (inferred_key, now, row["upload_id"]),
                    )
                return self._handoff(
                    str(row["upload_id"]),
                    prepared,
                    inferred_key,
                    http_status=201,
                    replayed=True,
                )
            if not _lease_expired(row["lease_until"]):
                raise V4CapacityError("UPLOAD_IN_PROGRESS", "the same upload is currently in progress")
        staging = self._staging_path(row["staging_relative_path"])
        if staging is not None and staging.exists():
            _remove_tree_best_effort(staging)
        return None

    def _reconcile_existing_spread(self, prepared: PreparedUpload, key: str) -> V4Result | None:
        metadata = prepared.metadata
        with self.store.transaction() as connection:
            scan = connection.execute(
                "SELECT * FROM scan_sessions WHERE scan_session_id=?",
                (prepared.scan_session_id,),
            ).fetchone()
            if scan is None:
                raise S0NotFoundError("SCAN_SESSION_NOT_FOUND", "unknown scan_session_id")
            if scan["device_id"] != metadata.device_id:
                raise S0ConflictError("SCAN_DEVICE_MISMATCH", "upload device does not own this scan")
            _require_scan_accepts(scan, metadata.sequence)
            active_position = connection.execute(
                """
                SELECT upload_id FROM spread_upload_attempts
                 WHERE scan_session_id=? AND sequence=? AND status IN ('receiving','promoted')
                   AND NOT (idempotency_key=? AND request_sha256=?)
                """,
                (prepared.scan_session_id, metadata.sequence, key, prepared.upload_digest),
            ).fetchone()
            if active_position is not None:
                raise V4CapacityError(
                    "UPLOAD_IN_PROGRESS", "another upload for this logical sequence is in progress"
                )
            active_artifact = connection.execute(
                """
                SELECT upload_id FROM spread_upload_attempts
                 WHERE artifact_id=? AND status IN ('receiving','promoted')
                   AND NOT (scan_session_id=? AND idempotency_key=? AND request_sha256=?)
                """,
                (metadata.artifact_id, prepared.scan_session_id, key, prepared.upload_digest),
            ).fetchone()
            if active_artifact is not None:
                raise V4CapacityError(
                    "UPLOAD_IN_PROGRESS", "another upload for this artifact is in progress"
                )
            row = connection.execute(
                "SELECT * FROM scan_spreads WHERE scan_session_id=? AND sequence=?",
                (prepared.scan_session_id, metadata.sequence),
            ).fetchone()
            if row is None:
                artifact = connection.execute(
                    "SELECT scan_session_id, sequence FROM scan_spreads WHERE artifact_id=?",
                    (metadata.artifact_id,),
                ).fetchone()
                if artifact is not None:
                    raise S0ConflictError(
                        "ARTIFACT_ID_COLLISION",
                        "artifact_id was already assigned to another logical position",
                    )
                return None
            same = (
                row["artifact_id"] == metadata.artifact_id
                and row["spread_id"] == metadata.spread_id
                and row["source_frame_id"] == metadata.source_frame_id
                and row["manifest_sha256"] == metadata.manifest_sha256
            )
            if not same:
                raise S0ConflictError(
                    "SPREAD_SEQUENCE_COLLISION",
                    "sequence was already accepted with different content",
                )
            now = self._timestamp()
            upload_id = f"upload-{uuid.uuid4().hex}"
            body = _success_body(prepared, str(row["receipt_id"]), str(row["received_at"]), str(row["status"]))
            connection.execute(
                """
                INSERT INTO spread_upload_attempts(
                    upload_id, scan_session_id, device_id, sequence, idempotency_key,
                    request_sha256, artifact_id, spread_id, source_frame_id, manifest_sha256,
                    declared_file_count, declared_total_bytes, received_file_count, received_total_bytes,
                    status, attempt_count, bundle_relative_path, s1_receipt_id,
                    response_http_status, response_json, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', 1, ?, ?, 200, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    prepared.scan_session_id,
                    metadata.device_id,
                    metadata.sequence,
                    key,
                    prepared.upload_digest,
                    metadata.artifact_id,
                    metadata.spread_id,
                    metadata.source_frame_id,
                    metadata.manifest_sha256,
                    metadata.file_count,
                    metadata.total_file_bytes,
                    metadata.file_count,
                    metadata.total_file_bytes,
                    row["bundle_relative_path"],
                    row["receipt_id"],
                    json.dumps(body, sort_keys=True),
                    now,
                    now,
                    now,
                ),
            )
        return V4Result(body, 200)

    def _claim(self, prepared: PreparedUpload, key: str) -> tuple[str, Path]:
        metadata = prepared.metadata
        now = self._timestamp()
        lease_until = (datetime.fromisoformat(now) + timedelta(seconds=self.config.upload_lease_seconds)).isoformat()
        owner = f"writer-{uuid.uuid4().hex}"
        with self.store.transaction() as connection:
            scan = connection.execute(
                "SELECT * FROM scan_sessions WHERE scan_session_id=?",
                (prepared.scan_session_id,),
            ).fetchone()
            if scan is None:
                raise S0NotFoundError("SCAN_SESSION_NOT_FOUND", "unknown scan_session_id")
            if scan["device_id"] != metadata.device_id:
                raise S0ConflictError("SCAN_DEVICE_MISMATCH", "upload device does not own this scan")
            _require_scan_accepts(scan, metadata.sequence)
            prior = connection.execute(
                "SELECT * FROM spread_upload_attempts WHERE scan_session_id=? AND idempotency_key=?",
                (prepared.scan_session_id, key),
            ).fetchone()
            excluded_upload_id = ""
            if prior is not None:
                if prior["request_sha256"] != prepared.upload_digest:
                    raise S0ConflictError(
                        "IDEMPOTENCY_KEY_REUSED",
                        "Idempotency-Key was reused with different content",
                    )
                excluded_upload_id = str(prior["upload_id"])
                if prior["status"] == "receiving" and not _lease_expired(prior["lease_until"]):
                    raise V4CapacityError(
                        "UPLOAD_IN_PROGRESS",
                        "the same upload is currently in progress",
                    )
                if prior["status"] not in {"receiving", "abandoned"}:
                    raise V4CapacityError(
                        "UPLOAD_STATE_CHANGED",
                        "upload state changed while the request was being claimed",
                    )
            active_position = connection.execute(
                """
                SELECT upload_id FROM spread_upload_attempts
                 WHERE scan_session_id=? AND sequence=?
                   AND status IN ('receiving','promoted') AND upload_id<>?
                """,
                (prepared.scan_session_id, metadata.sequence, excluded_upload_id),
            ).fetchone()
            if active_position is not None:
                raise V4CapacityError(
                    "UPLOAD_IN_PROGRESS",
                    "another upload for this logical sequence is in progress",
                )
            active_artifact = connection.execute(
                """
                SELECT upload_id FROM spread_upload_attempts
                 WHERE artifact_id=? AND status IN ('receiving','promoted') AND upload_id<>?
                """,
                (metadata.artifact_id, excluded_upload_id),
            ).fetchone()
            if active_artifact is not None:
                raise V4CapacityError(
                    "UPLOAD_IN_PROGRESS",
                    "another upload for this artifact is in progress",
                )
            active = int(
                connection.execute(
                    "SELECT COUNT(*) FROM spread_upload_attempts "
                    "WHERE status='receiving' AND upload_id<>?",
                    (excluded_upload_id,),
                ).fetchone()[0]
            )
            if active >= self.config.max_concurrent_upload_writers:
                raise V4CapacityError("UPLOAD_CAPACITY_BUSY", "upload writer capacity is busy")
            reserved = int(
                connection.execute(
                    "SELECT COALESCE(SUM(declared_total_bytes), 0) FROM spread_upload_attempts "
                    "WHERE status='receiving' AND upload_id<>?",
                    (excluded_upload_id,),
                ).fetchone()[0]
            )
            if reserved + metadata.total_file_bytes > self.config.max_staging_bytes:
                raise V4CapacityError("UPLOAD_STORAGE_QUOTA", "upload staging quota is exhausted", http_status=507)
            received = int(
                connection.execute(
                    """
                    SELECT COALESCE(SUM(bundle_bytes), 0)
                      FROM (
                        SELECT MAX(declared_total_bytes) AS bundle_bytes
                          FROM spread_upload_attempts
                         WHERE status IN ('promoted','accepted','rejected')
                           AND bundle_relative_path IS NOT NULL
                         GROUP BY bundle_relative_path
                      )
                    """
                ).fetchone()[0]
            )
            if received + metadata.total_file_bytes > self.config.max_received_bytes:
                raise V4CapacityError("UPLOAD_STORAGE_QUOTA", "upload receive quota is exhausted", http_status=507)
            if prior is not None:
                upload_id = str(prior["upload_id"])
                staging_name = f"{upload_id}.partial"
                connection.execute(
                    """
                    UPDATE spread_upload_attempts
                       SET status='receiving', attempt_count=attempt_count+1,
                           lease_owner=?, lease_until=?, staging_relative_path=?,
                           bundle_relative_path=NULL, received_file_count=0, received_total_bytes=0,
                           response_http_status=NULL, response_json=NULL, completed_at=NULL,
                           error_code=NULL, error_detail=NULL, updated_at=?
                     WHERE upload_id=?
                    """,
                    (owner, lease_until, staging_name, now, upload_id),
                )
            else:
                upload_id = f"upload-{uuid.uuid4().hex}"
                staging_name = f"{upload_id}.partial"
                connection.execute(
                    """
                    INSERT INTO spread_upload_attempts(
                        upload_id, scan_session_id, device_id, sequence, idempotency_key,
                        request_sha256, artifact_id, spread_id, source_frame_id, manifest_sha256,
                        declared_file_count, declared_total_bytes, status, attempt_count,
                        lease_owner, lease_until, staging_relative_path, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'receiving', 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        upload_id,
                        prepared.scan_session_id,
                        metadata.device_id,
                        metadata.sequence,
                        key,
                        prepared.upload_digest,
                        metadata.artifact_id,
                        metadata.spread_id,
                        metadata.source_frame_id,
                        metadata.manifest_sha256,
                        metadata.file_count,
                        metadata.total_file_bytes,
                        owner,
                        lease_until,
                        staging_name,
                        now,
                        now,
                    ),
                )
        staging = self.config.staging_root / staging_name
        try:
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=False)
        except OSError as exc:
            error = S0TemporaryError(
                "UPLOAD_STORAGE_TEMPORARY",
                "temporary upload staging allocation failure",
            )
            self._abandon_receiving(upload_id, staging, error)
            raise error from exc
        return upload_id, staging

    def _write_staging(
        self,
        staging: Path,
        prepared: PreparedUpload,
        files: Iterable[tuple[str, BinaryIO]],
    ) -> None:
        manifest_path = staging / "manifest.json"
        with manifest_path.open("xb") as handle:
            handle.write(prepared.manifest_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        expected = {item.path: item for item in prepared.files}
        seen: set[str] = set()
        actual_total = 0
        for raw_path, stream in files:
            normalized = safe_relative_path(raw_path, self.config).as_posix()
            declaration = expected.get(normalized)
            if declaration is None or normalized in seen:
                raise V4BundleRejectedError(
                    "BUNDLE_INVENTORY_MISMATCH",
                    "multipart files differ from manifest inventory",
                    {"path": normalized},
                )
            target = staging.joinpath(*normalized.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            actual = self._write_file(target, stream, declaration)
            actual_total += actual
            if actual_total > self.config.max_bundle_bytes:
                raise V4BundleRejectedError("BUNDLE_BYTE_LIMIT", "bundle exceeds configured byte limit")
            seen.add(normalized)
        missing = sorted(set(expected) - seen)
        if missing:
            raise V4BundleRejectedError(
                "BUNDLE_INVENTORY_MISMATCH",
                "multipart files differ from manifest inventory",
                {"missing": missing},
            )
        if actual_total != prepared.metadata.total_file_bytes:
            raise V4BundleRejectedError("BUNDLE_BYTE_COUNT_MISMATCH", "actual bundle byte total differs")
        _fsync_directory(staging)

    @staticmethod
    def _write_file(target: Path, stream: BinaryIO, declaration: FileDeclaration) -> int:
        digest = hashlib.sha256()
        total = 0
        with target.open("xb") as handle:
            while True:
                chunk = stream.read(1 << 20)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise V4BundleRejectedError("BUNDLE_FILE_INVALID", "bundle file stream returned non-bytes")
                total += len(chunk)
                if total > declaration.size_bytes:
                    raise V4BundleRejectedError(
                        "BUNDLE_FILE_HASH_MISMATCH",
                        "bundle file size differs from manifest",
                        {"path": declaration.path},
                    )
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if total != declaration.size_bytes or digest.hexdigest() != declaration.sha256:
            raise V4BundleRejectedError(
                "BUNDLE_FILE_HASH_MISMATCH",
                "bundle file size or hash differs from manifest",
                {"path": declaration.path},
            )
        return total

    def _promote(self, upload_id: str, staging: Path) -> str:
        relative = Path("v4") / upload_id
        final = self.config.received_root / relative
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            raise S0ConflictError("UPLOAD_STORAGE_COLLISION", "upload final storage key already exists")
        os.replace(staging, final)
        _fsync_directory(final.parent)
        return relative.as_posix()

    def _handoff(
        self,
        upload_id: str,
        prepared: PreparedUpload,
        bundle_key: str,
        *,
        http_status: int,
        replayed: bool = False,
    ) -> V4Result:
        try:
            receipt = self.s1.accept_verified_spread(
                VerifiedSpreadInput(
                    scan_session_id=prepared.scan_session_id,
                    sequence=prepared.metadata.sequence,
                    artifact_id=prepared.metadata.artifact_id,
                    spread_id=prepared.metadata.spread_id,
                    source_frame_id=prepared.metadata.source_frame_id,
                    bundle_storage_key=bundle_key,
                    manifest_sha256=prepared.metadata.manifest_sha256,
                )
            )
        except S0Error as exc:
            if not exc.retryable:
                self._store_terminal_error(upload_id, exc)
            raise
        accepted_at = self._timestamp()
        body = _success_body(prepared, receipt.receipt_id, accepted_at, receipt.status.value)
        with self.store.transaction() as connection:
            connection.execute(
                """
                UPDATE spread_upload_attempts
                   SET status='accepted', s1_receipt_id=?, response_http_status=?, response_json=?,
                       lease_owner=NULL, lease_until=NULL, completed_at=?, updated_at=?,
                       error_code=NULL, error_detail=NULL
                 WHERE upload_id=?
                """,
                (
                    receipt.receipt_id,
                    http_status,
                    json.dumps(body, sort_keys=True),
                    accepted_at,
                    accepted_at,
                    upload_id,
                ),
            )
        return V4Result(body, http_status, replayed=replayed)

    def _reject(self, upload_id: str, staging: Path, error: S0Error) -> None:
        _remove_tree_best_effort(staging)
        self._store_terminal_error(upload_id, error)

    def _store_terminal_error(self, upload_id: str, error: S0Error) -> None:
        now = self._timestamp()
        with self.store.transaction() as connection:
            connection.execute(
                """
                UPDATE spread_upload_attempts
                   SET status='rejected', lease_owner=NULL, lease_until=NULL,
                       response_http_status=?, response_json=?, completed_at=?, updated_at=?,
                       error_code=?, error_detail=?
                 WHERE upload_id=?
                """,
                (
                    error.http_status,
                    json.dumps(error.to_dict(), sort_keys=True),
                    now,
                    now,
                    error.code,
                    error.message,
                    upload_id,
                ),
            )

    def _abandon_receiving(self, upload_id: str, staging: Path, error: S0Error) -> None:
        _remove_tree_best_effort(staging)
        now = self._timestamp()
        with self.store.transaction() as connection:
            connection.execute(
                """
                UPDATE spread_upload_attempts
                   SET status='abandoned', lease_owner=NULL, lease_until=NULL,
                       staging_relative_path=NULL, updated_at=?, error_code=?, error_detail=?
                 WHERE upload_id=? AND status='receiving'
                """,
                (now, error.code, error.message, upload_id),
            )

    def _recover_receiving_after_restart(self) -> int:
        with self.store.readonly() as connection:
            rows = connection.execute(
                "SELECT * FROM spread_upload_attempts WHERE status='receiving' ORDER BY created_at"
            ).fetchall()
        count = 0
        for row in rows:
            upload_id = str(row["upload_id"])
            inferred_key = (Path("v4") / upload_id).as_posix()
            inferred_final = self.config.received_root / Path(inferred_key)
            if inferred_final.is_dir():
                now = self._timestamp()
                with self.store.transaction() as connection:
                    connection.execute(
                        """
                        UPDATE spread_upload_attempts
                           SET status='promoted', staging_relative_path=NULL,
                               bundle_relative_path=?, received_file_count=declared_file_count,
                               received_total_bytes=declared_total_bytes,
                               lease_owner=NULL, lease_until=NULL, updated_at=?
                         WHERE upload_id=? AND status='receiving'
                        """,
                        (inferred_key, now, upload_id),
                    )
                continue
            if not _lease_expired(row["lease_until"]):
                continue
            staging = self._staging_path(row["staging_relative_path"])
            if staging is not None and staging.exists():
                _remove_tree_best_effort(staging)
            self._abandon_receiving(
                upload_id,
                staging or self.config.staging_root / "missing",
                S0TemporaryError("UPLOAD_LEASE_EXPIRED", "upload lease expired before completion"),
            )
            count += 1
        return count

    def _staging_path(self, value: object) -> Path | None:
        if value is None:
            return None
        if not isinstance(value, str) or "/" in value or "\\" in value or not value.endswith(".partial"):
            raise S0ConflictError("UPLOAD_JOURNAL_PATH_INVALID", "stored upload staging path is invalid")
        path = (self.config.staging_root / value).resolve()
        if path.parent != self.config.staging_root.resolve():
            raise S0ConflictError("UPLOAD_JOURNAL_PATH_INVALID", "stored upload staging path escapes root")
        return path

    def _prepared_from_row(self, row: Any) -> PreparedUpload:
        bundle_key = row["bundle_relative_path"]
        if not isinstance(bundle_key, str):
            raise S0ConflictError("UPLOAD_JOURNAL_INCOMPLETE", "promoted upload has no bundle key")
        relative = safe_relative_path(bundle_key, self.config)
        manifest_path = self.config.received_root.joinpath(*relative.parts) / "manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        metadata = {
            "schema_version": 1,
            "device_id": row["device_id"],
            "sequence": int(row["sequence"]),
            "artifact_id": row["artifact_id"],
            "spread_id": row["spread_id"],
            "source_frame_id": row["source_frame_id"],
            "manifest_sha256": row["manifest_sha256"],
            "file_count": int(row["declared_file_count"]),
            "total_file_bytes": int(row["declared_total_bytes"]),
        }
        return prepare_upload(
            str(row["scan_session_id"]),
            json.dumps(metadata, separators=(",", ":")).encode("utf-8"),
            manifest_bytes,
            str(row["request_sha256"]),
            self.config,
        )


def _require_scan_accepts(scan: Any, sequence: int) -> None:
    status = scan["status"]
    if status == "open":
        return
    if status == "sealing" and sequence <= int(scan["through_sequence"]):
        return
    raise S0ConflictError(
        "SCAN_NOT_ACCEPTING_SPREADS",
        "scan session does not accept this sequence",
        {"status": status, "through_sequence": scan["through_sequence"]},
    )


def _success_body(
    prepared: PreparedUpload,
    receipt_id: str,
    accepted_at: str,
    spread_status: str,
) -> dict[str, object]:
    return {
        "status": "acked",
        "receipt_id": receipt_id,
        "scan_session_id": prepared.scan_session_id,
        "sequence": prepared.metadata.sequence,
        "artifact_id": prepared.metadata.artifact_id,
        "manifest_sha256": prepared.metadata.manifest_sha256,
        "upload_digest": prepared.upload_digest,
        "spread_status": spread_status,
        "accepted_at": accepted_at,
    }


def _lease_expired(value: object) -> bool:
    if not isinstance(value, str):
        return True
    try:
        return datetime.fromisoformat(value) <= datetime.now(timezone.utc)
    except ValueError:
        return True


def _fsync_directory(path: Path) -> None:
    flags = getattr(os, "O_RDONLY", 0)
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags | directory_flag)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _remove_tree_best_effort(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path)
    except OSError:
        # The journal no longer references the partial directory. Startup/TTL
        # orphan cleanup can reclaim it when the underlying condition clears.
        pass


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction is not None and is_junction(path))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
