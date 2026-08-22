"""Tests for pi_bridge.py's pure protocol logic (line formatting/parsing,
the HELLO/NAV dispatch loop) against a real DatapackSession built the same
way the rest of this project's test suite does (FixtureVlAdapter + a fake
synthesizer, no model weights, no real GPU/Piper needed). What is NOT
tested here, because there is no physical STM32 board or Bluetooth link
attached to the machine this was written on: SerialLineTransport itself,
and anything on the STM32/main.c side. Run from the document-parser repo
root with document_parser importable (e.g. via `pip install -e .` or
PYTHONPATH=src), plus this folder itself on the path for `pi_bridge`:

    python -m pytest hardware/stm_pi_bridge/test_pi_bridge.py -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for `import pi_bridge`

from pi_bridge import BRAILLE_CELL_COUNT, format_frame_line, parse_nav_line, run_bridge

from document_parser.accessibility import BraillePresenter, NavigationCommand
from document_parser.datapack.ingest import build_datapack
from document_parser.datapack.loader import load_datapack
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl
from document_parser.server.session import DatapackSession


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


class FakeTransport:
    """Queues lines to "receive" in order; records every line "sent". A
    `None` appended to the receive queue simulates the transport closing."""

    def __init__(self, incoming):
        self._incoming = list(incoming)
        self.sent: list[str] = []

    def read_line(self):
        if not self._incoming:
            return None
        return self._incoming.pop(0)

    def write_line(self, line):
        self.sent.append(line)


def build_and_load_datapack(tmp_root: Path, book_id="stm-book"):
    image_path = tmp_root / f"{book_id}.png"
    image_path.write_bytes(b"fake-png")
    blocks = [
        {"block_label": "text", "block_content": "함수 $f(x)=x^2$ 에 대하여",
         "block_bbox": [100, 100, 900, 160], "block_id": 1, "block_order": 1},
        {"block_label": "display_formula", "block_content": "$$y=2x+1$$",
         "block_bbox": [100, 300, 500, 350], "block_id": 2, "block_order": 2},
    ]
    adapter = FixtureVlAdapter({str(image_path.resolve()): {"width": 2434, "height": 3071, "parsing_res_list": blocks}})
    page_ir = build_document_ir_from_vl([image_path], adapter=adapter, book_id=book_id)

    output_dir = tmp_root / "datapacks"
    system_dir = output_dir / "_system"
    build_datapack(
        book_id=book_id, title="STM 테스트", page_ir=page_ir, synthesize=FakeSynthesizer(),
        tts_manifest={}, output_dir=output_dir, system_dir=system_dir, log_fn=lambda msg: None,
    )
    return load_datapack(output_dir / book_id, system_dir)


class FormatFrameLineTests(unittest.TestCase):
    def test_pads_short_cell_lists_to_exactly_braille_cell_count(self):
        state = _FakeState(page_index=0, node_index=1, math_span_index=0, braille_offset=0, generation=3)
        line = format_frame_line(state, {"cells": [1, 2, 3]})

        fields = line.split(",")
        self.assertEqual(fields[0], "FRAME")
        self.assertEqual(len(fields), 1 + 5 + BRAILLE_CELL_COUNT)  # matches main.c's 5 + BRAILLE_CELL_COUNT exactly
        self.assertEqual(fields[6:], ["1", "2", "3"] + ["0"] * 7)

    def test_truncates_cell_lists_longer_than_braille_cell_count(self):
        # Defensive only -- should never happen once viewport_size=10 is
        # wired up correctly, but format_frame_line must never emit a line
        # main.c's fixed-width parser would reject.
        state = _FakeState(page_index=0, node_index=0, math_span_index=0, braille_offset=0, generation=0)
        line = format_frame_line(state, {"cells": list(range(20))})

        fields = line.split(",")
        self.assertEqual(len(fields), 1 + 5 + BRAILLE_CELL_COUNT)

    def test_state_fields_in_expected_order(self):
        state = _FakeState(page_index=2, node_index=5, math_span_index=1, braille_offset=7, generation=9)
        line = format_frame_line(state, {"cells": []})

        fields = line.split(",")
        self.assertEqual(fields[1:6], ["2", "5", "1", "7", "9"])


class ParseNavLineTests(unittest.TestCase):
    def test_parses_all_valid_combinations(self):
        expected = {
            "U": "UP", "D": "DOWN", "L": "LEFT", "R": "RIGHT",
        }
        for direction, button in expected.items():
            for length, action in (("S", "SHORT"), ("L", "LONG")):
                with self.subTest(direction=direction, length=length):
                    command = parse_nav_line(f"NAV,{direction},{length}")
                    self.assertEqual(command, NavigationCommand(button=button, action=action))

    def test_rejects_wrong_prefix(self):
        self.assertIsNone(parse_nav_line("HELLO"))
        self.assertIsNone(parse_nav_line("FRAME,0,0,0,0,0"))

    def test_rejects_unknown_direction_or_length(self):
        self.assertIsNone(parse_nav_line("NAV,X,S"))
        self.assertIsNone(parse_nav_line("NAV,U,X"))

    def test_rejects_wrong_field_count(self):
        self.assertIsNone(parse_nav_line("NAV,U"))
        self.assertIsNone(parse_nav_line("NAV,U,S,extra"))


class RunBridgeTests(unittest.TestCase):
    def test_hello_replies_with_current_state_without_advancing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack, braille_presenter=BraillePresenter(viewport_size=BRAILLE_CELL_COUNT))
            generation_before = session.state.generation

            transport = FakeTransport(["HELLO", None])
            run_bridge(session, transport, log=lambda msg: None)

            self.assertEqual(len(transport.sent), 1)
            self.assertTrue(transport.sent[0].startswith("FRAME,"))
            self.assertEqual(session.state.generation, generation_before)  # HELLO must not advance state

    def test_nav_line_advances_state_and_replies_with_new_frame(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack, braille_presenter=BraillePresenter(viewport_size=BRAILLE_CELL_COUNT))
            node_before = session.state.node_index

            transport = FakeTransport(["NAV,D,S", None])
            run_bridge(session, transport, log=lambda msg: None)

            self.assertEqual(len(transport.sent), 1)
            fields = transport.sent[0].split(",")
            self.assertEqual(int(fields[2]), node_before + 1)  # node_index advanced by one DOWN SHORT

    def test_every_frame_line_has_exactly_braille_cell_count_cells_walking_the_whole_document(self):
        # The real end-to-end guarantee this bridge exists for: no matter
        # what the document contains (short/long formulas, multiple pages),
        # every single FRAME line sent to the STM has exactly
        # BRAILLE_CELL_COUNT cell fields -- never more (would be silently
        # dropped by main.c's fixed-width parser), never fewer.
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack, braille_presenter=BraillePresenter(viewport_size=BRAILLE_CELL_COUNT))

            commands = ["NAV,D,S"] * 6 + ["NAV,U,S"] * 6 + ["NAV,R,S"] * 4 + ["NAV,L,S"] * 4 + [None]
            transport = FakeTransport(commands)
            run_bridge(session, transport, log=lambda msg: None)

            for line in transport.sent:
                fields = line.split(",")
                self.assertEqual(len(fields), 1 + 5 + BRAILLE_CELL_COUNT, line)

    def test_unrecognized_line_is_ignored_not_crashed_on(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack, braille_presenter=BraillePresenter(viewport_size=BRAILLE_CELL_COUNT))

            transport = FakeTransport(["GARBAGE", "", "NAV,D,S", None])
            run_bridge(session, transport, log=lambda msg: None)  # must not raise

            self.assertEqual(len(transport.sent), 1)  # only the valid NAV line got a reply


class _FakeState:
    """Minimal stand-in with just the attributes format_frame_line reads --
    avoids depending on the real NavigationState constructor's full
    signature for these pure-formatting tests."""

    def __init__(self, page_index, node_index, math_span_index, braille_offset, generation):
        self.page_index = page_index
        self.node_index = node_index
        self.math_span_index = math_span_index
        self.braille_offset = braille_offset
        self.generation = generation


if __name__ == "__main__":
    unittest.main()
