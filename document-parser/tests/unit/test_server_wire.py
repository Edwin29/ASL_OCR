import tempfile
import unittest
from pathlib import Path

from document_parser.accessibility.domain.commands import NavigationCommand
from document_parser.accessibility.domain.navigation_state import NavigationState
from document_parser.datapack.ingest import build_datapack
from document_parser.datapack.loader import load_datapack
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl
from document_parser.server.session import DatapackSession
from document_parser.server.wire import (
    audio_to_wire,
    command_from_wire,
    handle_wire_command,
    result_to_wire,
    state_to_wire,
)


class FakeSynthesizer:
    def __call__(self, text):
        return (b"\x00\x00" * 100, 16000, 1)


class FixtureVlAdapter:
    engine_id = "fixture-paddleocr-vl"
    engine_version = "0.0.0"

    def __init__(self, result_by_path):
        self.result_by_path = result_by_path

    def parse_page(self, image_path):
        return self.result_by_path[str(Path(image_path).resolve())]


def build_and_load_datapack(tmp_root: Path, book_id="wire-book"):
    image_path = tmp_root / f"{book_id}.png"
    image_path.write_bytes(b"fake-png")
    blocks = [{
        "block_label": "text", "block_content": "안녕하세요",
        "block_bbox": [100, 100, 900, 160], "block_id": 1, "block_order": 1,
    }]
    adapter = FixtureVlAdapter({str(image_path.resolve()): {"width": 2434, "height": 3071, "parsing_res_list": blocks}})
    page_ir = build_document_ir_from_vl([image_path], adapter=adapter, book_id=book_id)

    output_dir = tmp_root / "datapacks"
    system_dir = output_dir / "_system"
    build_datapack(
        book_id=book_id, title="제목", page_ir=page_ir, synthesize=FakeSynthesizer(),
        tts_manifest={}, output_dir=output_dir, system_dir=system_dir, log_fn=lambda msg: None,
    )
    return load_datapack(output_dir / book_id, system_dir)


class CommandFromWireTests(unittest.TestCase):
    def test_parses_valid_command(self):
        command = command_from_wire({"button": "RIGHT", "action": "LONG"})
        self.assertEqual(command, NavigationCommand("RIGHT", "LONG"))

    def test_defaults_action_to_short(self):
        command = command_from_wire({"button": "UP"})
        self.assertEqual(command.action, "SHORT")

    def test_rejects_unknown_button(self):
        with self.assertRaises(ValueError):
            command_from_wire({"button": "MIDDLE"})

    def test_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            command_from_wire({"button": "UP", "action": "DOUBLE_TAP"})


class StateToWireTests(unittest.TestCase):
    def test_all_fields_present_and_json_safe(self):
        state = NavigationState(document_id="doc", page_index=0, node_index=2, table_row=1, table_column=3)
        wire = state_to_wire(state)
        self.assertEqual(wire, {
            "document_id": "doc", "page_index": 0, "node_index": 2, "mode": "DOCUMENT",
            "table_row": 1, "table_column": 3, "braille_offset": 0, "math_span_index": 0, "generation": 0,
        })


class AudioToWireTests(unittest.TestCase):
    def test_none_stays_none(self):
        self.assertIsNone(audio_to_wire(None))

    def test_maps_wav_to_audio_ref(self):
        wire = audio_to_wire({"text": "hi", "wav": "/abs/path/hi.wav", "duration_ms": 500, "sample_rate": 22050})
        self.assertEqual(wire, {"text": "hi", "audio_ref": "/abs/path/hi.wav", "duration_ms": 500, "sample_rate": 22050})


class HandleWireCommandTests(unittest.TestCase):
    def test_full_round_trip_returns_json_safe_dict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)

            wire_result = handle_wire_command(session, {"button": "DOWN", "action": "SHORT"})

            self.assertIn("state", wire_result)
            self.assertIn("braille_frame", wire_result)
            self.assertIn("audio", wire_result)
            self.assertEqual(wire_result["state"]["node_index"], 0)  # only item -> boundary, no move
            self.assertIsInstance(wire_result["audio"]["audio_ref"], str)

    def test_malformed_payload_returns_wire_safe_error_not_an_exception(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)

            wire_result = handle_wire_command(session, {"button": "NOT_A_BUTTON"})

            self.assertIn("error", wire_result)

    def test_result_to_wire_matches_handle_wire_command_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)
            raw_result = session.handle_button(NavigationCommand("DOWN", "SHORT"))

            self.assertEqual(result_to_wire(raw_result)["state"]["node_index"], raw_result["state"].node_index)


if __name__ == "__main__":
    unittest.main()
