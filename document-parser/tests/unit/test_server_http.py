import tempfile
import unittest
from pathlib import Path

from document_parser.datapack.ingest import build_datapack
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl
from document_parser.server.store import SessionStore

try:
    import flask  # noqa: F401

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False


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


def write_book(datapacks_dir: Path, system_dir: Path, book_id="http-book"):
    image_path = datapacks_dir / f"{book_id}.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"fake-png")
    blocks = [
        {"block_label": "text", "block_content": "함수 $f(x)=x^2$ 에 대하여",
         "block_bbox": [100, 100, 900, 160], "block_id": 1, "block_order": 1},
        {"block_label": "display_formula", "block_content": "$$y=2x+1$$",
         "block_bbox": [100, 300, 500, 350], "block_id": 2, "block_order": 2},
    ]
    adapter = FixtureVlAdapter({str(image_path.resolve()): {"width": 2434, "height": 3071, "parsing_res_list": blocks}})
    page_ir = build_document_ir_from_vl([image_path], adapter=adapter, book_id=book_id)
    build_datapack(
        book_id=book_id, title=book_id, page_ir=page_ir, synthesize=FakeSynthesizer(),
        tts_manifest={}, output_dir=datapacks_dir, system_dir=system_dir, log_fn=lambda msg: None,
    )


@unittest.skipUnless(FLASK_AVAILABLE, "flask not installed (pip install document-parser[remote-ingest])")
class ServerHttpTests(unittest.TestCase):
    def _make_client(self, datapacks_dir: Path, api_key="secret"):
        from document_parser.server.http_server import create_app

        store = SessionStore(datapacks_dir)
        app = create_app(store, api_key=api_key)
        return app.test_client()

    def test_health_needs_no_api_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._make_client(Path(temp_dir))
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)

    def test_create_session_without_api_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._make_client(Path(temp_dir))
            response = client.post("/sessions", json={"session_id": "s1", "book_id": "http-book"})
            self.assertEqual(response.status_code, 401)

    def test_create_session_missing_fields_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._make_client(Path(temp_dir))
            response = client.post("/sessions", headers={"X-API-Key": "secret"}, json={"session_id": "s1"})
            self.assertEqual(response.status_code, 400)

    def test_create_session_unknown_book_returns_404(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._make_client(Path(temp_dir))
            response = client.post(
                "/sessions", headers={"X-API-Key": "secret"},
                json={"session_id": "s1", "book_id": "does-not-exist"},
            )
            self.assertEqual(response.status_code, 404)

    def test_create_session_returns_initial_state_without_local_storage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system")
            client = self._make_client(root)

            response = client.post(
                "/sessions", headers={"X-API-Key": "secret"},
                json={"session_id": "s1", "book_id": "http-book"},
            )

            self.assertEqual(response.status_code, 201)
            body = response.get_json()
            self.assertEqual(body["state"]["node_index"], 0)
            self.assertIsNotNone(body["audio"])  # first item's landing announcement

    def test_get_session_returns_current_state_without_advancing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system")
            client = self._make_client(root)
            client.post("/sessions", headers={"X-API-Key": "secret"}, json={"session_id": "s1", "book_id": "http-book"})

            response = client.get("/sessions/s1", headers={"X-API-Key": "secret"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["state"]["node_index"], 0)

    def test_get_unknown_session_returns_404(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._make_client(Path(temp_dir))
            response = client.get("/sessions/does-not-exist", headers={"X-API-Key": "secret"})
            self.assertEqual(response.status_code, 404)

    def test_command_advances_state_and_returns_new_frame(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system")
            client = self._make_client(root)
            client.post("/sessions", headers={"X-API-Key": "secret"}, json={"session_id": "s1", "book_id": "http-book"})

            response = client.post(
                "/sessions/s1/command", headers={"X-API-Key": "secret"},
                json={"button": "DOWN", "action": "SHORT"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["state"]["node_index"], 1)

    def test_page_next_button_is_accepted_over_the_wire(self):
        # This fixture book is single-page, so PAGE_NEXT hits the boundary --
        # the point here is just that the dedicated page-turn button round-
        # trips through command_from_wire/BUTTONS without being rejected as
        # an unknown button (that used to be true for anything but UP/DOWN/
        # LEFT/RIGHT).
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system")
            client = self._make_client(root)
            client.post("/sessions", headers={"X-API-Key": "secret"}, json={"session_id": "s1", "book_id": "http-book"})

            response = client.post(
                "/sessions/s1/command", headers={"X-API-Key": "secret"},
                json={"button": "PAGE_NEXT", "action": "SHORT"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["state"]["page_index"], 0)

    def test_command_on_unknown_session_returns_404(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._make_client(Path(temp_dir))
            response = client.post(
                "/sessions/does-not-exist/command", headers={"X-API-Key": "secret"},
                json={"button": "DOWN", "action": "SHORT"},
            )
            self.assertEqual(response.status_code, 404)

    def test_command_with_invalid_button_returns_400(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system")
            client = self._make_client(root)
            client.post("/sessions", headers={"X-API-Key": "secret"}, json={"session_id": "s1", "book_id": "http-book"})

            response = client.post(
                "/sessions/s1/command", headers={"X-API-Key": "secret"},
                json={"button": "NOT_A_BUTTON", "action": "SHORT"},
            )

            self.assertEqual(response.status_code, 400)

    def test_viewport_size_is_honored_for_a_hardware_sized_display(self):
        # The whole reason this parameter exists: a real display (e.g. the
        # STM32 board's 10 cells) needs a non-default viewport.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root, root / "_system")
            client = self._make_client(root)
            client.post(
                "/sessions", headers={"X-API-Key": "secret"},
                json={"session_id": "s1", "book_id": "http-book", "viewport_size": 10},
            )

            # Move to the MATH item (display formula) and check its frame.
            response = client.post(
                "/sessions/s1/command", headers={"X-API-Key": "secret"},
                json={"button": "DOWN", "action": "SHORT"},
            )
            frame = response.get_json()["braille_frame"]
            if frame["total_cell_count"] > 0:
                self.assertEqual(frame["viewport_size"], 10)


if __name__ == "__main__":
    unittest.main()
