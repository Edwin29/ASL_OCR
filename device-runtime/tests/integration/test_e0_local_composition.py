from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("document_parser.server.v4_upload")
werkzeug_serving = pytest.importorskip("werkzeug.serving")
Image = pytest.importorskip("PIL.Image")

from asl_device.adapters.local_controls import NullControlSource
from asl_device.adapters.local_feedback import MemoryFeedbackSink
from asl_device.delivery_domain import V4TransportError
from asl_device.events import FeedbackCode
from asl_device.local_composition import build_local_device
from asl_device.types import DeviceControl, DeviceFlowState, DeviceInputEvent, InputAction
from document_parser.server.c0_presence import DevicePresenceService
from document_parser.server.s0_http import create_app
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from document_parser.server.s1_domain import S1Config
from document_parser.server.s1_parser import ParsedFragment
from document_parser.server.s1_services import S1Pipeline
from document_parser.server.v4_domain import V4Config
from document_parser.server.v4_upload import V4UploadService


class LocalServer:
    def __init__(self, app) -> None:
        self.server = werkzeug_serving.make_server("127.0.0.1", 0, app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class FakeFragmentParser:
    def parse(self, _image_path, page_id, _document_id):
        item_id = f"{page_id}-item"
        page = {"page_id": page_id, "nodes": [], "reading_order": []}
        accessible = {
            "page_id": page_id,
            "focus_items": [
                {
                    "id": item_id,
                    "kind": "TEXT",
                    "page_id": page_id,
                    "reading_index": 0,
                    "confidence": 1.0,
                    "issues": [],
                    "source_node_ids": [item_id],
                    "problem_id": None,
                    "spans": [{"kind": "TEXT", "text": f"content {page_id}"}],
                }
            ],
        }
        return ParsedFragment(page, accessible, {"engine": "fake"}, {"schema_valid": True})


class FakeSynthesizer:
    def __call__(self, _text):
        return (b"\x00\x00" * 100, 16000, 1)


def _value(value: str):
    return SimpleNamespace(value=value)


class BundleEngine:
    def __init__(self, session_id: str, artifact_root: Path) -> None:
        self.session_id = session_id
        self.pending_artifact = _write_bundle(artifact_root / "artifact-1", session_id)
        self._emitted = False
        self.callbacks: list[str] = []
        self.closed = False

    def start(self):
        return ()

    def poll(self):
        if self._emitted:
            return ()
        self._emitted = True
        artifact = self.pending_artifact
        return (
            SimpleNamespace(
                event_type=_value("artifact_ready"),
                event_id=f"{self.session_id}-artifact-ready-1",
                session_id=self.session_id,
                artifact_id=artifact.artifact_id,
                spread_id=artifact.spread_id,
                source_frame_id=artifact.source_frame_id,
                details=(),
            ),
        )

    def delivery_queued(self, _artifact_id):
        self.callbacks.append("queued")
        return ()

    def delivery_retrying(self, _artifact_id):
        if not self.callbacks or self.callbacks[-1] != "retrying":
            self.callbacks.append("retrying")
        return ()

    def delivery_confirmed(self, _artifact_id, _receipt_id):
        self.callbacks.append("acked")
        self.pending_artifact = None
        return (SimpleNamespace(event_type=_value("delivery_confirmed")),)

    def delivery_rejected(self, _artifact_id, _reason):
        self.callbacks.append("rejected")
        self.pending_artifact = None
        return (SimpleNamespace(event_type=_value("parser_rejected")),)

    def cancel(self):
        return ()

    def close(self):
        self.closed = True


class BundleEngineFactory:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root
        self.engines: list[BundleEngine] = []

    def create(self, *, session_id: str, datapack_id: str):
        engine = BundleEngine(session_id, self.artifact_root)
        self.engines.append(engine)
        return engine


class LoseFirstResponse:
    def __init__(self, transport) -> None:
        self.transport = transport
        self.lost = False

    def upload(self, prepared):
        response = self.transport.upload(prepared)
        if not self.lost:
            self.lost = True
            raise V4TransportError("simulated response loss after durable server commit")
        return response


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bundle(root: Path, session_id: str):
    root.mkdir(parents=True)
    records = []
    pages = {}
    source = root / "source_frame.jpg"
    Image.new("RGB", (80, 60), "black").save(source, quality=90)

    def record(path: Path):
        with Image.open(path) as image:
            width, height = image.size
        value = {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha(path),
            "size_bytes": path.stat().st_size,
            "width": width,
            "height": height,
            "mime_type": "image/jpeg",
        }
        records.append(value)
        return value

    record(source)
    for side, color in (("left", "white"), ("right", "gray")):
        side_dir = root / side
        side_dir.mkdir()
        image = side_dir / "uvdoc.jpg"
        Image.new("RGB", (64, 96), color).save(image, quality=95)
        uvdoc = record(image)
        pages[side] = {
            "side": side,
            "source_frame_id": "frame-1",
            "files": {"uvdoc": uvdoc},
            "local_readiness": {"ready": True},
        }
    manifest = {
        "schema_version": "2.0",
        "artifact_id": "artifact-1",
        "session_id": session_id,
        "processing_job_id": "job-1",
        "spread_id": "spread-1",
        "source_frame_id": "frame-1",
        "files": records,
        "pages": pages,
        "local_readiness": {"ready": True, "requires_both_pages": True},
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return SimpleNamespace(
        artifact_id=_value("artifact-1"),
        spread_id=_value("spread-1"),
        source_frame_id=_value("frame-1"),
        manifest_path=str(manifest_path.resolve()),
        manifest_sha256=_sha(manifest_path),
    )


def _write_config(root: Path, origin: str) -> Path:
    (root / "secret.txt").write_text("secret", encoding="utf-8")
    (root / "connectivity.toml").write_text(
        f"""
schema_version = 1
device_id = "device-1"
server_base_url = "{origin}"
api_key_file = "secret.txt"
allow_insecure_http = true
connect_timeout_seconds = 1.0
request_timeout_seconds = 2.0
heartbeat_interval_seconds = 5.0
stale_after_seconds = 10.0
offline_after_seconds = 20.0
retry_initial_seconds = 0.01
retry_max_seconds = 0.05
retry_jitter_fraction = 0.0
""".strip(),
        encoding="utf-8",
    )
    path = root / "device.toml"
    path.write_text(
        """
schema_version = 1
connectivity_config = "connectivity.toml"
viewport_size = 20
poll_interval_ms = 5

[delivery]
outbox_db_path = "device-state/outbox.sqlite3"
artifact_root = "device-state/ready"
retry_initial_seconds = 0.01
retry_max_seconds = 0.05

[scanner]
profile = "replay"
staging_root = "device-state/staging"
ready_root = "device-state/ready"
uvdoc_runtime_path = "unused/uvdoc"
uvdoc_checkpoint_path = "unused/uvdoc.pth"
uvdoc_device = "cpu"
m1_model_dir = "unused/paddle"
m1_model_manifest = "unused/paddle.json"
replay_path = "unused/replay.mp4"

[local_io]
feedback = "jsonl"
""".strip(),
        encoding="utf-8",
    )
    return path


def _press(event_id: str) -> DeviceInputEvent:
    return DeviceInputEvent(event_id, DeviceControl.CONFIRM, InputAction.SHORT, time.monotonic())


def _step_until(application, predicate, *, attempts: int = 200) -> None:
    for _ in range(attempts):
        application.step()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("E0 local application did not reach the expected state")


def test_e0_response_loss_ack_flush_seal_and_reading_are_ordered(tmp_path: Path) -> None:
    server_store = S0Store(tmp_path / "server.sqlite3", tmp_path / "server-datapacks")
    s0 = S0ControlPlane(server_store)
    presence = DevicePresenceService(server_store)
    s1_config = S1Config.under(server_store.datapacks_root)
    pipeline = S1Pipeline(
        server_store,
        s0,
        s1_config,
        FakeFragmentParser(),
        synthesizer=FakeSynthesizer(),
        tts_manifest={"engine_id": "fake"},
    )
    v4 = V4UploadService(server_store, pipeline, V4Config.from_s1(s1_config))
    server_app = create_app(
        s0,
        "secret",
        pipeline,
        presence_service=presence,
        v4_service=v4,
    )

    with LocalServer(server_app) as server:
        config_path = _write_config(tmp_path, server.origin)
        artifact_root = tmp_path / "device-state/ready"
        factory = BundleEngineFactory(artifact_root)
        feedback = MemoryFeedbackSink()
        composition = build_local_device(
            config_path,
            scanner_factory=factory,
            controls=NullControlSource(),
            feedback=feedback,
        )
        composition.delivery.transport = LoseFirstResponse(composition.delivery.transport)
        app = composition.application
        app.start()
        _step_until(app, lambda: composition.coordinator.state is DeviceFlowState.SELECTING_DATAPACK)
        app.submit_input(_press("select-new"))
        _step_until(app, lambda: composition.coordinator.state is DeviceFlowState.SCANNING)
        assert not any(event.code is FeedbackCode.SPREAD_SENT for event in feedback.events)
        assert factory.engines[0].callbacks.count("acked") == 0
        first_spreads = pipeline.list_spreads(
            composition.coordinator.scan_session.scan_session_id.value
        )
        assert len(first_spreads) == 1
        _step_until(
            app,
            lambda: any(event.code is FeedbackCode.SPREAD_SENT for event in feedback.events),
        )

        engine = factory.engines[0]
        codes = [event.code for event in feedback.events]
        assert engine.callbacks.count("retrying") == 1
        assert engine.callbacks.count("acked") == 1
        assert codes.count(FeedbackCode.SPREAD_SENT) == 1
        spreads = pipeline.list_spreads(composition.coordinator.scan_session.scan_session_id.value)
        assert len(spreads) == 1
        assert len(spreads[0]["fragments"]) == 2
        assert FeedbackCode.FINALIZING not in codes
        assert FeedbackCode.DATAPACK_SAVED not in codes

        assert pipeline.process_next_fragment()
        assert pipeline.process_next_fragment()
        app.submit_input(_press("stop-scan"))
        _step_until(app, lambda: composition.coordinator.state is DeviceFlowState.FINALIZING_DATAPACK)
        assert not any(event.code is FeedbackCode.DATAPACK_SAVED for event in feedback.events)
        assert pipeline.process_next_finalization()
        _step_until(app, lambda: composition.coordinator.state is DeviceFlowState.READING)

        codes = [event.code for event in feedback.events]
        assert codes.count(FeedbackCode.SPREAD_SENT) == 1
        assert codes.count(FeedbackCode.FINALIZING) == 1
        assert codes.count(FeedbackCode.DATAPACK_SAVED) == 1
        assert engine.closed
        row = composition.delivery.store.list_scan(
            composition.coordinator.scan_session.scan_session_id.value
        )[0]
        assert row["attempt_count"] == 2
        assert not (artifact_root / "artifact-1").exists()
        app.stop()
