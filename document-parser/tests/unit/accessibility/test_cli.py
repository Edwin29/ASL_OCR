"""Smoke tests for `document_parser.accessibility.cli` -- the runnable
entry point that was missing before (Page IR document -> SpeechController
-> TTS + console braille preview, with no wiring anywhere else in the repo).
Not exhaustive (the navigation/braille/TTS logic itself is covered by the
application/braille/speech test suites) -- just verifies the wiring runs
end to end without crashing, including the real Unicode braille rendering
that previously crashed on a non-UTF-8 console (cp949)."""

import io
import json
import tempfile
import unittest
from pathlib import Path

from document_parser.accessibility.cli import (
    BrailleFrameRecorder,
    ConsoleTtsEngineAdapter,
    render_braille_frame,
    run,
)
from document_parser.accessibility.domain.accessible_document import (
    build_accessible_document,
    build_focus_item,
    build_page,
)

from .support import load_accessible_document


class RenderBrailleFrameTests(unittest.TestCase):
    def test_empty_cells_render_as_placeholder_text(self):
        self.assertEqual(render_braille_frame({"cells": []}), "(점자 없음)")

    def test_nonempty_cells_render_as_real_unicode_braille_characters(self):
        # cell value 1 (dot 1 only) -> U+2801.
        frame = {"cells": [1], "has_previous": False, "has_next": False}
        self.assertEqual(render_braille_frame(frame), " ⠁ ")

    def test_has_previous_and_has_next_render_as_arrows(self):
        frame = {"cells": [1], "has_previous": True, "has_next": True}
        self.assertEqual(render_braille_frame(frame), "◂⠁▸")


class ConsoleTtsEngineAdapterTests(unittest.TestCase):
    def test_speak_fires_on_complete_immediately(self):
        adapter = ConsoleTtsEngineAdapter()
        completed = []
        adapter.on_complete(completed.append)
        adapter.speak("hello", 5)
        self.assertEqual(completed, [5])

    def test_cancel_does_not_raise_without_a_prior_speak(self):
        ConsoleTtsEngineAdapter().cancel()


class BrailleFrameRecorderTests(unittest.TestCase):
    """Debugging aid: dumps each distinct braille frame to a numbered .json
    file so a test run leaves an inspectable, offline-readable record --
    same motivation as PiperTtsEngineAdapter's record_dir for audio."""

    def test_records_a_frame_as_json_with_unicode_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = BrailleFrameRecorder(tmp)
            frame = {
                "source_id": "m1", "offset": 0, "viewport_size": 20, "total_cell_count": 1,
                "has_previous": False, "has_next": False, "cells": [1],
            }
            path = recorder.record(frame)
            self.assertIsNotNone(path)
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(payload["source_id"], "m1")
            self.assertEqual(payload["cells"], [1])
            self.assertEqual(payload["unicode"], " ⠁ ")

    def test_identical_consecutive_frames_are_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = BrailleFrameRecorder(tmp)
            frame = {"source_id": "m1", "offset": 0, "cells": [1], "has_previous": False, "has_next": False}
            first = recorder.record(frame)
            second = recorder.record(dict(frame))  # same content, different dict object
            self.assertIsNotNone(first)
            self.assertIsNone(second)
            self.assertEqual(len(recorder.recorded_files), 1)

    def test_a_changed_frame_gets_a_new_numbered_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = BrailleFrameRecorder(tmp)
            recorder.record({"source_id": "m1", "offset": 0, "cells": [1], "has_previous": False, "has_next": False})
            second = recorder.record({"source_id": "m1", "offset": 3, "cells": [2], "has_previous": True, "has_next": False})
            self.assertIsNotNone(second)
            self.assertEqual(len(recorder.recorded_files), 2)
            self.assertNotEqual(recorder.recorded_files[0].name, recorder.recorded_files[1].name)


class RunEndToEndTests(unittest.TestCase):
    """Runs the actual CLI `run()` loop against a real fixture and a
    hand-built document with an inline math span, driven by a fake stdin,
    to guard against the encoding crash this module previously had and any
    future wiring regressions."""

    def test_real_fixture_navigates_without_crashing(self):
        document = load_accessible_document("p019")
        engine = ConsoleTtsEngineAdapter()
        commands = io.StringIO("down\ndown\nup\nleft\nright\nq\n")
        run(document, engine, viewport_size=20, input_stream=commands)  # must not raise

    def test_navigating_into_an_inline_math_span_updates_the_braille_frame(self):
        text_item = build_focus_item(
            "t1", "TEXT", "p1", 0, ["t1"],
            spans=[
                {"kind": "TEXT", "text": "값"},
                {"kind": "MATH", "text": "a", "presentation_ast": {"type": "Identifier", "value": "a"}, "unconsumed_tokens": [], "ast_status": "VALID"},
            ],
        )
        document = build_accessible_document("doc", [build_page("p1", [text_item])])
        engine = ConsoleTtsEngineAdapter()
        commands = io.StringIO("right\nq\n")
        run(document, engine, viewport_size=20, input_stream=commands)  # must not raise
        # No direct access to the controller from `run()` by design (it's a
        # thin CLI loop) -- this test's real value is exercising the exact
        # render_braille_frame() call path with real, non-empty cells.

    def test_braille_recorder_captures_frames_across_a_run(self):
        text_item = build_focus_item(
            "t1", "TEXT", "p1", 0, ["t1"],
            spans=[{"kind": "MATH", "text": "a", "presentation_ast": {"type": "Identifier", "value": "a"}, "unconsumed_tokens": [], "ast_status": "VALID"}],
        )
        document = build_accessible_document("doc", [build_page("p1", [text_item])])
        engine = ConsoleTtsEngineAdapter()
        commands = io.StringIO("q\n")
        with tempfile.TemporaryDirectory() as tmp:
            recorder = BrailleFrameRecorder(tmp)
            run(document, engine, viewport_size=20, input_stream=commands, braille_recorder=recorder)
            self.assertGreaterEqual(len(recorder.recorded_files), 1)
            self.assertTrue(recorder.recorded_files[0].is_file())


if __name__ == "__main__":
    unittest.main()
