import json
import tempfile
import unittest
from pathlib import Path

from document_parser.ingest import ImageIngestor
from document_parser.ocr.cache import OcrResultCache
from document_parser.ocr.fixture import FixtureGeneralOcrAdapter, token
from document_parser.ocr.noop import NoopGeneralOcrAdapter
from document_parser.serialization.text_ir import (
    TextOnlyPageIrBuilder,
    normalize_bbox,
    page_id_from_path,
    validate_document_ir,
)


class OcrTextIrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package_root = Path(__file__).resolve().parents[2]
        cls.sample_image = cls.package_root / "data" / "pages_pdf300" / "ebs_2027_math1_p008.png"

    def test_fixture_tokens_become_text_nodes(self):
        adapter = FixtureGeneralOcrAdapter({
            "p008": [
                token("log", 200, 300, 80, 30, confidence=0.95),
                token("rule", 300, 300, 80, 30, confidence=0.94),
            ]
        })
        builder = TextOnlyPageIrBuilder(adapter=adapter)
        page_ir = builder.build_document([self.sample_image])
        page = page_ir["pages"][0]
        self.assertEqual(len(page["nodes"]), 1)
        self.assertEqual(page["reading_order"], ["p008-n001"])
        self.assertEqual(page["nodes"][0]["normalized_text"], "log rule")
        self.assertEqual(page["nodes"][0]["layout"]["source_token_count"], 2)
        self.assertEqual(page_ir["engine_manifest"]["general_ocr"]["engine_id"], "fixture-general-ocr")
        self.assertTrue(page_ir["validation_summary"]["validation_performed"])
        self.assertTrue(page_ir["validation_summary"]["schema_valid"])

    def test_noop_adapter_reports_not_configured(self):
        builder = TextOnlyPageIrBuilder(adapter=NoopGeneralOcrAdapter())
        page_ir = builder.build_document([self.sample_image])
        page = page_ir["pages"][0]
        self.assertEqual(page["nodes"], [])
        codes = {issue["code"] for issue in page["parse_issues"]}
        self.assertIn("OCR_ENGINE_NOT_CONFIGURED", codes)

    def test_cache_writes_raw_ocr_result(self):
        image = ImageIngestor().load(self.sample_image, page_id="p008")
        adapter = FixtureGeneralOcrAdapter({"p008": [token("x", 1, 2, 3, 4)]})
        result = adapter.recognize(image)
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = OcrResultCache(Path(tmp)).write(image, result)
            self.assertTrue(cache_path.exists())
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["ocr_result"]["tokens"][0]["text"], "x")

    def test_normalize_bbox(self):
        self.assertEqual(
            normalize_bbox(token("x", 10, 20, 30, 40).bbox, 100, 200),
            {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.2},
        )

    def test_page_id_from_render_name(self):
        self.assertEqual(page_id_from_path(Path("ebs_2027_math1_p102.png"), 1), "p102")

    def test_page_id_falls_back_when_name_has_no_page_marker(self):
        self.assertEqual(page_id_from_path(Path("scan_2027_001.png"), 7), "p007")

    def test_validate_document_ir_reports_bad_reading_order_reference(self):
        payload = {
            "document_manifest": {"book_id": "book", "page_count": 1},
            "pages": [
                {
                    "page_id": "p001",
                    "page_geometry": {"width": 100, "height": 100},
                    "nodes": [
                        {
                            "node_id": "p001-n001",
                            "content_type": "TEXT",
                            "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
                            "normalized_bbox": {"x": 0, "y": 0, "width": 0.1, "height": 0.1},
                            "confidence": 0.9,
                            "source_engine": "fixture",
                            "issues": [],
                        }
                    ],
                    "reading_order": ["p001-n001", "p001-n999"],
                    "parse_issues": [],
                    "quality_report": {"status": "PASS"},
                }
            ],
            "engine_manifest": {},
            "validation_summary": {},
        }
        summary = validate_document_ir(payload)
        self.assertFalse(summary["schema_valid"])
        self.assertEqual(summary["invalid_reading_order_ref_count"], 1)


if __name__ == "__main__":
    unittest.main()
