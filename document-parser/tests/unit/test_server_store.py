import tempfile
import unittest
from pathlib import Path

from document_parser.accessibility import BraillePresenter
from document_parser.datapack.ingest import build_datapack
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl
from document_parser.server.store import SessionStore


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


def write_book(datapacks_dir: Path, system_dir: Path, book_id: str):
    image_path = datapacks_dir / f"{book_id}.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"fake-png")
    blocks = [{
        "block_label": "text", "block_content": f"{book_id} 내용",
        "block_bbox": [100, 100, 900, 160], "block_id": 1, "block_order": 1,
    }]
    adapter = FixtureVlAdapter({str(image_path.resolve()): {"width": 2434, "height": 3071, "parsing_res_list": blocks}})
    page_ir = build_document_ir_from_vl([image_path], adapter=adapter, book_id=book_id)
    build_datapack(
        book_id=book_id, title=book_id, page_ir=page_ir, synthesize=FakeSynthesizer(),
        tts_manifest={}, output_dir=datapacks_dir, system_dir=system_dir, log_fn=lambda msg: None,
    )


class SessionStoreTests(unittest.TestCase):
    def test_creates_a_session_for_a_new_session_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system", "book_a")
            store = SessionStore(root)

            session = store.get_or_create_session("device-1", "book_a")

            self.assertEqual(session.datapack.book_id, "book_a")
            self.assertIs(store.get_session("device-1"), session)

    def test_braille_presenter_override_is_used_for_a_new_session(self):
        # Real physical displays (e.g. a 10-cell STM32 board) need a
        # non-default viewport size -- the server has no way to know the
        # hardware's fixed cell count unless told explicitly.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system", "book_a")
            store = SessionStore(root)
            presenter = BraillePresenter(viewport_size=10)

            session = store.get_or_create_session("device-1", "book_a", braille_presenter=presenter)

            self.assertIs(session._controller._braille_presenter, presenter)

    def test_returns_the_same_session_instance_on_repeated_calls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system", "book_a")
            store = SessionStore(root)

            first = store.get_or_create_session("device-1", "book_a")
            second = store.get_or_create_session("device-1", "book_a")

            self.assertIs(first, second)

    def test_switching_books_mid_session_replaces_the_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system", "book_a")
            write_book(root, root / "_system", "book_b")
            store = SessionStore(root)

            first = store.get_or_create_session("device-1", "book_a")
            second = store.get_or_create_session("device-1", "book_b")

            self.assertIsNot(first, second)
            self.assertEqual(second.datapack.book_id, "book_b")
            self.assertEqual(second.state.document_id, "book_b")

    def test_datapack_is_loaded_once_and_reused_across_sessions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system", "book_a")
            store = SessionStore(root)

            session_1 = store.get_or_create_session("device-1", "book_a")
            session_2 = store.get_or_create_session("device-2", "book_a")

            self.assertIs(session_1.datapack, session_2.datapack)

    def test_drop_session_removes_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system", "book_a")
            store = SessionStore(root)
            store.get_or_create_session("device-1", "book_a")

            store.drop_session("device-1")

            self.assertIsNone(store.get_session("device-1"))

    def test_get_session_returns_none_for_unknown_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(Path(temp_dir))
            self.assertIsNone(store.get_session("nope"))


if __name__ == "__main__":
    unittest.main()
