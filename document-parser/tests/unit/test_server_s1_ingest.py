import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from document_parser.server.s0_domain import S0ConflictError, S0ValidationError
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from document_parser.server.s1_bundle import LocalBundleIngestHarness
from document_parser.server.s1_domain import S1Config, VerifiedSpreadInput
from document_parser.server.s1_parser import ParsedFragment, PaddleVlFragmentParser
from document_parser.server.s1_services import S1Pipeline


class FakeFragmentParser:
    def __init__(self, fail_times=0):
        self.calls = []
        self.fail_times = fail_times

    def parse(self, image_path, page_id, document_id):
        self.calls.append((image_path, page_id, document_id))
        if len(self.calls) <= self.fail_times:
            raise RuntimeError("temporary backend outage")
        item_id = f"{page_id}-item"
        page = {"page_id": page_id, "nodes": [], "reading_order": []}
        accessible = {
            "page_id": page_id,
            "focus_items": [{
                "id": item_id,
                "kind": "TEXT",
                "page_id": page_id,
                "reading_index": 0,
                "confidence": 1.0,
                "issues": [],
                "source_node_ids": [item_id],
                "problem_id": None,
                "spans": [{"kind": "TEXT", "text": f"content {page_id}"}],
            }],
        }
        return ParsedFragment(page, accessible, {"engine": "fake"}, {"schema_valid": True})


class FixtureVlAdapter:
    engine_id = "fixture-vl"
    engine_version = "1"

    def parse_page(self, _image_path):
        return {
            "width": 1000,
            "height": 1400,
            "parsing_res_list": [{
                "block_label": "text",
                "block_content": "incremental page",
                "block_bbox": [10, 10, 900, 100],
                "block_id": 1,
                "block_order": 1,
            }],
        }


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_bundle(root: Path, session_id: str, artifact_id: str, spread_id="spread-1", frame_id="frame-1"):
    root.mkdir(parents=True)
    records = []
    pages = {}
    source = root / "source_frame.jpg"
    Image.new("RGB", (80, 60), "black").save(source, quality=90)
    records.append(file_record(root, source))
    for side, color in (("left", "white"), ("right", "gray")):
        side_dir = root / side
        side_dir.mkdir()
        image = side_dir / "uvdoc.jpg"
        Image.new("RGB", (64, 96), color).save(image, quality=95)
        uvdoc = file_record(root, image)
        records.append(uvdoc)
        pages[side] = {
            "side": side,
            "files": {"uvdoc": uvdoc},
            "local_readiness": {"ready": True},
        }
    manifest = {
        "schema_version": "2.0",
        "artifact_id": artifact_id,
        "session_id": session_id,
        "processing_job_id": "job-1",
        "spread_id": spread_id,
        "source_frame_id": frame_id,
        "files": records,
        "pages": pages,
        "local_readiness": {"ready": True, "requires_both_pages": True},
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return manifest_path


def file_record(root: Path, path: Path):
    with Image.open(path) as image:
        width, height = image.size
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha(path),
        "size_bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "mime_type": "image/jpeg",
    }


