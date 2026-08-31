import json
import tempfile
import unittest
from pathlib import Path

from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from document_parser.server.s1_bundle import LocalBundleIngestHarness
from document_parser.server.s1_domain import S1Config, VerifiedSpreadInput
from document_parser.server.s1_services import S1Pipeline
from tests.unit.test_server_s0 import write_book
from tests.unit.test_server_s1_ingest import FakeFragmentParser, sha, write_bundle


class FakeSynthesizer:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, text):
        self.calls.append(text)
        if self.fail:
            raise RuntimeError("tts unavailable")
        return (b"\x00\x00" * 100, 16000, 1)


class S1FinalizeTests(unittest.TestCase):
    def make_pipeline(self, root: Path, synthesizer=None):
        store = S0Store(root / "state.sqlite3", root / "datapacks")
        s0 = S0ControlPlane(store)
        config = S1Config.under(store.datapacks_root)
        pipeline = S1Pipeline(
            store,
            s0,
            config,
            FakeFragmentParser(),
            synthesizer=synthesizer or FakeSynthesizer(),
            tts_manifest={"engine_id": "fake"},
        )
        return store, s0, config, pipeline

    def ingest_ready_spread(self, root, s0, config, pipeline, datapack_id, operation="scan-open"):
        scan = s0.open_scan("device-1", datapack_id, operation)
        source = root / f"source-{operation}"
        manifest = write_bundle(source, scan.scan_session_id, f"artifact-{operation}")
        key = f"bundle-{operation}"
        LocalBundleIngestHarness(config).import_bundle(source, key)
        spread = VerifiedSpreadInput(
            scan.scan_session_id,
            1,
            f"artifact-{operation}",
            "spread-1",
            "frame-1",
            key,
            sha(manifest),
        )
        pipeline.accept_verified_spread(spread)
        self.assertTrue(pipeline.process_next_fragment())
        self.assertTrue(pipeline.process_next_fragment())
        return scan

    def test_new_draft_publishes_revision_one_with_left_then_right(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, s0, config, pipeline = self.make_pipeline(root)
            datapack = s0.create_datapack("device-1", "create-1")
            scan = self.ingest_ready_spread(root, s0, config, pipeline, datapack.datapack_id)

            pipeline.request_seal(scan.scan_session_id, 1)
            self.assertTrue(pipeline.process_next_finalization())

            view = pipeline.get_scan_view(scan.scan_session_id)
            self.assertEqual(view["status"], "sealed")
            self.assertEqual(view["published_revision"], 1)
            with store.readonly() as connection:
                revision = connection.execute(
                    "SELECT * FROM datapack_revisions WHERE datapack_id=? AND revision=1",
                    (datapack.datapack_id,),
                ).fetchone()
            document = json.loads(
                (store.datapacks_root / revision["root_relative_path"] / "document.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual([page["page_id"][-1] for page in document["pages"]], ["L", "R"])
            reading = s0.open_reading("device-1", datapack.datapack_id, 10, "read-1")
            self.assertEqual(reading["revision"], 1)

    def test_existing_revision_append_preserves_old_pages_and_publishes_revision_two(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root / "datapacks", "book_a")
            store, s0, config, pipeline = self.make_pipeline(root)
            s0.bootstrap_existing_datapacks()
            base_document = json.loads(
                (store.datapacks_root / "book_a" / "document.json").read_text(encoding="utf-8")
            )
            scan = self.ingest_ready_spread(root, s0, config, pipeline, "book_a", "append-open")

            pipeline.request_seal(scan.scan_session_id, 1)
            pipeline.process_next_finalization()

            view = pipeline.get_scan_view(scan.scan_session_id)
            self.assertEqual(view["published_revision"], 2)
            with store.readonly() as connection:
                revisions = connection.execute(
                    "SELECT * FROM datapack_revisions WHERE datapack_id='book_a' ORDER BY revision"
                ).fetchall()
            self.assertEqual([row["status"] for row in revisions], ["superseded", "ready"])
            appended = json.loads(
                (store.datapacks_root / revisions[1]["root_relative_path"] / "document.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(appended["pages"][:2], base_document["pages"])
            self.assertEqual(len(appended["pages"]), 4)

    def test_existing_cutoff_zero_is_noop_and_draft_zero_is_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root / "datapacks", "book_a")
            _store, s0, _config, pipeline = self.make_pipeline(root)
            s0.bootstrap_existing_datapacks()
            existing_scan = s0.open_scan("device-1", "book_a", "existing-open")
            pipeline.request_seal(existing_scan.scan_session_id, 0)
            pipeline.process_next_finalization()
            self.assertEqual(pipeline.get_scan_view(existing_scan.scan_session_id)["published_revision"], 1)

            draft = s0.create_datapack("device-1", "create-empty")
            draft_scan = s0.open_scan("device-1", draft.datapack_id, "draft-open")
            pipeline.request_seal(draft_scan.scan_session_id, 0)
            pipeline.process_next_finalization()
            view = pipeline.get_scan_view(draft_scan.scan_session_id)
            self.assertEqual(view["status"], "error")
            self.assertEqual(view["error_code"], "EMPTY_DRAFT_SCAN")
            self.assertEqual(s0.list_datapacks("device-1")[0].status.value, "draft")

    def test_append_tts_failure_keeps_existing_current_revision_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root / "datapacks", "book_a")
            store, s0, config, pipeline = self.make_pipeline(root, FakeSynthesizer(fail=True))
            s0.bootstrap_existing_datapacks()
            scan = self.ingest_ready_spread(root, s0, config, pipeline, "book_a", "failed-append")
            pipeline.request_seal(scan.scan_session_id, 1)

            pipeline.process_next_finalization()

            view = pipeline.get_scan_view(scan.scan_session_id)
            self.assertEqual(view["status"], "error")
            with store.readonly() as connection:
                datapack = connection.execute("SELECT * FROM datapacks WHERE datapack_id='book_a'").fetchone()
                revision_count = connection.execute(
                    "SELECT COUNT(*) FROM datapack_revisions WHERE datapack_id='book_a'"
                ).fetchone()[0]
            self.assertEqual(datapack["status"], "ready")
            self.assertEqual(datapack["current_revision"], 1)
            self.assertEqual(revision_count, 1)

    def test_process_crash_after_directory_promotion_resumes_publish(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, s0, config, pipeline = self.make_pipeline(root)
            datapack = s0.create_datapack("device-1", "create-crash")
            scan = self.ingest_ready_spread(root, s0, config, pipeline, datapack.datapack_id, "crash-open")
            pipeline.request_seal(scan.scan_session_id, 1)
            original_publish = pipeline._publish_revision

            def crash_after_promotion(*_args, **_kwargs):
                raise KeyboardInterrupt("simulated process termination")

            pipeline._publish_revision = crash_after_promotion
            with self.assertRaises(KeyboardInterrupt):
                pipeline.process_next_finalization()
            pipeline._publish_revision = original_publish

            restarted = S1Pipeline(
                store,
                s0,
                config,
                FakeFragmentParser(),
                synthesizer=FakeSynthesizer(),
                tts_manifest={"engine_id": "fake"},
            )
            self.assertTrue(restarted.process_next_finalization())
            self.assertEqual(restarted.get_scan_view(scan.scan_session_id)["published_revision"], 1)

    def test_promoted_revision_audio_tamper_is_rejected_before_publish(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, s0, config, pipeline = self.make_pipeline(root)
            datapack = s0.create_datapack("device-1", "create-tamper")
            scan = self.ingest_ready_spread(root, s0, config, pipeline, datapack.datapack_id, "tamper-open")
            pipeline.request_seal(scan.scan_session_id, 1)

            def crash_after_promotion(*_args, **_kwargs):
                raise KeyboardInterrupt("simulated process termination")

            pipeline._publish_revision = crash_after_promotion
            with self.assertRaises(KeyboardInterrupt):
                pipeline.process_next_finalization()
            with store.readonly() as connection:
                run = connection.execute(
                    "SELECT * FROM finalize_runs WHERE scan_session_id=?",
                    (scan.scan_session_id,),
                ).fetchone()
            promoted = store.datapacks_root / run["final_relative_path"]
            next(promoted.glob("audio/*.wav")).write_bytes(b"not a wav")

            restarted = S1Pipeline(
                store,
                s0,
                config,
                FakeFragmentParser(),
                synthesizer=FakeSynthesizer(),
                tts_manifest={"engine_id": "fake"},
            )
            self.assertTrue(restarted.process_next_finalization())
            view = restarted.get_scan_view(scan.scan_session_id)
            self.assertEqual(view["status"], "error")
            self.assertEqual(view["error_code"], "REVISION_AUDIO_HASH_MISMATCH")
            with store.readonly() as connection:
                revision_count = connection.execute(
                    "SELECT COUNT(*) FROM datapack_revisions WHERE datapack_id=?",
                    (datapack.datapack_id,),
                ).fetchone()[0]
            self.assertEqual(revision_count, 0)

    def test_waiting_scan_does_not_block_ready_finalize_for_another_datapack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root / "datapacks", "book_a")
            _store, s0, _config, pipeline = self.make_pipeline(root)
            s0.bootstrap_existing_datapacks()
            waiting_draft = s0.create_datapack("device-1", "create-waiting")
            waiting_scan = s0.open_scan("device-1", waiting_draft.datapack_id, "waiting-open")
            pipeline.request_seal(waiting_scan.scan_session_id, 1)
            ready_scan = s0.open_scan("device-1", "book_a", "ready-open")
            pipeline.request_seal(ready_scan.scan_session_id, 0)

            self.assertTrue(pipeline.process_next_finalization())

            self.assertEqual(pipeline.get_scan_view(waiting_scan.scan_session_id)["status"], "sealing")
            self.assertEqual(pipeline.get_scan_view(ready_scan.scan_session_id)["status"], "sealed")


if __name__ == "__main__":
    unittest.main()
