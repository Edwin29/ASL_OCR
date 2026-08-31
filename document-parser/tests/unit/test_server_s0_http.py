import tempfile
import unittest
from pathlib import Path

from document_parser.server.s0_http import create_app
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from tests.unit.test_server_s0 import write_book


class S0HttpTests(unittest.TestCase):
    def make_client(self, root: Path):
        service = S0ControlPlane(S0Store(root / "state.sqlite3", root / "datapacks"))
        service.bootstrap_existing_datapacks()
        return create_app(service, "secret").test_client()

    def test_health_is_public_but_catalog_requires_auth(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self.make_client(Path(temp_dir))
            self.assertEqual(client.get("/api/v1/health").status_code, 200)
            response = client.get("/api/v1/devices/device-1/datapacks")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.get_json()["code"], "UNAUTHORIZED")

    def test_catalog_create_retry_returns_one_draft(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self.make_client(Path(temp_dir))
            headers = {
                "X-API-Key": "secret",
                "Idempotency-Key": "create-1",
                "Content-Type": "application/json",
            }
            first = client.post("/api/v1/devices/device-1/datapacks", headers=headers, json={})
            second = client.post("/api/v1/devices/device-1/datapacks", headers=headers, json={})
            self.assertEqual(first.status_code, 201)
            self.assertEqual(first.get_json(), second.get_json())
            listed = client.get(
                "/api/v1/devices/device-1/datapacks", headers={"X-API-Key": "secret"}
            ).get_json()["datapacks"]
            self.assertEqual(len(listed), 1)

    def test_scan_seal_returns_finalizing_without_revision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self.make_client(Path(temp_dir))
            base = {"X-API-Key": "secret", "Content-Type": "application/json"}
            created = client.post(
                "/api/v1/devices/device-1/datapacks",
                headers={**base, "Idempotency-Key": "create-1"},
                json={},
            ).get_json()
            opened = client.post(
                f"/api/v1/datapacks/{created['datapack_id']}/scan-sessions",
                headers={**base, "Idempotency-Key": "scan-open-1"},
                json={"device_id": "device-1"},
            ).get_json()
            sealed = client.post(
                f"/api/v1/scan-sessions/{opened['scan_session_id']}/seal-intent",
                headers=base,
                json={"through_sequence": 3},
            )
            self.assertEqual(sealed.status_code, 202)
            self.assertEqual(sealed.get_json()["status"], "sealing")
            self.assertIsNone(sealed.get_json()["base_revision"])

    def test_reading_command_http_retry_does_not_advance_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root / "datapacks", "book_a")
            client = self.make_client(root)
            base = {"X-API-Key": "secret", "Content-Type": "application/json"}
            opened = client.post(
                "/api/v1/reading-sessions",
                headers={**base, "Idempotency-Key": "reading-open-1"},
                json={"device_id": "device-1", "datapack_id": "book_a", "viewport_size": 20},
            ).get_json()
            url = f"/api/v1/reading-sessions/{opened['reading_session_id']}/commands"
            command = {"command_id": "cmd-1", "button": "PAGE_NEXT", "action": "SHORT"}
            first = client.post(url, headers=base, json=command)
            replay = client.post(url, headers=base, json=command)
            self.assertEqual(first.get_json(), replay.get_json())
            self.assertEqual(first.get_json()["cursor"]["page_index"], 1)

    def test_mutation_requires_json_and_idempotency_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self.make_client(Path(temp_dir))
            no_json = client.post(
                "/api/v1/devices/device-1/datapacks", headers={"X-API-Key": "secret"}
            )
            self.assertEqual(no_json.status_code, 400)
            self.assertEqual(no_json.get_json()["code"], "JSON_REQUIRED")
            no_key = client.post(
                "/api/v1/devices/device-1/datapacks",
                headers={"X-API-Key": "secret"},
                json={},
            )
            self.assertEqual(no_key.status_code, 400)
            self.assertEqual(no_key.get_json()["code"], "IDEMPOTENCY_KEY_REQUIRED")

    def test_request_body_limit_uses_structured_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self.make_client(Path(temp_dir))
            response = client.post(
                "/api/v1/devices/device-1/datapacks",
                headers={
                    "X-API-Key": "secret",
                    "Idempotency-Key": "large-1",
                    "Content-Type": "application/json",
                },
                data=b'{' + b'"padding":"' + (b'x' * 70000) + b'"}',
            )
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.get_json()["code"], "PAYLOAD_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()
