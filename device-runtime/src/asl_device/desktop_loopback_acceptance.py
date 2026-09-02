"""Desktop-only E0-B replay acceptance orchestration and evidence capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from .replay_boundary_report import E0B_SOURCE_SHA256, build_report, parse_json_lines


_SCAN_ID_RE = re.compile(r"^(scan-[0-9a-f]+)-spread-[0-9]{6}$")
_PAGE_POSITION_RE = re.compile(r"-([0-9]{8})-(L|R)$")
_EXPECTED_PAGE_POSITIONS = (
    ("00000001", "L"),
    ("00000001", "R"),
    ("00000002", "L"),
    ("00000002", "R"),
)
_REQUIRED_MODEL_PATHS = (
    "uvdoc/runtime/model.py",
    "uvdoc/checkpoint.pth",
    "paddle/page-number/inference.json",
    "paddle/page-number/inference.pdiparams",
    "paddle/page-number/inference.yml",
    "paddle/page-number-manifest.json",
)


class LoopbackAcceptanceError(RuntimeError):
    """A bounded acceptance precondition or lifecycle invariant failed."""


@dataclass(slots=True)
class LoopbackController:
    """Turn Device JSONL observations into bounded console commands."""

    selection_requested: bool = False
    confirmed_datapack_id: str | None = None
    scan_datapack_id: str | None = None
    spread_sequences: list[int] = field(default_factory=list)
    page_change_spread_ids: list[str] = field(default_factory=list)
    exhausted: Mapping[str, Any] | None = None
    seal_requested: bool = False
    saved_datapack_id: str | None = None
    saved_revision: int | None = None
    reading_document_id: str | None = None
    reading_positions: list[tuple[str, str]] = field(default_factory=list)
    navigation_index: int = 0
    reverse_verified: bool = False
    _awaiting_page_change_start: int | None = None

    def handle(self, record: Mapping[str, Any]) -> tuple[str, ...]:
        record_type = record.get("type")
        if record_type == "reading_snapshot":
            return self._handle_reading_snapshot(record)
        if record_type != "feedback":
            return ()

        code = record.get("code")
        details_value = record.get("details")
        details = details_value if isinstance(details_value, Mapping) else {}
        if self._awaiting_page_change_start is not None:
            self._verify_page_change_start(code, details)
            return ()

        if code == "speak_catalog_title" and not self.selection_requested:
            kind = details.get("kind")
            if kind != "new_datapack":
                raise LoopbackAcceptanceError(
                    "fresh loopback Server unexpectedly exposed an existing datapack"
                )
            self.selection_requested = True
            return ("confirm",)
        if code == "confirm_selection":
            self.confirmed_datapack_id = _required_text(details, "datapack_id")
        elif code == "scan_started":
            self.scan_datapack_id = _required_text(details, "datapack_id")
            if self.scan_datapack_id != self.confirmed_datapack_id:
                raise LoopbackAcceptanceError("scan_started datapack lineage mismatch")
        elif code == "spread_sent":
            sequence = _required_int(details, "sequence")
            self.spread_sequences.append(sequence)
            self._awaiting_page_change_start = sequence
        elif code == "scan_input_exhausted":
            self.exhausted = {
                "queued_count": details.get("queued_count"),
                "acked_count": details.get("acked_count"),
            }
            if self.spread_sequences != [1, 2]:
                raise LoopbackAcceptanceError(
                    f"unexpected spread sequence at EOF: {self.spread_sequences}"
                )
            if self.exhausted != {"queued_count": 2, "acked_count": 2}:
                raise LoopbackAcceptanceError(f"unexpected EOF counts: {self.exhausted}")
            if len(self.page_change_spread_ids) != 2:
                raise LoopbackAcceptanceError("page-change start diagnostics were incomplete")
            self.seal_requested = True
            return ("confirm",)
        elif code == "datapack_saved":
            self.saved_datapack_id = _required_text(details, "datapack_id")
            self.saved_revision = _required_int(details, "revision")
            if self.saved_datapack_id != self.confirmed_datapack_id or self.saved_revision != 1:
                raise LoopbackAcceptanceError("saved datapack lineage or revision mismatch")
        elif code == "reading_resumed":
            self.reading_document_id = _required_text(details, "document_id")
            if self.reading_document_id != self.confirmed_datapack_id:
                raise LoopbackAcceptanceError("reading document lineage mismatch")
        return ()

    def _verify_page_change_start(self, code: object, details: Mapping[str, Any]) -> None:
        sequence = self._awaiting_page_change_start
        if code != "identity_collection_started" or details.get("identity_role") != "page_change":
            raise LoopbackAcceptanceError(
                f"spread_sent sequence={sequence} was not followed by explicit page-change start"
            )
        spread_id = _required_text(details, "spread_id")
        if not spread_id.endswith(f"-spread-{sequence:06d}"):
            raise LoopbackAcceptanceError("page-change start spread lineage mismatch")
        if spread_id in self.page_change_spread_ids:
            raise LoopbackAcceptanceError("duplicate page-change start diagnostic")
        self.page_change_spread_ids.append(spread_id)
        self._awaiting_page_change_start = None

    def _handle_reading_snapshot(self, record: Mapping[str, Any]) -> tuple[str, ...]:
        if self.reading_document_id is None or self.saved_datapack_id is None:
            raise LoopbackAcceptanceError("reading snapshot arrived before save/read transition")
        if record.get("datapack_id") != self.confirmed_datapack_id:
            raise LoopbackAcceptanceError("reading snapshot datapack lineage mismatch")
        cursor_value = record.get("cursor")
        cursor = cursor_value if isinstance(cursor_value, Mapping) else {}
        page_id = _required_text(cursor, "page_id")
        match = _PAGE_POSITION_RE.search(page_id)
        if match is None:
            raise LoopbackAcceptanceError(f"unexpected reading page id: {page_id}")
        position = (match.group(1), match.group(2))

        if self.navigation_index < len(_EXPECTED_PAGE_POSITIONS):
            expected = _EXPECTED_PAGE_POSITIONS[self.navigation_index]
            if position != expected:
                raise LoopbackAcceptanceError(
                    f"unexpected reading position: expected {expected}, got {position}"
                )
            self.reading_positions.append(position)
            self.navigation_index += 1
            return ("up",) if self.navigation_index == 4 else ("down",)

        if not self.reverse_verified:
            if position != _EXPECTED_PAGE_POSITIONS[2]:
                raise LoopbackAcceptanceError(
                    f"reverse navigation expected {_EXPECTED_PAGE_POSITIONS[2]}, got {position}"
                )
            self.reverse_verified = True
        return ()

    @property
    def complete(self) -> bool:
        return self.reverse_verified

    def assert_complete(self) -> None:
        if self._awaiting_page_change_start is not None:
            raise LoopbackAcceptanceError("page-change start remained pending")
        if not self.selection_requested or self.scan_datapack_id is None:
            raise LoopbackAcceptanceError("new datapack scan was not started")
        if not self.seal_requested or self.saved_revision != 1:
            raise LoopbackAcceptanceError("scan was not sealed and saved at revision 1")
        if self.reading_positions != list(_EXPECTED_PAGE_POSITIONS):
            raise LoopbackAcceptanceError("four ordered reading pages were not observed")
        if not self.reverse_verified:
            raise LoopbackAcceptanceError("reverse reading navigation was not observed")


@dataclass(frozen=True, slots=True)
class PreparedInputs:
    root: Path
    video: Path
    source_report_path: Path
    source_report: dict[str, Any]
    models_root: Path
    api_key_path: Path


def validate_prepared_root(prepared_root: str | Path) -> PreparedInputs:
    root = Path(prepared_root).resolve()
    video = root / "inputs" / "scanner-replay.mp4"
    source_report_path = root / "reports" / "e0b-replay-input.json"
    models_root = root / "models"
    api_key_path = root / "secrets" / "device-api-key.txt"
    required = (video, source_report_path, api_key_path)
    missing = [str(path) for path in required if not path.is_file()]
    missing.extend(
        str(models_root / relative)
        for relative in _REQUIRED_MODEL_PATHS
        if not (models_root / relative).is_file()
    )
    if missing:
        raise LoopbackAcceptanceError(f"prepared root is incomplete: {missing}")

    source_report = _load_object(source_report_path)
    actual_sha256 = _sha256(video)
    if (
        source_report.get("status") != "passed"
        or source_report.get("sha256") != E0B_SOURCE_SHA256
        or actual_sha256 != E0B_SOURCE_SHA256
    ):
        raise LoopbackAcceptanceError(
            "prepared replay source report/video does not match the pinned E0-B source"
        )
    api_key = api_key_path.read_text(encoding="utf-8").strip()
    if not api_key or len(api_key) > 4096 or any(character in api_key for character in "\r\n"):
        raise LoopbackAcceptanceError("prepared API key file is invalid")
    return PreparedInputs(root, video, source_report_path, source_report, models_root, api_key_path)


def write_loopback_config(
    work_root: str | Path,
    prepared: PreparedInputs,
    *,
    port: int,
    device_id: str,
) -> Path:
    root = Path(work_root).resolve()
    secret_dir = root / "secrets"
    secret_dir.mkdir(parents=True, exist_ok=True)
    (root / "state" / "device" / "artifacts" / "staging").mkdir(parents=True, exist_ok=True)
    (root / "state" / "device" / "artifacts" / "ready").mkdir(parents=True, exist_ok=True)
    secret_path = secret_dir / "device-api-key.txt"
    shutil.copyfile(prepared.api_key_path, secret_path)

    connectivity_path = root / "device-connectivity.e0b.loopback.toml"
    connectivity_path.write_text(
        "\n".join(
            (
                "schema_version = 1",
                f"device_id = {_toml_string(device_id)}",
                f'server_base_url = "http://127.0.0.1:{port}"',
                'api_key_file = "secrets/device-api-key.txt"',
                "allow_insecure_http = true",
                "connect_timeout_seconds = 5.0",
                "request_timeout_seconds = 30.0",
                "heartbeat_interval_seconds = 5.0",
                "stale_after_seconds = 15.0",
                "offline_after_seconds = 30.0",
                "retry_initial_seconds = 0.25",
                "retry_max_seconds = 2.0",
                "retry_jitter_fraction = 0.0",
                "",
            )
        ),
        encoding="utf-8",
    )

    state = root / "state" / "device"
    app_path = root / "device-app.e0b.loopback.toml"
    app_path.write_text(
        "\n".join(
            (
                "schema_version = 1",
                'connectivity_config = "device-connectivity.e0b.loopback.toml"',
                "viewport_size = 10",
                "poll_interval_ms = 20",
                "",
                "[delivery]",
                f"outbox_db_path = {_toml_string(state / 'delivery.sqlite3')}",
                f"artifact_root = {_toml_string(state / 'artifacts' / 'ready')}",
                "upload_timeout_seconds = 60.0",
                "retry_initial_seconds = 0.5",
                "retry_max_seconds = 5.0",
                "",
                "[scanner]",
                'profile = "replay"',
                f"staging_root = {_toml_string(state / 'artifacts' / 'staging')}",
                f"ready_root = {_toml_string(state / 'artifacts' / 'ready')}",
                f"uvdoc_runtime_path = {_toml_string(prepared.models_root / 'uvdoc' / 'runtime')}",
                f"uvdoc_checkpoint_path = {_toml_string(prepared.models_root / 'uvdoc' / 'checkpoint.pth')}",
                'uvdoc_device = "cpu"',
                f"m1_model_dir = {_toml_string(prepared.models_root / 'paddle' / 'page-number')}",
                f"m1_model_manifest = {_toml_string(prepared.models_root / 'paddle' / 'page-number-manifest.json')}",
                f"replay_path = {_toml_string(prepared.video)}",
                "sample_interval_ms = 100",
                "opaque_identity_max_collection_ms = 30000",
                "",
                "[local_io]",
                'controls = "console"',
                'feedback = "jsonl"',
                "",
            )
        ),
        encoding="utf-8",
    )
    return app_path


def extract_server_evidence(database: str | Path, scan_session_id: str) -> dict[str, Any]:
    db = Path(database).resolve()
    connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        spreads = [
            dict(row)
            for row in connection.execute(
                """
                SELECT sequence, spread_id, source_frame_id, receipt_id, status
                FROM scan_spreads WHERE scan_session_id=? ORDER BY sequence
                """,
                (scan_session_id,),
            )
        ]
        fragments = [
            dict(row)
            for row in connection.execute(
                """
                SELECT sequence, side, page_id, status
                FROM page_fragments WHERE scan_session_id=? ORDER BY sequence, side
                """,
                (scan_session_id,),
            )
        ]
        uploads = [
            dict(row)
            for row in connection.execute(
                """
                SELECT sequence, status, attempt_count, s1_receipt_id
                FROM spread_upload_attempts
                WHERE scan_session_id=? ORDER BY sequence, created_at
                """,
                (scan_session_id,),
            )
        ]
    finally:
        connection.close()
    accepted = [row for row in uploads if row["status"] == "accepted"]
    accepted_sequences = {row["sequence"] for row in accepted}
    summary = {
        "spread_receipts": len({row["receipt_id"] for row in spreads}),
        "fragments": len(fragments),
        "duplicates": max(0, len(accepted) - len(accepted_sequences)),
    }
    return {
        "scan_session_id": scan_session_id,
        "summary": summary,
        "spreads": spreads,
        "fragments": fragments,
        "upload_attempts": uploads,
    }


def run_desktop_loopback_acceptance(
    prepared_root: str | Path,
    *,
    evidence_dir: str | Path | None = None,
    work_dir: str | Path | None = None,
    server_python: str | Path | None = None,
    device_python: str | Path | None = None,
    timeout_seconds: float = 600.0,
    idle_timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    if timeout_seconds <= 0 or idle_timeout_seconds <= 0:
        raise LoopbackAcceptanceError("acceptance timeouts must be positive")
    prepared = validate_prepared_root(prepared_root)
    repository = Path(__file__).resolve().parents[3]
    run_id = _run_id()
    server_executable = (
        Path(server_python).resolve()
        if server_python
        else repository / "document-parser" / ".venv" / "Scripts" / "python.exe"
    )
    device_executable = Path(device_python).resolve() if device_python else Path(sys.executable).resolve()
    for name, executable in (("Server", server_executable), ("Device", device_executable)):
        if not executable.is_file():
            raise LoopbackAcceptanceError(f"{name} Python environment not found: {executable}")
    child_environment = _child_environment(repository)
    _verify_python_environment(
        server_executable,
        ("document_parser", "flask"),
        environment=child_environment,
        label="Server",
    )
    _verify_python_environment(
        device_executable,
        ("asl_device", "book_scanner", "cv2", "numpy", "paddle"),
        environment=child_environment,
        label="Device",
    )
    evidence = (
        Path(evidence_dir).resolve()
        if evidence_dir is not None
        else (repository / "tmp" / "e0b-loopback-runs" / run_id / "evidence").resolve()
    )
    work = (
        Path(work_dir).resolve()
        if work_dir is not None
        else (repository / "tmp" / "e0b-loopback-runs" / run_id / "work").resolve()
    )
    if _paths_overlap(evidence, work):
        raise LoopbackAcceptanceError("work and evidence directories must not overlap")
    evidence.mkdir(parents=True, exist_ok=False)
    work.mkdir(parents=True, exist_ok=False)
    source_copy = evidence / "e0b-replay-input.json"
    shutil.copyfile(prepared.source_report_path, source_copy)

    port = _free_loopback_port()
    device_id = f"desktop-loopback-{uuid.uuid4().hex[:12]}"
    app_config = write_loopback_config(work, prepared, port=port, device_id=device_id)
    server_state = work / "state" / "server"
    server_log_path = evidence / "e0b-server.log"
    console_log_path = evidence / "e0b-replay-console.log"
    server_summary_path = evidence / "e0b-server-summary.json"
    server_evidence_path = evidence / "e0b-server-evidence.json"
    boundary_path = evidence / "e0b-replay-boundary.json"
    manifest_path = evidence / "e0b-loopback-run-manifest.json"
    controller = LoopbackController()
    records: list[dict[str, Any]] = []
    server_process: subprocess.Popen[bytes] | None = None
    device_process: subprocess.Popen[bytes] | None = None
    reader_thread: threading.Thread | None = None
    output_queue: queue.Queue[bytes | None] = queue.Queue()
    started_at = datetime.now(timezone.utc)
    failure: str | None = None
    boundary_report: dict[str, Any] | None = None
    server_evidence: dict[str, Any] | None = None

    try:
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        with server_log_path.open("wb") as server_log:
            server_process = subprocess.Popen(
                [
                    str(server_executable),
                    "-m",
                    "document_parser.server.e0b_bench_server",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--state-root",
                    str(server_state),
                    "--api-key-file",
                    str(prepared.api_key_path),
                ],
                cwd=repository,
                env=child_environment,
                stdin=subprocess.DEVNULL,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )
            _wait_for_health(port, server_process, timeout_seconds=30.0)
            device_process = subprocess.Popen(
                [str(device_executable), "-m", "asl_device", "--config", str(app_config)],
                cwd=repository,
                env=child_environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )
            assert device_process.stdout is not None
            reader_thread = threading.Thread(
                target=_read_binary_lines,
                args=(device_process.stdout, output_queue),
                name="e0b-loopback-device-output",
                daemon=True,
            )
            reader_thread.start()
            deadline = time.monotonic() + timeout_seconds
            idle_deadline = time.monotonic() + idle_timeout_seconds
            with console_log_path.open("w", encoding="utf-8", newline="\n") as console_log:
                while not controller.complete:
                    remaining = min(deadline, idle_deadline) - time.monotonic()
                    if remaining <= 0:
                        raise LoopbackAcceptanceError("loopback acceptance timed out")
                    try:
                        raw_line = output_queue.get(timeout=min(1.0, remaining))
                    except queue.Empty:
                        if device_process.poll() is not None:
                            raise LoopbackAcceptanceError(
                                f"Device process exited early with code {device_process.returncode}"
                            )
                        continue
                    if raw_line is None:
                        raise LoopbackAcceptanceError(
                            f"Device output closed early with code {device_process.poll()}"
                        )
                    idle_deadline = time.monotonic() + idle_timeout_seconds
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                    console_log.write(line + "\n")
                    console_log.flush()
                    parsed = parse_json_lines((line,))
                    if not parsed:
                        continue
                    record = parsed[0]
                    records.append(record)
                    for command in controller.handle(record):
                        _send_command(device_process, command)
            controller.assert_complete()
    except (KeyboardInterrupt, Exception) as exc:
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        _interrupt_process(device_process)
        if reader_thread is not None:
            reader_thread.join(timeout=5.0)
        _interrupt_process(server_process)

    scan_session_id: str | None = None
    try:
        scan_session_id = _scan_session_id(controller.page_change_spread_ids)
        if scan_session_id is not None and (server_state / "server.sqlite3").is_file():
            server_evidence = extract_server_evidence(server_state / "server.sqlite3", scan_session_id)
            _write_json(server_evidence_path, server_evidence)
            _write_json(server_summary_path, server_evidence["summary"])
            if failure is None and not _server_evidence_complete(server_evidence):
                failure = "LoopbackAcceptanceError: Server evidence was not fully ready/accepted"
        boundary_report = build_report(
            records,
            source_report=prepared.source_report,
            server_summary=server_evidence["summary"] if server_evidence is not None else None,
        )
        _write_json(boundary_path, boundary_report)
        if failure is None and boundary_report["status"] != "passed":
            failure = "LoopbackAcceptanceError: boundary report did not pass"
    except Exception as exc:
        if failure is None:
            failure = f"{type(exc).__name__}: {exc}"

    manifest = {
        "schema_version": 1,
        "kind": "e0b_desktop_loopback_acceptance",
        "environment": "desktop_loopback",
        "status": "passed" if failure is None else "failed",
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "repository_revision": _git_revision(repository),
        "repository_dirty": _git_dirty(repository),
        "device_id": device_id,
        "scan_session_id": scan_session_id,
        "work_dir": str(work),
        "evidence_dir": str(evidence),
        "checks": {
            "controller_complete": controller.complete,
            "explicit_page_change_starts": len(controller.page_change_spread_ids) == 2,
            "reverse_navigation": controller.reverse_verified,
            "boundary_status": boundary_report.get("status") if boundary_report else None,
            "server_summary": server_evidence.get("summary") if server_evidence else None,
            "server_rows_complete": (
                _server_evidence_complete(server_evidence)
                if server_evidence is not None
                else False
            ),
        },
        "limitations": [
            "This is single-host Desktop loopback evidence, not Laptop/Tailscale evidence.",
            "Camera, STM/HC-05, speaker, and production OCR/TTS quality were not exercised.",
        ],
        "failure": failure,
    }
    _write_json(manifest_path, manifest)
    result = {
        "status": manifest["status"],
        "evidence_dir": str(evidence),
        "work_dir": str(work),
        "scan_session_id": scan_session_id,
        "boundary_status": manifest["checks"]["boundary_status"],
        "failure": failure,
    }
    if failure is not None:
        raise LoopbackAcceptanceError(json.dumps(result, ensure_ascii=False))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared_root", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--server-python", type=Path)
    parser.add_argument("--device-python", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--idle-timeout-seconds", type=float, default=120.0)
    args = parser.parse_args(argv)
    try:
        result = run_desktop_loopback_acceptance(
            args.prepared_root,
            evidence_dir=args.evidence_dir,
            work_dir=args.work_dir,
            server_python=args.server_python,
            device_python=args.device_python,
            timeout_seconds=args.timeout_seconds,
            idle_timeout_seconds=args.idle_timeout_seconds,
        )
    except LoopbackAcceptanceError as exc:
        print(f"[E0-B.4-D] FAILED: {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


def _required_text(values: Mapping[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise LoopbackAcceptanceError(f"missing or invalid {key}")
    return value


def _required_int(values: Mapping[str, Any], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoopbackAcceptanceError(f"missing or invalid {key}")
    return value


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LoopbackAcceptanceError(f"cannot read JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise LoopbackAcceptanceError(f"JSON root must be an object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _toml_string(value: object) -> str:
    return json.dumps(str(value).replace("\\", "/"), ensure_ascii=True)


def _run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("e0b-loopback-%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _child_environment(repository: Path) -> dict[str, str]:
    environment = dict(os.environ)
    python_paths = (
        repository / "device-runtime" / "src",
        repository / "book-scanner" / "src",
        repository / "document-parser" / "src",
    )
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        [*(str(path) for path in python_paths), *((existing,) if existing else ())]
    )
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def _verify_python_environment(
    executable: Path,
    modules: tuple[str, ...],
    *,
    environment: Mapping[str, str],
    label: str,
) -> None:
    statement = ";".join(f"import {module}" for module in modules)
    try:
        result = subprocess.run(
            [str(executable), "-c", statement],
            env=dict(environment),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LoopbackAcceptanceError(f"{label} Python preflight failed") from exc
    if result.returncode != 0:
        raise LoopbackAcceptanceError(
            f"{label} Python is missing required E0-B dependencies"
        )


def _wait_for_health(
    port: int,
    process: subprocess.Popen[bytes],
    *,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://127.0.0.1:{port}/api/v1/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LoopbackAcceptanceError(
                f"Bench Server exited before health with code {process.returncode}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and payload.get("status") == "ok":
                return
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            pass
        time.sleep(0.1)
    raise LoopbackAcceptanceError("Bench Server health timed out")


def _read_binary_lines(stream: BinaryIO, destination: queue.Queue[bytes | None]) -> None:
    try:
        for line in iter(stream.readline, b""):
            destination.put(line)
    finally:
        destination.put(None)


def _send_command(process: subprocess.Popen[bytes], command: str) -> None:
    if process.stdin is None or process.poll() is not None:
        raise LoopbackAcceptanceError(f"cannot send Device command: {command}")
    process.stdin.write((command + "\n").encode("ascii"))
    process.stdin.flush()


def _interrupt_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)
        process.wait(timeout=10.0)
    except (OSError, subprocess.TimeoutExpired):
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)


def _scan_session_id(spread_ids: list[str]) -> str | None:
    scan_ids = set()
    for spread_id in spread_ids:
        match = _SCAN_ID_RE.fullmatch(spread_id)
        if match is None:
            raise LoopbackAcceptanceError(f"invalid accepted spread id: {spread_id}")
        scan_ids.add(match.group(1))
    if not scan_ids:
        return None
    if len(scan_ids) != 1:
        raise LoopbackAcceptanceError("accepted spreads crossed scan sessions")
    return scan_ids.pop()


def _server_evidence_complete(evidence: Mapping[str, Any]) -> bool:
    spreads = evidence.get("spreads")
    fragments = evidence.get("fragments")
    uploads = evidence.get("upload_attempts")
    return (
        evidence.get("summary")
        == {"spread_receipts": 2, "fragments": 4, "duplicates": 0}
        and isinstance(spreads, list)
        and len(spreads) == 2
        and all(row.get("status") == "ready" for row in spreads)
        and isinstance(fragments, list)
        and len(fragments) == 4
        and all(row.get("status") == "ready" for row in fragments)
        and isinstance(uploads, list)
        and len(uploads) == 2
        and all(
            row.get("status") == "accepted" and row.get("attempt_count") == 1
            for row in uploads
        )
    )


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_revision(repository: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _git_dirty(repository: Path) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return bool(result.stdout.strip())


if __name__ == "__main__":
    raise SystemExit(main())
