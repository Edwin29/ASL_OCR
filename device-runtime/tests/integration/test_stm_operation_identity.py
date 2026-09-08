"""STM boot identity through the real persistent S0 receipt/progress boundary."""

from pathlib import Path

from asl_device.adapters.stm_serial import StmSerialControlSource
from asl_device.hold_repeat import HoldRepeatController
from asl_device.local_composition import build_local_device
from document_parser.datapack.ingest import build_datapack
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl
from document_parser.server.s0_domain import require_id
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from tests.integration.test_e0_local_composition import (
    BundleEngineFactory, FakeSynthesizer, _write_config,
)
from tests.unit.test_stm_serial import FakeSerial, _config, _next_events


def _events(namespace):
    serial = FakeSerial((b"HELLO,3\n", b"NAV,C,S,2\n", b"NAV,D,A,3\n"))
    source = StmSerialControlSource(
        _config(), event_namespace=namespace, serial_factory=lambda _config: serial,
    )
    try:
        return _next_events(source, 2)
    finally:
        source.close()


def _write_reading_fixture(root: Path):
    paths = [root / f"book-p{index:03d}.png" for index in range(1, 4)]

    class FixtureAdapter:
        engine_id = "stabilization-fixture"
        engine_version = "1"

        def parse_page(self, path):
            return {
                "width": 100, "height": 100,
                "parsing_res_list": [{
                    "block_label": "text", "block_content": ("first item", "second item", "third item")[paths.index(Path(path))],
                    "block_bbox": [0, 0, 90, 90], "block_id": 1, "block_order": 1,
                }],
            }

    page_ir = build_document_ir_from_vl(paths, adapter=FixtureAdapter(), book_id="book")
    build_datapack(
        book_id="book", title="book", page_ir=page_ir,
        synthesize=FakeSynthesizer(), tts_manifest={}, output_dir=root,
        system_dir=root / "_system", log_fn=lambda _message: None,
    )


def test_stm_boots_create_new_datapacks_and_resume_cursor_with_fresh_down(tmp_path):
    root = tmp_path / "datapacks"
    root.mkdir()
    _write_reading_fixture(root)
    first = S0ControlPlane(S0Store(tmp_path / "state.sqlite3", root))
    first.bootstrap_existing_datapacks()
    select_a, down_a = _events("boot-a")
    select_b, down_b = _events("boot-b")
    created_a = first.create_datapack("stable-device", select_a.event_id + ":create")
    assert first.create_datapack("stable-device", select_a.event_id + ":create") == created_a
    opened = first.open_reading("stable-device", "book", 10, select_a.event_id + ":reading-open")
    moved = first.send_reading_command(opened["reading_session_id"], down_a.event_id, "DOWN", "SHORT")
    second = S0ControlPlane(S0Store(tmp_path / "state.sqlite3", root))
    created_b = second.create_datapack("stable-device", select_b.event_id + ":create")
    assert created_b.datapack_id != created_a.datapack_id
    resumed = second.open_reading("stable-device", "book", 10, select_b.event_id + ":reading-open")
    assert resumed["reading_session_id"] == opened["reading_session_id"]
    assert resumed["cursor"] == moved["cursor"]
    fresh = second.send_reading_command(resumed["reading_session_id"], down_b.event_id, "DOWN", "SHORT")
    assert fresh["cursor"]["page_index"] == moved["cursor"]["page_index"] + 1
    assert fresh["cursor"]["generation"] == moved["cursor"]["generation"] + 1
    assert second.send_reading_command(resumed["reading_session_id"], down_b.event_id, "DOWN", "SHORT") == fresh


def test_stm_namespace_suffixes_and_hold_fit_server_ids():
    select, down = _events("b" * 80)
    for suffix in (":create", ":scan-open", ":reading-open"):
        require_id("operation_id", select.event_id + suffix)
    hold = HoldRepeatController(monotonic=lambda: 0.0)
    # Check the actual host-generated command ID, including its hold suffix.
    command = hold.apply_edge(down)[0]
    require_id("command_id", command.event_id)


def test_local_stm_composition_uses_c0_boot_namespace(tmp_path, monkeypatch):
    config = _write_config(tmp_path, "http://127.0.0.1:1")
    config.write_text(config.read_text().replace("viewport_size = 20", "viewport_size = 10")
                      + '\ncontrols = "stm_serial"\n\n[local_io.stm_serial]\nport = "COM5"\n')
    captured = []

    def source(config, *, event_namespace):
        captured.append(event_namespace)
        return StmSerialControlSource(config, event_namespace=event_namespace)

    monkeypatch.setattr("asl_device.local_composition.StmSerialControlSource", source)
    composition = build_local_device(config, scanner_factory=BundleEngineFactory(tmp_path / "ready"))
    assert captured == [composition.coordinator.connectivity.boot_id]
    composition.application.stop()
