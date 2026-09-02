import io
import tempfile
import time
import unittest
from pathlib import Path

from document_parser.datapack.remote_ingest import JobRegistry
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

    def parse_page(self, image_path):
        blocks = [{
            "block_label": "text", "block_content": "합쳐진 서버 테스트",
            "block_bbox": [100, 100, 900, 160], "block_id": 1, "block_order": 1,
        }]
        return {"width": 2434, "height": 3071, "parsing_res_list": blocks}


class CombinedServerConfigurationTests(unittest.TestCase):
    def test_api_key_file_is_trimmed_and_validated(self):
        from document_parser.server.combined_server import _resolve_api_key

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "api-key.txt"
            path.write_text("secret-value\n", encoding="utf-8")

            self.assertEqual(_resolve_api_key(None, path), "secret-value")

    def test_api_key_must_be_one_nonempty_line(self):
        from document_parser.server.combined_server import _resolve_api_key

        with self.assertRaises(ValueError):
            _resolve_api_key("", None)
        with self.assertRaises(ValueError):
            _resolve_api_key("first\nsecond", None)


@unittest.skipUnless(FLASK_AVAILABLE, "flask not installed (pip install document-parser[remote-ingest])")
class CombinedServerTests(unittest.TestCase):
    def _make_client(self, datapacks_dir: Path, jobs_dir: Path, api_key="secret", with_s0=False):
        from document_parser.server.combined_server import create_app

        registry = JobRegistry(
            adapter=FixtureVlAdapter(), synthesize=FakeSynthesizer(), tts_manifest={"engine_id": "piper"},
            jobs_root=jobs_dir, datapacks_dir=datapacks_dir,
        )
        store = SessionStore(datapacks_dir)
        control_plane = None
        if with_s0:
            from document_parser.server.s0_services import S0ControlPlane
            from document_parser.server.s0_store import S0Store

            control_plane = S0ControlPlane(
                S0Store(datapacks_dir / "_server" / "state.sqlite3", datapacks_dir)
            )
        app = create_app(registry, store, api_key=api_key, control_plane=control_plane)
        return app.test_client()

    def _wait_for_status(self, client, job_id, target_statuses, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            response = client.get(f"/jobs/{job_id}", headers={"X-API-Key": "secret"})
            if response.get_json()["status"] in target_statuses:
                return response.get_json()
            time.sleep(0.02)
        self.fail(f"job {job_id} did not reach {target_statuses} within {timeout}s")

    def test_upload_to_listed_to_session_with_no_download_step(self):
        # The whole point of merging the two servers: a finished ingest job
        # is immediately selectable (/datapacks) and servable (/sessions) --
        # no zip download, no manual extraction into a shared folder.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = self._make_client(datapacks_dir=root / "datapacks", jobs_dir=root / "jobs")

            self.assertEqual(client.get("/datapacks", headers={"X-API-Key": "secret"}).get_json(), {"book_ids": []})

            response = client.post(
                "/jobs", headers={"X-API-Key": "secret"},
                data={"book_id": "merged_book", "images": (io.BytesIO(b"fake-png"), "p1.png")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 202)
            job_id = response.get_json()["job_id"]

            status = self._wait_for_status(client, job_id, {"done", "error"})
            self.assertEqual(status["status"], "done", status.get("error"))

            listing = client.get("/datapacks", headers={"X-API-Key": "secret"}).get_json()
            self.assertEqual(listing["book_ids"], ["merged_book"])

            create_response = client.post(
                "/sessions", headers={"X-API-Key": "secret"},
                json={"session_id": "s1", "book_id": "merged_book", "viewport_size": 10},
            )
            self.assertEqual(create_response.status_code, 201)

            command_response = client.post(
                "/sessions/s1/command", headers={"X-API-Key": "secret"},
                json={"button": "DOWN", "action": "SHORT"},
            )
            self.assertEqual(command_response.status_code, 200)

    def test_download_route_reports_shared_dir_mode_instead_of_404_body(self):
        # /jobs/<id>/download still exists (it comes with remote_ingest's
        # routes) but there's nothing to zip -- the result already lives
        # where /datapacks and /sessions read it from directly.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = self._make_client(datapacks_dir=root / "datapacks", jobs_dir=root / "jobs")
            response = client.post(
                "/jobs", headers={"X-API-Key": "secret"},
                data={"book_id": "b", "images": (io.BytesIO(b"fake-png"), "p1.png")},
                content_type="multipart/form-data",
            )
            job_id = response.get_json()["job_id"]
            self._wait_for_status(client, job_id, {"done", "error"})

            download = client.get(f"/jobs/{job_id}/download", headers={"X-API-Key": "secret"})
            self.assertEqual(download.status_code, 409)

    def test_datapacks_endpoint_excludes_system_pool(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            datapacks_dir = root / "datapacks"
            (datapacks_dir / "_system").mkdir(parents=True)
            (datapacks_dir / "book_a").mkdir(parents=True)
            client = self._make_client(datapacks_dir=datapacks_dir, jobs_dir=root / "jobs")

            listing = client.get("/datapacks", headers={"X-API-Key": "secret"}).get_json()
            self.assertEqual(listing["book_ids"], ["book_a"])

    def test_datapacks_endpoint_needs_api_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = self._make_client(datapacks_dir=root / "datapacks", jobs_dir=root / "jobs")
            response = client.get("/datapacks")
            self.assertEqual(response.status_code, 401)

    def test_s0_json_limit_does_not_limit_legacy_image_uploads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = self._make_client(
                datapacks_dir=root / "datapacks", jobs_dir=root / "jobs", with_s0=True
            )

            response = client.post(
                "/jobs",
                headers={"X-API-Key": "secret"},
                data={"book_id": "large-image", "images": (io.BytesIO(b"x" * 70000), "p1.png")},
                content_type="multipart/form-data",
            )

            self.assertEqual(response.status_code, 202)
            self._wait_for_status(client, response.get_json()["job_id"], {"done", "error"})


if __name__ == "__main__":
    unittest.main()
