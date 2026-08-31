import tempfile
import unittest
from pathlib import Path

from document_parser.server.s0_http import create_app
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from document_parser.server.s1_domain import S1Config
from document_parser.server.s1_services import S1Pipeline
from tests.unit.test_server_s0 import write_book
from tests.unit.test_server_s1_finalize import FakeSynthesizer
from tests.unit.test_server_s1_ingest import FakeFragmentParser


class S1HttpTests(unittest.TestCase):
    def test_seal_enqueues_finalize_and_status_exposes_published_revision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root / "datapacks", "book_a")
            store = S0Store(root / "state.sqlite3", root / "datapacks")
            s0 = S0ControlPlane(store)
            s0.bootstrap_existing_datapacks()
            pipeline = S1Pipeline(
                store,
                s0,
                S1Config.under(store.datapacks_root),
                FakeFragmentParser(),
                synthesizer=FakeSynthesizer(),
                tts_manifest={"engine_id": "fake"},
            )
            client = create_app(s0, "secret", pipeline).test_client()
            base = {"X-API-Key": "secret", "Content-Type": "application/json"}
            opened = client.post(
                "/api/v1/datapacks/book_a/scan-sessions",
                headers={**base, "Idempotency-Key": "scan-open-1"},
                json={"device_id": "device-1"},
            ).get_json()

            sealing = client.post(
                f"/api/v1/scan-sessions/{opened['scan_session_id']}/seal-intent",
                headers=base,
                json={"through_sequence": 0},
            )
            self.assertEqual(sealing.status_code, 202)
            self.assertEqual(sealing.get_json()["status"], "sealing")
            self.assertEqual(sealing.get_json()["finalization"]["status"], "waiting")
            self.assertTrue(pipeline.process_next_finalization())

            status = client.get(
                f"/api/v1/scan-sessions/{opened['scan_session_id']}",
                headers={"X-API-Key": "secret"},
            ).get_json()
            spreads = client.get(
                f"/api/v1/scan-sessions/{opened['scan_session_id']}/spreads",
                headers={"X-API-Key": "secret"},
            ).get_json()
            self.assertEqual(status["status"], "sealed")
            self.assertEqual(status["published_revision"], 1)
            self.assertEqual(status["finalization"]["status"], "published")
            self.assertEqual(spreads, {"spreads": []})


if __name__ == "__main__":
    unittest.main()
