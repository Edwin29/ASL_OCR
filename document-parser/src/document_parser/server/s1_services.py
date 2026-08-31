"""Persistent Server S1 spread acceptance, parser work, and finalization orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from document_parser.server.s0_domain import (
    S0ConflictError,
    S0Error,
    S0NotFoundError,
    S0ValidationError,
)
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from document_parser.server.s1_bundle import ScannerBundleValidator
from document_parser.server.s1_assembler import IncrementalDatapackAssembler
from document_parser.server.s1_domain import (
    FragmentState,
    S1Config,
    SpreadReceipt,
    SpreadState,
    VerifiedSpreadInput,
)
from document_parser.server.s1_parser import FragmentParserPort, ParserRejectError


class S1Pipeline:
    def __init__(
        self,
        store: S0Store,
        s0: S0ControlPlane,
        config: S1Config,
        parser: FragmentParserPort,
        *,
        now: Callable[[], datetime] | None = None,
        worker_id: str | None = None,
        synthesizer: Callable[[str], tuple[bytes, int, int]] | None = None,
        tts_manifest: dict[str, object] | None = None,
    ) -> None:
        self.store = store
        self.s0 = s0
        self.config = config
        self.parser = parser
        self.synthesizer = synthesizer
        self.tts_manifest = dict(tts_manifest or {})
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.worker_id = worker_id or f"s1-{uuid.uuid4().hex}"
        for directory in (
            config.received_root,
            config.fragments_root,
            config.finalize_root,
            config.revisions_root,
        ):
            resolved = directory.resolve()
            root = store.datapacks_root.resolve()
            if resolved != root and root not in resolved.parents:
                raise S0ValidationError(
                    "S1_STORAGE_PATH_INVALID", "S1 storage roots must be inside datapacks root"
                )
            directory.mkdir(parents=True, exist_ok=True)
        self.validator = ScannerBundleValidator(config)

    def accept_verified_spread(self, spread: VerifiedSpreadInput) -> SpreadReceipt:
        bundle = self.validator.validate(spread)
        now = self._timestamp()
        receipt_id = _receipt_id(spread)
        with self.store.transaction() as connection:
            scan = connection.execute(
                "SELECT * FROM scan_sessions WHERE scan_session_id=?",
                (spread.scan_session_id,),
            ).fetchone()
            if scan is None:
                raise S0NotFoundError("SCAN_SESSION_NOT_FOUND", "unknown scan_session_id")
            if scan["status"] == "open":
                pass
            elif scan["status"] == "sealing" and spread.sequence <= int(scan["through_sequence"]):
                pass
            else:
                raise S0ConflictError(
                    "SCAN_NOT_ACCEPTING_SPREADS",
                    "scan session does not accept this sequence",
                    {"status": scan["status"], "through_sequence": scan["through_sequence"]},
                )
            existing = connection.execute(
                "SELECT * FROM scan_spreads WHERE scan_session_id=? AND sequence=?",
                (spread.scan_session_id, spread.sequence),
            ).fetchone()
            if existing is not None:
                if (
                    existing["artifact_id"] != spread.artifact_id
                    or existing["manifest_sha256"] != spread.manifest_sha256
                    or existing["bundle_relative_path"] != bundle.relative_root
                ):
                    raise S0ConflictError(
                        "SPREAD_SEQUENCE_COLLISION",
                        "sequence was already accepted with different content",
                    )
                return SpreadReceipt(
                    existing["receipt_id"],
                    spread.scan_session_id,
                    spread.sequence,
                    existing["artifact_id"],
                    SpreadState(existing["status"]),
                )
            artifact = connection.execute(
                "SELECT scan_session_id, sequence FROM scan_spreads WHERE artifact_id=?",
                (spread.artifact_id,),
            ).fetchone()
            if artifact is not None:
                raise S0ConflictError(
                    "ARTIFACT_ID_COLLISION",
                    "artifact_id was already assigned to another logical position",
                )
            connection.execute(
                """
                INSERT INTO scan_spreads(
                    scan_session_id, sequence, artifact_id, spread_id, source_frame_id,
                    manifest_sha256, bundle_relative_path, receipt_id, status,
                    received_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'received', ?, ?)
                """,
                (
                    spread.scan_session_id,
                    spread.sequence,
                    spread.artifact_id,
                    spread.spread_id,
                    spread.source_frame_id,
                    spread.manifest_sha256,
                    bundle.relative_root,
                    receipt_id,
                    now,
                    now,
                ),
            )
            for page in (bundle.left, bundle.right):
                connection.execute(
                    """
                    INSERT INTO page_fragments(
                        scan_session_id, sequence, side, page_id, image_relative_path,
                        image_sha256, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                    """,
                    (
                        spread.scan_session_id,
                        spread.sequence,
                        page.side,
                        _page_id(spread.scan_session_id, spread.sequence, page.side),
                        page.image_relative_path,
                        page.image_sha256,
                        now,
                        now,
                    ),
                )
        return SpreadReceipt(
            receipt_id,
            spread.scan_session_id,
            spread.sequence,
            spread.artifact_id,
            SpreadState.RECEIVED,
        )

    def process_next_fragment(self) -> bool:
        claim = self._claim_fragment()
        if claim is None:
            return False
        try:
            image_path = (self.config.received_root / claim["image_relative_path"]).resolve()
            _require_confined(image_path, self.config.received_root)
            if _sha256_file(image_path) != claim["image_sha256"]:
                raise ParserRejectError("FRAGMENT_IMAGE_HASH_MISMATCH", "fragment image hash changed")
            parsed = self.parser.parse(image_path, claim["page_id"], claim["datapack_id"])
            if parsed.accessible_page.get("page_id") != claim["page_id"]:
                raise ParserRejectError("FRAGMENT_PAGE_ID_MISMATCH", "parser changed the assigned page ID")
            output = (
                self.config.fragments_root
                / claim["scan_session_id"]
                / f"{int(claim['sequence']):08d}"
                / claim["side"]
            )
            page_ir_path = output / "page_ir.json"
            accessible_path = output / "accessible_page.json"
            _atomic_json(page_ir_path, parsed.page_ir)
            _atomic_json(accessible_path, parsed.accessible_page)
            self._finish_fragment(
                claim,
                FragmentState.READY,
                page_ir_path=page_ir_path,
                accessible_path=accessible_path,
                engine=parsed.engine_manifest,
                validation=parsed.validation,
            )
        except ParserRejectError as exc:
            self._finish_fragment(
                claim,
                FragmentState.REJECTED,
                error_code=exc.code,
                error_detail=str(exc),
                validation=exc.validation,
            )
        except Exception as exc:
            terminal = int(claim["attempt_count"]) >= self.config.parser_max_attempts
            self._finish_fragment(
                claim,
                FragmentState.ERROR if terminal else FragmentState.QUEUED,
                error_code="PARSER_RUNTIME_FAILED",
                error_detail=f"{type(exc).__name__}: {exc}",
            )
        return True

    def list_spreads(self, scan_session_id: str) -> tuple[dict[str, object], ...]:
        with self.store.readonly() as connection:
            scan = connection.execute(
                "SELECT 1 FROM scan_sessions WHERE scan_session_id=?", (scan_session_id,)
            ).fetchone()
            if scan is None:
                raise S0NotFoundError("SCAN_SESSION_NOT_FOUND", "unknown scan_session_id")
            rows = connection.execute(
                "SELECT * FROM scan_spreads WHERE scan_session_id=? ORDER BY sequence",
                (scan_session_id,),
            ).fetchall()
            fragments = connection.execute(
                """
                SELECT sequence, side, page_id, status, attempt_count, error_code, error_detail
                  FROM page_fragments WHERE scan_session_id=? ORDER BY sequence, side
                """,
                (scan_session_id,),
            ).fetchall()
        by_sequence: dict[int, list[dict[str, object]]] = {}
        for row in fragments:
            by_sequence.setdefault(int(row["sequence"]), []).append(dict(row))
        return tuple(
            {
                "sequence": int(row["sequence"]),
                "artifact_id": row["artifact_id"],
                "spread_id": row["spread_id"],
                "source_frame_id": row["source_frame_id"],
                "manifest_sha256": row["manifest_sha256"],
                "receipt_id": row["receipt_id"],
                "status": row["status"],
                "fragments": by_sequence.get(int(row["sequence"]), []),
                "error_code": row["error_code"],
                "error_detail": row["error_detail"],
            }
            for row in rows
        )

    def spread_counts(self, scan_session_id: str) -> dict[str, int]:
        counts = {state.value: 0 for state in SpreadState}
        with self.store.readonly() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM scan_spreads WHERE scan_session_id=? GROUP BY status",
                (scan_session_id,),
            ).fetchall()
        for row in rows:
            counts[row["status"]] = int(row["count"])
        return counts

    def request_seal(self, scan_session_id: str, through_sequence: int) -> dict[str, object]:
        self.s0.request_seal(scan_session_id, through_sequence)
        self._ensure_finalize_run(scan_session_id)
        return self.get_scan_view(scan_session_id)

    def recover_finalization_runs(self) -> int:
        with self.store.readonly() as connection:
            rows = connection.execute(
                """
                SELECT scan_session_id FROM scan_sessions
                 WHERE status='sealing' AND finalize_run_id IS NULL
                """
            ).fetchall()
        for row in rows:
            self._ensure_finalize_run(row["scan_session_id"])
        return len(rows)

    def process_next_finalization(self) -> bool:
        self.recover_finalization_runs()
        with self.store.readonly() as connection:
            runs = connection.execute(
                """
                SELECT * FROM finalize_runs
                 WHERE status IN ('waiting','assembling','validating','promoted')
                 ORDER BY CASE status
                            WHEN 'promoted' THEN 0
                            WHEN 'validating' THEN 1
                            WHEN 'assembling' THEN 2
                            ELSE 3
                          END,
                          created_at
                """
            ).fetchall()
        for row in runs:
            run = dict(row)
            if run["status"] == "promoted":
                final_relative = run.get("final_relative_path")
                manifest_hash = run.get("manifest_sha256")
                if not isinstance(final_relative, str) or not isinstance(manifest_hash, str):
                    self._fail_finalize(
                        run["finalize_run_id"],
                        "PROMOTED_JOURNAL_INVALID",
                        "promoted finalize run lacks revision path or manifest hash",
                    )
                    return True
                final = (self.store.datapacks_root / final_relative).resolve()
                _require_confined(final, self.store.datapacks_root)
                if not final.is_dir() or _sha256_file(final / "manifest.json") != manifest_hash:
                    self._fail_finalize(
                        run["finalize_run_id"],
                        "PROMOTED_REVISION_INVALID",
                        "promoted revision directory is missing or changed",
                    )
                    return True
                try:
                    if self.synthesizer is None:
                        raise S0ValidationError(
                            "S1_TTS_NOT_CONFIGURED", "S1 finalization requires a synthesizer"
                        )
                    IncrementalDatapackAssembler(
                        self.store.datapacks_root,
                        self.synthesizer,
                        self.tts_manifest,
                    ).validate(final, run["datapack_id"])
                    self._publish_revision(run["finalize_run_id"], final_relative, manifest_hash)
                except S0Error as exc:
                    self._fail_finalize(run["finalize_run_id"], exc.code, exc.message)
                except Exception as exc:
                    self._fail_finalize(
                        run["finalize_run_id"],
                        "FINALIZE_PUBLISH_FAILED",
                        f"{type(exc).__name__}: {exc}",
                    )
                return True
            if run["status"] == "waiting":
                readiness = self._finalize_readiness(run)
                if readiness == "wait":
                    continue
                if readiness == "error":
                    return True
                if int(run["through_sequence"]) == 0:
                    self._publish_noop(run)
                    return True
                now = self._timestamp()
                with self.store.transaction() as connection:
                    connection.execute(
                        "UPDATE finalize_runs SET status='assembling', updated_at=? WHERE finalize_run_id=? AND status='waiting'",
                        (now, run["finalize_run_id"]),
                    )
                run["status"] = "assembling"
            try:
                self._assemble_and_publish(run["finalize_run_id"])
            except S0Error as exc:
                self._fail_finalize(run["finalize_run_id"], exc.code, exc.message)
            except Exception as exc:
                self._fail_finalize(
                    run["finalize_run_id"],
                    "FINALIZE_ASSEMBLY_FAILED",
                    f"{type(exc).__name__}: {exc}",
                )
            return True
        return False

    def get_scan_view(self, scan_session_id: str) -> dict[str, object]:
        with self.store.readonly() as connection:
            scan = connection.execute(
                "SELECT * FROM scan_sessions WHERE scan_session_id=?",
                (scan_session_id,),
            ).fetchone()
            if scan is None:
                raise S0NotFoundError("SCAN_SESSION_NOT_FOUND", "unknown scan_session_id")
            finalize = None
            if scan["finalize_run_id"]:
                finalize = connection.execute(
                    "SELECT * FROM finalize_runs WHERE finalize_run_id=?",
                    (scan["finalize_run_id"],),
                ).fetchone()
        result: dict[str, object] = {
            "scan_session_id": scan["scan_session_id"],
            "datapack_id": scan["datapack_id"],
            "device_id": scan["device_id"],
            "base_revision": scan["base_revision"],
            "status": scan["status"],
            "through_sequence": scan["through_sequence"],
            "published_revision": scan["published_revision"],
            "revision": scan["published_revision"],
            "created_at": scan["created_at"],
            "updated_at": scan["updated_at"],
            "spread_counts": self.spread_counts(scan_session_id),
            "error_code": scan["finalize_error_code"] or scan["error_code"],
            "error_detail": scan["finalize_error_detail"] or scan["error_detail"],
        }
        result["finalization"] = (
            {
                "status": finalize["status"],
                "error_code": finalize["error_code"],
                "error_detail": finalize["error_detail"],
            }
            if finalize is not None
            else None
        )
        return result

    def _ensure_finalize_run(self, scan_session_id: str) -> str:
        now = self._timestamp()
        run_id = f"finalize-{hashlib.sha256(scan_session_id.encode('utf-8')).hexdigest()[:32]}"
        with self.store.transaction() as connection:
            scan = connection.execute(
                "SELECT * FROM scan_sessions WHERE scan_session_id=?",
                (scan_session_id,),
            ).fetchone()
            if scan is None:
                raise S0NotFoundError("SCAN_SESSION_NOT_FOUND", "unknown scan_session_id")
            if scan["status"] not in {"sealing", "sealed", "error"}:
                raise S0ConflictError("SCAN_NOT_SEALING", "scan session has no seal intent")
            existing = connection.execute(
                "SELECT finalize_run_id FROM finalize_runs WHERE scan_session_id=?",
                (scan_session_id,),
            ).fetchone()
            if existing is not None:
                return existing["finalize_run_id"]
            cutoff = int(scan["through_sequence"])
            base = scan["base_revision"]
            target = int(base) if cutoff == 0 and base is not None else (int(base) + 1 if base is not None else 1)
            connection.execute(
                """
                INSERT INTO finalize_runs(
                    finalize_run_id, scan_session_id, datapack_id, base_revision,
                    target_revision, through_sequence, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?, ?)
                """,
                (run_id, scan_session_id, scan["datapack_id"], base, target, cutoff, now, now),
            )
            connection.execute(
                """
                UPDATE scan_sessions SET finalize_run_id=?, finalize_started_at=?, updated_at=?
                 WHERE scan_session_id=?
                """,
                (run_id, now, now, scan_session_id),
            )
        return run_id

    def _finalize_readiness(self, run: dict[str, Any]) -> str:
        cutoff = int(run["through_sequence"])
        if cutoff == 0:
            if run["base_revision"] is None:
                self._fail_finalize(run["finalize_run_id"], "EMPTY_DRAFT_SCAN", "new draft has no spreads")
                return "error"
            return "ready"
        with self.store.readonly() as connection:
            rows = connection.execute(
                """
                SELECT sequence, status FROM scan_spreads
                 WHERE scan_session_id=? AND sequence <= ? ORDER BY sequence
                """,
                (run["scan_session_id"], cutoff),
            ).fetchall()
            beyond = connection.execute(
                "SELECT COUNT(*) FROM scan_spreads WHERE scan_session_id=? AND sequence > ?",
                (run["scan_session_id"], cutoff),
            ).fetchone()[0]
        if beyond:
            self._fail_finalize(run["finalize_run_id"], "SPREAD_AFTER_CUTOFF", "spread exists after cutoff")
            return "error"
        sequences = [int(row["sequence"]) for row in rows]
        if sequences != list(range(1, cutoff + 1)):
            return "wait"
        statuses = {row["status"] for row in rows}
        if statuses & {"rejected", "error"}:
            self._fail_finalize(
                run["finalize_run_id"],
                "FRAGMENT_TERMINAL_FAILURE",
                "one or more spread fragments failed",
            )
            return "error"
        return "ready" if statuses == {"ready"} else "wait"

    def _assemble_and_publish(self, finalize_run_id: str) -> None:
        with self.store.readonly() as connection:
            run_row = connection.execute(
                "SELECT * FROM finalize_runs WHERE finalize_run_id=?", (finalize_run_id,)
            ).fetchone()
            if run_row is None:
                raise S0NotFoundError("FINALIZE_RUN_NOT_FOUND", "unknown finalize run")
            run = dict(run_row)
            datapack = connection.execute(
                "SELECT * FROM datapacks WHERE datapack_id=?", (run["datapack_id"],)
            ).fetchone()
            if datapack is None:
                raise S0NotFoundError("DATAPACK_NOT_FOUND", "unknown datapack")
            fragments = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM page_fragments
                     WHERE scan_session_id=? AND sequence <= ? AND status='ready'
                     ORDER BY sequence, CASE side WHEN 'left' THEN 0 ELSE 1 END
                    """,
                    (run["scan_session_id"], run["through_sequence"]),
                ).fetchall()
            ]
            base_revision = run["base_revision"]
            base_row = None
            if base_revision is not None:
                base_row = connection.execute(
                    "SELECT * FROM datapack_revisions WHERE datapack_id=? AND revision=?",
                    (run["datapack_id"], base_revision),
                ).fetchone()
        if datapack["current_revision"] != base_revision:
            raise S0ConflictError("BASE_REVISION_CHANGED", "datapack current revision changed")
        if len(fragments) != int(run["through_sequence"]) * 2:
            raise S0ConflictError("FRAGMENT_COUNT_MISMATCH", "finalize fragment count is incomplete")
        if self.synthesizer is None:
            raise S0ValidationError("S1_TTS_NOT_CONFIGURED", "S1 finalization requires a synthesizer")
        base_root = None
        if base_row is not None:
            base_root = self.store.datapacks_root / base_row["root_relative_path"]
        attempt = self.config.finalize_root / f"{finalize_run_id}.attempt-{uuid.uuid4().hex}"
        assembler = IncrementalDatapackAssembler(
            self.store.datapacks_root, self.synthesizer, self.tts_manifest
        )
        manifest_hash = assembler.assemble(
            attempt,
            datapack_id=run["datapack_id"],
            title=datapack["title"],
            base_revision=base_revision,
            target_revision=int(run["target_revision"]),
            base_root=base_root,
            fragments=fragments,
            scan_session_id=run["scan_session_id"],
            through_sequence=int(run["through_sequence"]),
            created_at=run["created_at"],
        )
        final = (
            self.config.revisions_root
            / datapack["storage_key"]
            / f"r{int(run['target_revision']):08d}"
        )
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            existing_hash = _sha256_file(final / "manifest.json")
            if existing_hash != manifest_hash:
                raise S0ConflictError("REVISION_STORAGE_COLLISION", "target revision path has another hash")
            assembler.validate(final, run["datapack_id"])
            _safe_rmtree(attempt, self.config.finalize_root)
        else:
            os.replace(attempt, final)
        final_relative = self._storage_relative(final)
        now = self._timestamp()
        with self.store.transaction() as connection:
            connection.execute(
                """
                UPDATE finalize_runs
                   SET status='promoted', final_relative_path=?, manifest_sha256=?, updated_at=?
                 WHERE finalize_run_id=?
                """,
                (final_relative, manifest_hash, now, finalize_run_id),
            )
        self._publish_revision(finalize_run_id, final_relative, manifest_hash)

    def _publish_revision(self, finalize_run_id: str, final_relative: str, manifest_hash: str) -> None:
        now = self._timestamp()
        with self.store.transaction() as connection:
            run = connection.execute(
                "SELECT * FROM finalize_runs WHERE finalize_run_id=?", (finalize_run_id,)
            ).fetchone()
            datapack = connection.execute(
                "SELECT * FROM datapacks WHERE datapack_id=?", (run["datapack_id"],)
            ).fetchone()
            if datapack["current_revision"] != run["base_revision"]:
                raise S0ConflictError("BASE_REVISION_CHANGED", "datapack current revision changed")
            target = int(run["target_revision"])
            existing = connection.execute(
                "SELECT * FROM datapack_revisions WHERE datapack_id=? AND revision=?",
                (run["datapack_id"], target),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO datapack_revisions(
                        datapack_id, revision, status, root_relative_path,
                        manifest_sha256, created_at, published_at
                    ) VALUES (?, ?, 'ready', ?, ?, ?, ?)
                    """,
                    (run["datapack_id"], target, final_relative, manifest_hash, now, now),
                )
            elif existing["manifest_sha256"] != manifest_hash or existing["root_relative_path"] != final_relative:
                raise S0ConflictError("REVISION_ROW_COLLISION", "target revision row has another identity")
            if run["base_revision"] is not None and int(run["base_revision"]) != target:
                connection.execute(
                    "UPDATE datapack_revisions SET status='superseded' WHERE datapack_id=? AND revision=?",
                    (run["datapack_id"], run["base_revision"]),
                )
            connection.execute(
                """
                UPDATE datapacks SET status='ready', current_revision=?, updated_at=?,
                       error_code=NULL, error_detail=NULL WHERE datapack_id=?
                """,
                (target, now, run["datapack_id"]),
            )
            connection.execute(
                """
                UPDATE scan_sessions SET status='sealed', published_revision=?,
                       finalize_completed_at=?, updated_at=?, finalize_error_code=NULL,
                       finalize_error_detail=NULL WHERE scan_session_id=?
                """,
                (target, now, now, run["scan_session_id"]),
            )
            connection.execute(
                """
                UPDATE finalize_runs SET status='published', final_relative_path=?,
                       manifest_sha256=?, updated_at=?, published_at=?, error_code=NULL,
                       error_detail=NULL WHERE finalize_run_id=?
                """,
                (final_relative, manifest_hash, now, now, finalize_run_id),
            )
        self.s0.invalidate_datapack_cache(run["datapack_id"])

    def _publish_noop(self, run: dict[str, Any]) -> None:
        now = self._timestamp()
        base = int(run["base_revision"])
        with self.store.transaction() as connection:
            datapack = connection.execute(
                "SELECT current_revision FROM datapacks WHERE datapack_id=?", (run["datapack_id"],)
            ).fetchone()
            if datapack is None or datapack["current_revision"] != base:
                raise S0ConflictError("BASE_REVISION_CHANGED", "datapack current revision changed")
            connection.execute(
                "UPDATE datapacks SET status='ready', updated_at=? WHERE datapack_id=?",
                (now, run["datapack_id"]),
            )
            connection.execute(
                """
                UPDATE scan_sessions SET status='sealed', published_revision=?,
                       finalize_completed_at=?, updated_at=? WHERE scan_session_id=?
                """,
                (base, now, now, run["scan_session_id"]),
            )
            connection.execute(
                """
                UPDATE finalize_runs SET status='published', published_at=?, updated_at=?
                 WHERE finalize_run_id=?
                """,
                (now, now, run["finalize_run_id"]),
            )

    def _fail_finalize(self, finalize_run_id: str, code: str, detail: str) -> None:
        now = self._timestamp()
        with self.store.transaction() as connection:
            run = connection.execute(
                "SELECT * FROM finalize_runs WHERE finalize_run_id=?", (finalize_run_id,)
            ).fetchone()
            if run is None or run["status"] in {"published", "error"}:
                return
            connection.execute(
                """
                UPDATE finalize_runs SET status='error', updated_at=?, error_code=?, error_detail=?
                 WHERE finalize_run_id=?
                """,
                (now, code, detail, finalize_run_id),
            )
            connection.execute(
                """
                UPDATE scan_sessions SET status='error', updated_at=?, finalize_completed_at=?,
                       finalize_error_code=?, finalize_error_detail=? WHERE scan_session_id=?
                """,
                (now, now, code, detail, run["scan_session_id"]),
            )
            desired = "draft" if run["base_revision"] is None else "ready"
            connection.execute(
                """
                UPDATE datapacks SET status=?, updated_at=?
                 WHERE datapack_id=? AND current_revision IS ?
                """,
                (desired, now, run["datapack_id"], run["base_revision"]),
            )

    def _claim_fragment(self) -> dict[str, Any] | None:
        now_dt = self._now().astimezone(timezone.utc)
        now = now_dt.isoformat(timespec="microseconds")
        lease_until = (now_dt + timedelta(seconds=self.config.lease_seconds)).isoformat(
            timespec="microseconds"
        )
        with self.store.transaction() as connection:
            expired = connection.execute(
                """
                SELECT scan_session_id, sequence, side, attempt_count
                  FROM page_fragments
                 WHERE status='processing' AND lease_until < ?
                """,
                (now,),
            ).fetchall()
            for row in expired:
                terminal = int(row["attempt_count"]) >= self.config.parser_max_attempts
                connection.execute(
                    """
                    UPDATE page_fragments
                       SET status=?, lease_owner=NULL, lease_until=NULL, updated_at=?,
                           terminal_at=CASE WHEN ?='error' THEN ? ELSE NULL END,
                           error_code=CASE WHEN ?='error' THEN 'PARSER_LEASE_EXHAUSTED' ELSE error_code END
                     WHERE scan_session_id=? AND sequence=? AND side=? AND status='processing'
                    """,
                    (
                        "error" if terminal else "queued",
                        now,
                        "error" if terminal else "queued",
                        now,
                        "error" if terminal else "queued",
                        row["scan_session_id"],
                        row["sequence"],
                        row["side"],
                    ),
                )
                self._refresh_spread(connection, row["scan_session_id"], row["sequence"], now)
            row = connection.execute(
                """
                SELECT pf.*, ss.datapack_id
                  FROM page_fragments pf
                  JOIN scan_sessions ss ON ss.scan_session_id=pf.scan_session_id
                 WHERE pf.status='queued'
                 ORDER BY pf.created_at, pf.sequence, pf.side
                 LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE page_fragments
                   SET status='processing', attempt_count=attempt_count+1,
                       lease_owner=?, lease_until=?, updated_at=?
                 WHERE scan_session_id=? AND sequence=? AND side=? AND status='queued'
                """,
                (
                    self.worker_id,
                    lease_until,
                    now,
                    row["scan_session_id"],
                    row["sequence"],
                    row["side"],
                ),
            )
            self._refresh_spread(connection, row["scan_session_id"], row["sequence"], now)
            claimed = dict(row)
            claimed["attempt_count"] = int(row["attempt_count"]) + 1
            claimed["lease_owner"] = self.worker_id
            return claimed

    def _finish_fragment(
        self,
        claim: dict[str, Any],
        status: FragmentState,
        *,
        page_ir_path: Path | None = None,
        accessible_path: Path | None = None,
        engine: dict[str, object] | None = None,
        validation: dict[str, object] | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        now = self._timestamp()
        terminal = status in {FragmentState.READY, FragmentState.REJECTED, FragmentState.ERROR}
        with self.store.transaction() as connection:
            result = connection.execute(
                """
                UPDATE page_fragments
                   SET status=?, page_ir_relative_path=?, accessible_page_relative_path=?,
                       parser_engine_json=?, validation_json=?, lease_owner=NULL, lease_until=NULL,
                       updated_at=?, terminal_at=?, error_code=?, error_detail=?
                 WHERE scan_session_id=? AND sequence=? AND side=?
                   AND status='processing' AND lease_owner=?
                """,
                (
                    status.value,
                    self._storage_relative(page_ir_path) if page_ir_path else None,
                    self._storage_relative(accessible_path) if accessible_path else None,
                    _canonical_json(engine) if engine is not None else None,
                    _canonical_json(validation) if validation is not None else None,
                    now,
                    now if terminal else None,
                    error_code,
                    error_detail,
                    claim["scan_session_id"],
                    claim["sequence"],
                    claim["side"],
                    self.worker_id,
                ),
            )
            if result.rowcount != 1:
                raise S0ConflictError("FRAGMENT_LEASE_LOST", "parser fragment lease is no longer owned")
            self._refresh_spread(connection, claim["scan_session_id"], claim["sequence"], now)

    def _refresh_spread(self, connection, scan_session_id: str, sequence: int, now: str) -> None:
        rows = connection.execute(
            "SELECT status, error_code, error_detail FROM page_fragments WHERE scan_session_id=? AND sequence=?",
            (scan_session_id, sequence),
        ).fetchall()
        statuses = {row["status"] for row in rows}
        if len(rows) != 2:
            status = "error"
        elif "rejected" in statuses:
            status = "rejected"
        elif "error" in statuses:
            status = "error"
        elif statuses == {"ready"}:
            status = "ready"
        elif "processing" in statuses:
            status = "processing"
        else:
            status = "received"
        error = next((row for row in rows if row["error_code"]), None)
        connection.execute(
            """
            UPDATE scan_spreads SET status=?, updated_at=?, error_code=?, error_detail=?
             WHERE scan_session_id=? AND sequence=?
            """,
            (
                status,
                now,
                error["error_code"] if error else None,
                error["error_detail"] if error else None,
                scan_session_id,
                sequence,
            ),
        )

    def _storage_relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.store.datapacks_root).as_posix()
        except ValueError as exc:
            raise S0ValidationError("S1_STORAGE_PATH_INVALID", "S1 output escapes datapacks root") from exc

    def _timestamp(self) -> str:
        return self._now().astimezone(timezone.utc).isoformat(timespec="microseconds")


def _page_id(scan_session_id: str, sequence: int, side: str) -> str:
    prefix = hashlib.sha256(scan_session_id.encode("utf-8")).hexdigest()[:12]
    suffix = "L" if side == "left" else "R"
    return f"pg-{prefix}-{sequence:08d}-{suffix}"


def _receipt_id(spread: VerifiedSpreadInput) -> str:
    digest = hashlib.sha256(
        f"{spread.scan_session_id}\0{spread.sequence}\0{spread.artifact_id}\0{spread.manifest_sha256}".encode(
            "utf-8"
        )
    ).hexdigest()[:32]
    return f"spread-receipt-{digest}"


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _require_confined(path: Path, root: Path) -> None:
    root = root.resolve()
    if path != root and root not in path.parents:
        raise S0ValidationError("S1_STORAGE_PATH_INVALID", "storage path escapes configured root")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_rmtree(path: Path, root: Path) -> None:
    resolved = path.resolve()
    root = root.resolve()
    if resolved == root or root not in resolved.parents:
        raise S0ValidationError("S1_STORAGE_PATH_INVALID", "refusing to remove path outside finalize root")
    shutil.rmtree(resolved)
