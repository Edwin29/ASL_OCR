import tempfile
import unittest
from pathlib import Path

from document_parser.datapack.ingest import build_datapack
from document_parser.datapack.loader import load_datapack
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl


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


def build_and_write_datapack(tmp_root: Path, book_id="book"):
    image_path = tmp_root / f"{book_id}.png"
    image_path.write_bytes(b"fake-png")
    blocks = [{
        "block_label": "text", "block_content": "안녕하세요",
        "block_bbox": [100, 100, 900, 160], "block_id": 1, "block_order": 1,
    }]
    adapter = FixtureVlAdapter({str(image_path.resolve()): {"width": 2434, "height": 3071, "parsing_res_list": blocks}})
    page_ir = build_document_ir_from_vl([image_path], adapter=adapter, book_id=book_id)

    output_dir = tmp_root / "datapacks"
    system_dir = output_dir / "_system"
    build_datapack(
        book_id=book_id, title="제목", page_ir=page_ir, synthesize=FakeSynthesizer(),
        tts_manifest={"engine_id": "piper"}, output_dir=output_dir, system_dir=system_dir,
        log_fn=lambda msg: None,
    )
    return output_dir / book_id, system_dir


class LoadDatapackTests(unittest.TestCase):
    def test_loads_manifest_document_and_merged_audio_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            book_dir, system_dir = build_and_write_datapack(Path(temp_dir))

            datapack = load_datapack(book_dir, system_dir)

            self.assertEqual(datapack.book_id, "book")
            self.assertEqual(datapack.manifest["title"], "제목")
            self.assertEqual(len(datapack.document["pages"]), 1)
            # Book content and a system boundary message both resolve by text.
            self.assertIn("안녕하세요", datapack.audio_by_text)
            self.assertIn("문서의 끝입니다.", datapack.audio_by_text)

    def test_wav_paths_are_resolved_to_absolute_existing_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            book_dir, system_dir = build_and_write_datapack(Path(temp_dir))

            datapack = load_datapack(book_dir, system_dir)

            entry = datapack.audio_by_text["안녕하세요"]
            self.assertTrue(Path(entry["wav"]).is_absolute())
            self.assertTrue(Path(entry["wav"]).exists())

            system_entry = datapack.audio_by_text["문서의 끝입니다."]
            self.assertTrue(Path(system_entry["wav"]).is_absolute())
            self.assertTrue(Path(system_entry["wav"]).exists())


if __name__ == "__main__":
    unittest.main()
