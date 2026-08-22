import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from document_parser.datapack.loader import load_datapack
from document_parser.datapack.remote_ingest import JobRegistry, run_ingest_job, zip_datapack_output

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

    def __init__(self, result_by_path, delay=0.0):
        self.result_by_path = result_by_path
        self.delay = delay

    def parse_page(self, image_path):
        if self.delay:
            time.sleep(self.delay)
        return self.result_by_path[str(Path(image_path).resolve())]


def write_fake_page(tmp_root: Path, name: str) -> Path:
    path = tmp_root / name
    path.write_bytes(b"fake-png")
    return path


def fixture_result_for(image_path: Path, text: str = "안녕하세요"):
    blocks = [{
        "block_label": "text", "block_content": text,
        "block_bbox": [100, 100, 900, 160], "block_id": 1, "block_order": 1,
    }]
    return {str(image_path.resolve()): {"width": 2434, "height": 3071, "parsing_res_list": blocks}}


class RunIngestJobTests(unittest.TestCase):
    def test_produces_a_loadable_datapack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = write_fake_page(root, "p001.png")
            adapter = FixtureVlAdapter(fixture_result_for(image_path))
            output_dir = root / "out"
            system_dir = output_dir / "_system"

            book_dir = run_ingest_job(
                book_id="job_book", image_paths=[image_path], output_dir=output_dir,
                system_dir=system_dir, adapter=adapter, synthesize=FakeSynthesizer(),
                tts_manifest={"engine_id": "piper"},
            )

            self.assertEqual(book_dir, output_dir / "job_book")
            datapack = load_datapack(book_dir, system_dir)
            self.assertEqual(datapack.book_id, "job_book")
            self.assertIn("안녕하세요", datapack.audio_by_text)


class ZipDatapackOutputTests(unittest.TestCase):
    def test_zip_contains_a_loadable_datapack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = write_fake_page(root, "p001.png")
            adapter = FixtureVlAdapter(fixture_result_for(image_path))
            output_dir = root / "out"
            system_dir = output_dir / "_system"
            run_ingest_job(
                book_id="job_book", image_paths=[image_path], output_dir=output_dir,
                system_dir=system_dir, adapter=adapter, synthesize=FakeSynthesizer(),
                tts_manifest={},
            )

            zip_path = zip_datapack_output(output_dir, root / "job_book.zip")

            self.assertTrue(zip_path.exists())
            extract_dir = root / "extracted"
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)
            datapack = load_datapack(extract_dir / "job_book", extract_dir / "_system")
            self.assertEqual(datapack.book_id, "job_book")


@unittest.skipUnless(FLASK_AVAILABLE, "flask not installed (pip install document-parser[remote-ingest])")
class RemoteIngestServerTests(unittest.TestCase):
    def _make_client(self, adapter=None, synthesize=None, jobs_root=None):
        from document_parser.datapack.remote_ingest import create_app

        registry = JobRegistry(
            adapter=adapter or FixtureVlAdapter({}),
            synthesize=synthesize or FakeSynthesizer(),
            tts_manifest={"engine_id": "piper"},
            jobs_root=jobs_root,
        )
        app = create_app(registry, api_key="secret")
        return app.test_client(), registry

    def _wait_for_status(self, client, job_id, target_statuses, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            response = client.get(f"/jobs/{job_id}", headers={"X-API-Key": "secret"})
            if response.get_json()["status"] in target_statuses:
                return response.get_json()
            time.sleep(0.02)
        self.fail(f"job {job_id} did not reach {target_statuses} within {timeout}s")

    def test_health_needs_no_api_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._make_client(jobs_root=Path(temp_dir))
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"status": "ok"})

    def test_create_job_without_api_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._make_client(jobs_root=Path(temp_dir))
            response = client.post("/jobs", data={"book_id": "b"})
            self.assertEqual(response.status_code, 401)

    def test_create_job_without_book_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._make_client(jobs_root=Path(temp_dir))
            response = client.post(
                "/jobs", headers={"X-API-Key": "secret"},
                data={"images": (io.BytesIO(b"fake-png"), "p1.png")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 400)

    def test_create_job_without_images_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._make_client(jobs_root=Path(temp_dir))
            response = client.post("/jobs", headers={"X-API-Key": "secret"}, data={"book_id": "b"})
            self.assertEqual(response.status_code, 400)

    def test_full_happy_path_upload_poll_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jobs_root = root / "jobs"

            # The adapter looks up results by the *saved* image path, which the
            # server assigns internally -- so build a fake image on disk first,
            # then swap in an adapter that answers for whatever filename the
            # server ends up saving it as ("p1.png", from the upload's filename).
            adapter = _AnyPathVlAdapter(text="원격 업로드 테스트")
            client, _ = self._make_client(adapter=adapter, jobs_root=jobs_root)

            response = client.post(
                "/jobs", headers={"X-API-Key": "secret"},
                data={"book_id": "remote_book", "images": (io.BytesIO(b"fake-png"), "p1.png")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 202)
            job_id = response.get_json()["job_id"]

            status = self._wait_for_status(client, job_id, {"done", "error"})
            self.assertEqual(status["status"], "done", status.get("error"))

            # `with` closes Flask's send_file file handle before the test's
            # TemporaryDirectory tries to clean up -- on Windows an open
            # handle to a file under that directory otherwise makes cleanup
            # fail with PermissionError.
            with client.get(f"/jobs/{job_id}/download", headers={"X-API-Key": "secret"}) as download:
                self.assertEqual(download.status_code, 200)
                zip_bytes = download.data
            extract_dir = root / "extracted"
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(extract_dir)
            datapack = load_datapack(extract_dir / "remote_book", extract_dir / "_system")
            self.assertIn("원격 업로드 테스트", datapack.audio_by_text)

    def test_download_before_done_returns_409(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jobs_root = root / "jobs"
            adapter = _AnyPathVlAdapter(text="느린 작업", delay=0.3)
            client, _ = self._make_client(adapter=adapter, jobs_root=jobs_root)

            response = client.post(
                "/jobs", headers={"X-API-Key": "secret"},
                data={"book_id": "slow_book", "images": (io.BytesIO(b"fake-png"), "p1.png")},
                content_type="multipart/form-data",
            )
            job_id = response.get_json()["job_id"]

            download = client.get(f"/jobs/{job_id}/download", headers={"X-API-Key": "secret"})
            self.assertEqual(download.status_code, 409)

            self._wait_for_status(client, job_id, {"done", "error"})

    def test_unknown_job_id_returns_404(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._make_client(jobs_root=Path(temp_dir))
            response = client.get("/jobs/does-not-exist", headers={"X-API-Key": "secret"})
            self.assertEqual(response.status_code, 404)


class _AnyPathVlAdapter:
    """Answers any `parse_page(path)` call with the same fixture result,
    regardless of the path -- needed for the HTTP tests since the server
    (not the test) picks the on-disk filename for an uploaded image."""

    engine_id = "fixture-paddleocr-vl"
    engine_version = "0.0.0"

    def __init__(self, text: str, delay: float = 0.0):
        self._text = text
        self.delay = delay

    def parse_page(self, image_path):
        if self.delay:
            time.sleep(self.delay)
        blocks = [{
            "block_label": "text", "block_content": self._text,
            "block_bbox": [100, 100, 900, 160], "block_id": 1, "block_order": 1,
        }]
        return {"width": 2434, "height": 3071, "parsing_res_list": blocks}


if __name__ == "__main__":
    unittest.main()
