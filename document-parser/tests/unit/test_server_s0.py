import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from document_parser.datapack.ingest import build_datapack
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl
from document_parser.server.s0_domain import S0ConflictError
from document_parser.server.s0_domain import S0NotFoundError
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store


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


def write_book(datapacks_dir: Path, book_id: str) -> None:
    image_paths = []
    results = {}
    for index, text in enumerate(("first item", "second item"), start=1):
        image_path = datapacks_dir / f"{book_id}-p{index:03d}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"fake-png")
        image_paths.append(image_path)
        results[str(image_path.resolve())] = {
            "width": 2434,
            "height": 3071,
            "parsing_res_list": [{
                "block_label": "text",
                "block_content": text,
                "block_bbox": [100, 100, 900, 160],
                "block_id": index,
                "block_order": 1,
            }],
        }
    page_ir = build_document_ir_from_vl(
        image_paths,
        adapter=FixtureVlAdapter(results),
        book_id=book_id,
    )
    build_datapack(
        book_id=book_id,
        title=book_id,
        page_ir=page_ir,
        synthesize=FakeSynthesizer(),
        tts_manifest={},
        output_dir=datapacks_dir,
        system_dir=datapacks_dir / "_system",
        log_fn=lambda _message: None,
    )


class S0ControlPlaneTests(unittest.TestCase):
    def make_control_plane(self, root: Path) -> S0ControlPlane:
        return S0ControlPlane(S0Store(root / "state.sqlite3", root / "datapacks"))

    def test_migration_and_bootstrap_are_restart_safe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root / "datapacks", "book_a")
            first = self.make_control_plane(root)
            self.assertEqual(first.bootstrap_existing_datapacks()[0]["status"], "imported")

            second = self.make_control_plane(root)
            self.assertEqual(second.bootstrap_existing_datapacks()[0]["status"], "unchanged")
            catalog = second.list_datapacks("device-1")
            self.assertEqual([(row.datapack_id, row.current_revision) for row in catalog], [("book_a", 1)])

    def test_unknown_future_migration_fails_without_rebuilding_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.make_control_plane(root)
            connection = sqlite3.connect(root / "state.sqlite3")
            try:
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (999, 'future')"
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(RuntimeError, "unknown future migration"):
                self.make_control_plane(root)

    def test_create_and_scan_open_are_idempotent_and_device_exclusive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = self.make_control_plane(root)
            created = service.create_datapack("device-1", "create-1")
            replayed = service.create_datapack("device-1", "create-1")
            self.assertEqual(created, replayed)

            opened = service.open_scan("device-1", created.datapack_id, "open-1")
            recovered = self.make_control_plane(root).open_scan(
                "device-1", created.datapack_id, "open-after-restart"
            )
            self.assertEqual(opened.scan_session_id, recovered.scan_session_id)
            with self.assertRaisesRegex(S0ConflictError, "another device"):
                service.open_scan("device-2", created.datapack_id, "open-2")

    def test_scan_open_operation_key_cannot_be_reused_for_another_datapack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = self.make_control_plane(root)
            first = service.create_datapack("device-1", "create-1")
            second = service.create_datapack("device-1", "create-2")
            service.open_scan("device-1", first.datapack_id, "open-1")
            with self.assertRaisesRegex(S0ConflictError, "different request"):
                service.open_scan("device-1", second.datapack_id, "open-1")

    def test_seal_records_cutoff_but_does_not_publish_ready_revision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = self.make_control_plane(root)
            created = service.create_datapack("device-1", "create-1")
            opened = service.open_scan("device-1", created.datapack_id, "open-1")
            sealing = service.request_seal(opened.scan_session_id, 7)
            replayed = service.request_seal(opened.scan_session_id, 7)
            self.assertEqual(sealing, replayed)
            with self.assertRaisesRegex(S0ConflictError, "different cutoff"):
                service.request_seal(opened.scan_session_id, 8)
            catalog = service.list_datapacks("device-1")[0]
            self.assertEqual(catalog.status.value, "finalizing")
            self.assertIsNone(catalog.current_revision)

    def test_reading_command_receipt_prevents_double_navigation_after_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root / "datapacks", "book_a")
            service = self.make_control_plane(root)
            service.bootstrap_existing_datapacks()
            opened = service.open_reading("device-1", "book_a", 20, "reading-open-1")
            session_id = opened["reading_session_id"]
            moved = service.send_reading_command(session_id, "command-1", "PAGE_NEXT", "SHORT")
            self.assertEqual(moved["cursor"]["page_index"], 1)

            restarted = self.make_control_plane(root)
            replayed = restarted.send_reading_command(
                session_id, "command-1", "PAGE_NEXT", "SHORT"
            )
            current = restarted.get_reading(session_id)
            self.assertEqual(replayed, moved)
            self.assertEqual(current["cursor"]["page_index"], 1)
            self.assertFalse(Path(current["audio"]["audio_ref"]).is_absolute())

            with self.assertRaisesRegex(S0ConflictError, "different request"):
                restarted.send_reading_command(session_id, "command-1", "PAGE_PREVIOUS", "SHORT")

    def test_audio_resource_is_session_scoped_and_restart_safe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_book(root / "datapacks", "book_a")
            write_book(root / "datapacks", "book_b")
            service = self.make_control_plane(root)
            service.bootstrap_existing_datapacks()
            opened_a = service.open_reading("device-1", "book_a", 20, "reading-open-a")
            opened_b = service.open_reading("device-1", "book_b", 20, "reading-open-b")
            audio_ref = opened_a["audio"]["audio_ref"]

            first = service.get_audio_resource(opened_a["reading_session_id"], audio_ref)
            restarted = self.make_control_plane(root)
            replayed = restarted.get_audio_resource(
                opened_a["reading_session_id"], audio_ref.removeprefix("s0-audio:")
            )

            self.assertEqual(first.sha256, replayed.sha256)
            self.assertEqual(first.content_length, replayed.content_length)
            self.assertEqual(first.sample_rate, 16000)
            self.assertEqual(first.sample_width, 2)
            self.assertTrue(first.path.is_file())
            with self.assertRaisesRegex(S0NotFoundError, "unknown audio resource"):
                restarted.get_audio_resource(opened_b["reading_session_id"], audio_ref)

    def test_audio_resource_rejects_cross_revision_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            datapacks = root / "datapacks"
            write_book(datapacks, "book_a")
            write_book(datapacks, "book_b")
            book_b_index = json.loads((datapacks / "book_b/audio_index.json").read_text(encoding="utf-8"))
            foreign_wav = next(iter(book_b_index["utterances"].values()))["wav"]
            book_a_index_path = datapacks / "book_a/audio_index.json"
            book_a_index = json.loads(book_a_index_path.read_text(encoding="utf-8"))
            first_key = next(iter(book_a_index["utterances"]))
            book_a_index["utterances"][first_key]["wav"] = f"../book_b/{foreign_wav}"
            book_a_index_path.write_text(json.dumps(book_a_index), encoding="utf-8")
            service = self.make_control_plane(root)
            service.bootstrap_existing_datapacks()
            opened = service.open_reading("device-1", "book_a", 20, "reading-open-a")

            with self.assertRaisesRegex(S0ConflictError, "escapes the reading revision"):
                service.get_audio_resource(
                    opened["reading_session_id"], opened["audio"]["audio_ref"]
                )

    def test_audio_resource_rejects_oversized_wav(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            datapacks = root / "datapacks"
            write_book(datapacks, "book_a")
            index = json.loads((datapacks / "book_a/audio_index.json").read_text(encoding="utf-8"))
            first_entry = next(iter(index["utterances"].values()))
            wav_path = datapacks / "book_a" / first_entry["wav"]
            wav_path.write_bytes(wav_path.read_bytes() + b"x" * (4 * 1024 * 1024))
            service = self.make_control_plane(root)
            service.bootstrap_existing_datapacks()
            opened = service.open_reading("device-1", "book_a", 20, "reading-open-a")

            with self.assertRaisesRegex(S0ConflictError, "exceeds the supported size"):
                service.get_audio_resource(
                    opened["reading_session_id"], opened["audio"]["audio_ref"]
                )

    def test_invalid_legacy_directory_is_not_imported_as_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bad = root / "datapacks" / "broken"
            bad.mkdir(parents=True)
            (bad / "manifest.json").write_text(json.dumps({"book_id": "broken"}), encoding="utf-8")
            service = self.make_control_plane(root)
            result = service.bootstrap_existing_datapacks()
            self.assertEqual(result[0]["status"], "invalid")
            self.assertEqual(service.list_datapacks("device-1"), ())


if __name__ == "__main__":
    unittest.main()
