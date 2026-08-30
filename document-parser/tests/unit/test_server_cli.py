"""Smoke tests for `document_parser.server.cli` -- the console demo that
drives a real `DatapackSession` (loaded from a real, if fixture-built,
datapack) via the same stdin/stdout REPL shape as `accessibility.cli`.
Not exhaustive (navigation/braille/audio-lookup logic is covered by
test_server_session.py) -- verifies the wiring runs end to end without
crashing and reports the right things at the console."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from document_parser.accessibility.braille.braille_presenter import BraillePresenter
from document_parser.accessibility.domain.commands import NavigationCommand
from document_parser.datapack.ingest import build_datapack
from document_parser.datapack.loader import load_datapack
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl
from document_parser.server.cli import describe_audio, run
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


def build_and_load_datapack(tmp_root: Path, book_id="cli-book"):
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
        book_id=book_id, title="CLI 테스트", page_ir=page_ir, synthesize=FakeSynthesizer(),
        tts_manifest={}, output_dir=output_dir, system_dir=system_dir, log_fn=lambda msg: None,
    )
    return load_datapack(output_dir / book_id, system_dir)


class DescribeAudioTests(unittest.TestCase):
    def test_none_reports_silence_explicitly(self):
        self.assertIn("무음", describe_audio(None))

    def test_entry_reports_text_and_wav_path(self):
        message = describe_audio({"text": "안녕", "wav": "/abs/path/a.wav", "duration_ms": 500, "sample_rate": 22050})
        self.assertIn("안녕", message)
        self.assertIn("/abs/path/a.wav", message)


class RunEndToEndTests(unittest.TestCase):
    def test_real_datapack_navigates_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)
            commands = io.StringIO("down\nup\nleft\nright\nq\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run(session, input_stream=commands)  # must not raise

            output = buf.getvalue()
            self.assertIn("명령:", output)
            self.assertIn("[state]", output)

    def test_unknown_command_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)
            commands = io.StringIO("banana\nq\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run(session, input_stream=commands)

            self.assertIn("알 수 없는 명령", buf.getvalue())

    def test_silent_scroll_reports_silence_at_the_console(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack, braille_presenter=BraillePresenter(viewport_size=2))
            commands = io.StringIO("down\nright\nq\n")  # DOWN -> the MATH item, RIGHT -> within-span scroll

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run(session, input_stream=commands)

            self.assertIn("무음", buf.getvalue())

    def test_initial_turn_is_reported_before_any_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)
            commands = io.StringIO("q\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run(session, input_stream=commands)

            # AUDIO for the first focus item's landing announcement appears
            # even with zero commands issued.
            self.assertIn("[AUDIO]", buf.getvalue())

    def test_confirm_short_replays_current_focus(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)
            commands = io.StringIO("c\nq\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run(session, input_stream=commands)  # must not raise

            # Same item (node 0) announced twice: the initial turn, then c's replay.
            self.assertEqual(buf.getvalue().count("page=0 node=0"), 2)

    def test_confirm_long_falls_through_to_speechcontrollers_unsupported_message(self):
        # This bare CLI has no selection-screen orchestration layer (see
        # device_flow.py, hardware/stm_pi_bridge/) to intercept CONFIRM
        # LONG -- it reaches SpeechController like any other unrecognized
        # command and gets the generic "not yet supported" boundary
        # message. Must not crash (this exercises the same
        # SYSTEM_BOUNDARY_MESSAGES/audio_by_text lookup a live datapack
        # depends on).
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)
            commands = io.StringIO("cl\nq\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run(session, input_stream=commands)  # must not raise

            self.assertIn("아직 지원되지 않습니다", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