class S1IngestTests(unittest.TestCase):
    def make_pipeline(self, root: Path, parser=None):
        store = S0Store(root / "state.sqlite3", root / "datapacks")
        s0 = S0ControlPlane(store)
        config = S1Config.under(store.datapacks_root)
        pipeline = S1Pipeline(store, s0, config, parser or FakeFragmentParser())
        return store, s0, config, pipeline

    def prepare(self, root, s0, config, *, operation="create-1", artifact="artifact-1", key="bundle-1"):
        datapack = s0.create_datapack("device-1", operation)
        scan = s0.open_scan("device-1", datapack.datapack_id, f"{operation}-open")
        source = root / f"source-{key}"
        manifest = write_bundle(source, scan.scan_session_id, artifact)
        LocalBundleIngestHarness(config).import_bundle(source, key)
        spread = VerifiedSpreadInput(
            scan.scan_session_id,
            1,
            artifact,
            "spread-1",
            "frame-1",
            key,
            sha(manifest),
        )
        return datapack, scan, spread

    def test_accept_is_durable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, config, pipeline = self.make_pipeline(root)
            _datapack, _scan, spread = self.prepare(root, s0, config)

            first = pipeline.accept_verified_spread(spread)
            restarted = S1Pipeline(
                pipeline.store, s0, config, FakeFragmentParser()
            )
            replay = restarted.accept_verified_spread(spread)

            self.assertEqual(first, replay)
            rows = pipeline.list_spreads(spread.scan_session_id)
            self.assertEqual(len(rows), 1)
            self.assertEqual(len(rows[0]["fragments"]), 2)

    def test_bundle_hash_change_and_unlisted_file_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, config, pipeline = self.make_pipeline(root)
            _datapack, _scan, spread = self.prepare(root, s0, config)
            image = config.received_root / spread.bundle_storage_key / "left" / "uvdoc.jpg"
            image.write_bytes(image.read_bytes() + b"tamper")
            with self.assertRaisesRegex(S0ConflictError, "hash differs"):
                pipeline.accept_verified_spread(spread)

            _store2, s02, config2, pipeline2 = self.make_pipeline(root / "second")
            _datapack2, _scan2, spread2 = self.prepare(root / "second", s02, config2)
            extra = config2.received_root / spread2.bundle_storage_key / "unlisted.bin"
            extra.write_bytes(b"extra")
            with self.assertRaisesRegex(S0ValidationError, "listing does not exactly match"):
                pipeline2.accept_verified_spread(spread2)

    def test_real_fragment_composition_uses_explicit_page_id_and_validation(self):
        parsed = PaddleVlFragmentParser(FixtureVlAdapter()).parse(
            Path("ignored.jpg"), "pg-explicit-00000001-L", "book-a"
        )

        self.assertEqual(parsed.page_ir["page_id"], "pg-explicit-00000001-L")
        self.assertEqual(parsed.accessible_page["page_id"], "pg-explicit-00000001-L")
        self.assertTrue(parsed.validation["schema_valid"])

    def test_same_sequence_with_different_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, config, pipeline = self.make_pipeline(root)
            _datapack, scan, spread = self.prepare(root, s0, config)
            pipeline.accept_verified_spread(spread)
            second_source = root / "source-bundle-2"
            manifest = write_bundle(second_source, scan.scan_session_id, "artifact-2")
            LocalBundleIngestHarness(config).import_bundle(second_source, "bundle-2")
            collision = VerifiedSpreadInput(
                scan.scan_session_id, 1, "artifact-2", "spread-1", "frame-1", "bundle-2", sha(manifest)
            )

            with self.assertRaisesRegex(S0ConflictError, "different content"):
                pipeline.accept_verified_spread(collision)

    def test_fragment_worker_uses_uvdoc_and_makes_spread_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parser = FakeFragmentParser()
            _store, s0, config, pipeline = self.make_pipeline(root, parser)
            _datapack, _scan, spread = self.prepare(root, s0, config)
            pipeline.accept_verified_spread(spread)

            self.assertTrue(pipeline.process_next_fragment())
            self.assertTrue(pipeline.process_next_fragment())
            self.assertFalse(pipeline.process_next_fragment())

            row = pipeline.list_spreads(spread.scan_session_id)[0]
            self.assertEqual(row["status"], "ready")
            self.assertEqual({Path(call[0]).name for call in parser.calls}, {"uvdoc.jpg"})
            self.assertEqual([call[1][-1] for call in parser.calls], ["L", "R"])

    def test_transient_parser_failure_requeues_and_survives_pipeline_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parser = FakeFragmentParser(fail_times=1)
            store, s0, config, pipeline = self.make_pipeline(root, parser)
            _datapack, _scan, spread = self.prepare(root, s0, config)
            pipeline.accept_verified_spread(spread)
            pipeline.process_next_fragment()

            restarted = S1Pipeline(store, s0, config, parser)
            while restarted.process_next_fragment():
                pass

            self.assertEqual(restarted.list_spreads(spread.scan_session_id)[0]["status"], "ready")
            attempts = [item["attempt_count"] for item in restarted.list_spreads(spread.scan_session_id)[0]["fragments"]]
            self.assertEqual(sorted(attempts), [1, 2])

    def test_sealing_accepts_only_sequences_at_or_below_cutoff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, s0, config, pipeline = self.make_pipeline(root)
            _datapack, scan, spread = self.prepare(root, s0, config)
            s0.request_seal(scan.scan_session_id, 1)
            pipeline.accept_verified_spread(spread)
            source = root / "source-sequence-2"
            manifest = write_bundle(source, scan.scan_session_id, "artifact-2", "spread-2", "frame-2")
            LocalBundleIngestHarness(config).import_bundle(source, "bundle-2")
            second = VerifiedSpreadInput(
                scan.scan_session_id, 2, "artifact-2", "spread-2", "frame-2", "bundle-2", sha(manifest)
            )

            with self.assertRaisesRegex(S0ConflictError, "does not accept"):
                pipeline.accept_verified_spread(second)


if __name__ == "__main__":
    unittest.main()
