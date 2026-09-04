import tempfile
import unittest
from pathlib import Path

from document_parser.accessibility.braille.braille_presenter import BraillePresenter
from document_parser.accessibility.domain.commands import NavigationCommand
from document_parser.datapack.ingest import build_datapack
from document_parser.datapack.loader import load_datapack
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl
from document_parser.server.session import DatapackSession, DatapackTtsEngineAdapter


class FakeSynthesizer:
    def __init__(self):
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        return (b"\x00\x00" * 100, 16000, 1)


class FixtureVlAdapter:
    engine_id = "fixture-paddleocr-vl"
    engine_version = "0.0.0"

    def __init__(self, result_by_path):
        self.result_by_path = result_by_path

    def parse_page(self, image_path):
        return self.result_by_path[str(Path(image_path).resolve())]


def text_block(block_id, content, order, bbox=None):
    return {
        "block_label": "text",
        "block_content": content,
        "block_bbox": bbox or [100, 100 + block_id * 100, 900, 160 + block_id * 100],
        "block_id": block_id,
        "block_order": order,
    }


def fixture_result(blocks):
    return {"width": 2434, "height": 3071, "parsing_res_list": blocks}


def build_and_load_datapack(tmp_root: Path, book_id="test-book"):
    image_path = tmp_root / f"{book_id}.png"
    image_path.write_bytes(b"fake-png")
    blocks = [
        text_block(1, "함수 $f(x)=x^2$ 에 대하여", order=1),
        {
            "block_label": "display_formula", "block_content": "$$y=2x+1$$",
            "block_bbox": [100, 300, 500, 350], "block_id": 2, "block_order": 2,
        },
        {
            # Plain Hangul cell content, deliberately not math ("a>0" etc.) --
            # braille table-cell rendering only has TEXT-path (Hangul) coverage
            # today; MATH-kind table cell content is a documented, separate
            # NotImplementedError in table_formatter.py, unrelated to this test.
            "block_label": "table", "block_content": "<table><tr><td>참</td></tr></table>",
            "block_bbox": [100, 400, 500, 500], "block_id": 3, "block_order": 3,
        },
    ]
    adapter = FixtureVlAdapter({str(image_path.resolve()): fixture_result(blocks)})
    page_ir = build_document_ir_from_vl([image_path], adapter=adapter, book_id=book_id)

    output_dir = tmp_root / "datapacks"
    system_dir = output_dir / "_system"
    build_datapack(
        book_id=book_id, title="테스트", page_ir=page_ir, synthesize=FakeSynthesizer(),
        tts_manifest={}, output_dir=output_dir, system_dir=system_dir, log_fn=lambda msg: None,
    )
    return load_datapack(output_dir / book_id, system_dir)


class DatapackTtsEngineAdapterTests(unittest.TestCase):
    def test_speak_looks_up_by_exact_text(self):
        engine = DatapackTtsEngineAdapter({"hello": {"text": "hello", "wav": "a.wav"}})
        engine.speak("hello", generation=1)
        self.assertEqual(engine.last_audio["wav"], "a.wav")

    def test_speak_raises_on_miss(self):
        engine = DatapackTtsEngineAdapter({})
        with self.assertRaises(KeyError):
            engine.speak("nope", generation=1)

    def test_old_revision_audio_is_found_through_current_pronunciation(self):
        old_text = "f(x)와 a"
        engine = DatapackTtsEngineAdapter(
            {old_text: {"text": old_text, "wav": "legacy.wav"}}
        )

        engine.speak("에프(엑스)와 에이", generation=2)

        self.assertEqual(engine.last_audio["wav"], "legacy.wav")

    def test_pronunciation_compatibility_does_not_hide_unrelated_miss(self):
        engine = DatapackTtsEngineAdapter(
            {"f(x)": {"text": "f(x)", "wav": "legacy.wav"}}
        )
        with self.assertRaises(KeyError):
            engine.speak("완전히 다른 문장", generation=2)

    def test_on_complete_fires_immediately(self):
        engine = DatapackTtsEngineAdapter({"hi": {"text": "hi", "wav": "a.wav"}})
        completed = []
        engine.on_complete(lambda gen: completed.append(gen))
        engine.speak("hi", generation=3)
        self.assertEqual(completed, [3])


class DatapackSessionTests(unittest.TestCase):
    def test_construction_speaks_first_item_without_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)
            self.assertIsNotNone(session.audio)
            self.assertEqual(session.state.node_index, 0)

    def test_walking_the_whole_document_never_raises_keyerror(self):
        """The core round-trip guarantee: every utterance the live navigator
        could ever produce while walking this document was already
        pre-synthesized during ingest. A KeyError here would mean
        `enumerate_utterances` and `SpeechController`'s real dispatch have
        drifted apart."""
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)

            # Walk past the end of the document (DOWN repeatedly) -- exercises
            # every top-level focus item's first-landing announcement.
            for _ in range(20):
                session.handle_button(NavigationCommand("DOWN", "SHORT"))

            # Walk back to the start.
            for _ in range(20):
                session.handle_button(NavigationCommand("UP", "SHORT"))

            # Enter the inline math span on the first TEXT item and scroll
            # through it both directions (좌우 연장).
            for _ in range(5):
                session.handle_button(NavigationCommand("RIGHT", "SHORT"))
            for _ in range(5):
                session.handle_button(NavigationCommand("LEFT", "SHORT"))

    def test_boundary_message_audio_comes_from_shared_system_pool(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)

            result = session.handle_button(NavigationCommand("UP", "SHORT"))

            self.assertEqual(result["audio"]["text"], "문서의 시작입니다.")

    def test_silent_within_span_scroll_reports_no_new_audio(self):
        """The wire-level correctness fix: a pure within-span braille window
        scroll (Decision 2) must report `audio=None`, not stale audio from a
        previous turn -- otherwise a transport would incorrectly replay old
        speech on every silent scroll."""
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            # viewport_size=2 guarantees the display formula ("y=2x+1", a
            # top-level MATH item) needs more than one window to show fully.
            session = DatapackSession(datapack, braille_presenter=BraillePresenter(viewport_size=2))

            session.handle_button(NavigationCommand("DOWN", "SHORT"))  # -> the MATH item
            self.assertIsNotNone(session.audio)  # first landing always announces

            offset_before = session.braille_frame["offset"]
            result = session.handle_button(NavigationCommand("RIGHT", "SHORT"))  # within-span scroll
            offset_after = result["braille_frame"]["offset"]

            self.assertGreater(offset_after, offset_before)  # the scroll actually happened
            self.assertIsNone(result["audio"])  # but nothing new was spoken

    def test_table_entry_and_cell_navigation_do_not_raise(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            datapack = build_and_load_datapack(Path(temp_dir))
            session = DatapackSession(datapack)

            # Advance until the TABLE item is focused, then enter it (RIGHT).
            for _ in range(10):
                if session.state.node_index < len(datapack.document["pages"][0]["focus_items"]):
                    item = datapack.document["pages"][0]["focus_items"][session.state.node_index]
                    if item["kind"] == "TABLE":
                        break
                session.handle_button(NavigationCommand("DOWN", "SHORT"))

            session.handle_button(NavigationCommand("RIGHT", "SHORT"))  # enter table
            self.assertEqual(session.state.mode, "TABLE")
            session.handle_button(NavigationCommand("UP", "LONG"))  # exit table
            self.assertEqual(session.state.mode, "DOCUMENT")


if __name__ == "__main__":
    unittest.main()
