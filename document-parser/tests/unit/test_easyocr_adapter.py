import unittest
from pathlib import Path

from document_parser.ingest import ImageDocument
from document_parser.ocr.cache import OcrResultCache
from document_parser.ocr.easyocr_adapter import EasyOcrGeneralAdapter, bbox_from_points, token_from_easyocr_result
from document_parser.serialization.text_ir import TextOnlyPageIrBuilder


class FakeEasyOcrReader:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def readtext(self, image: str, detail: int = 1, paragraph: bool = False):
        self.calls.append({"image": image, "detail": detail, "paragraph": paragraph})
        return self.results


class EasyOcrAdapterTests(unittest.TestCase):
    def test_converts_easyocr_result_to_token(self):
        result = ([[10, 20], [50, 20], [50, 35], [10, 35]], "text", 0.91)
        token = token_from_easyocr_result(result, "p001", 1)

        self.assertIsNotNone(token)
        self.assertEqual(token.text, "text")
        self.assertEqual(token.bbox.x, 10)
        self.assertEqual(token.bbox.y, 20)
        self.assertEqual(token.bbox.width, 40)
        self.assertEqual(token.bbox.height, 15)
        self.assertEqual(token.confidence, 0.91)

    def test_recognize_returns_normalized_ocr_result(self):
        reader = FakeEasyOcrReader([
            ([[10, 20], [50, 20], [50, 35], [10, 35]], "alpha", 0.91),
            ([[10, 50], [45, 50], [45, 62], [10, 62]], "beta", 0.32),
            ("bad", "shape"),
        ])
        adapter = EasyOcrGeneralAdapter(reader=reader, low_confidence_threshold=0.5)
        result = adapter.recognize(image_doc())

        self.assertEqual(result.engine_id, "easyocr-general-ocr")
        self.assertEqual(len(result.tokens), 2)
        self.assertEqual(result.raw_result["result_count"], 3)
        self.assertEqual(result.raw_result["skipped_count"], 1)
        codes = [issue["code"] for issue in result.issues]
        self.assertIn("OCR_LOW_CONFIDENCE", codes)
        self.assertIn("UNKNOWN", codes)
        self.assertEqual(reader.calls[0]["detail"], 1)
        self.assertFalse(reader.calls[0]["paragraph"])

    def test_easyocr_tokens_flow_into_text_page_ir(self):
        reader = FakeEasyOcrReader([
            ([[10, 20], [50, 20], [50, 35], [10, 35]], "alpha", 0.91),
            ([[60, 20], [95, 20], [95, 35], [60, 35]], "beta", 0.9),
        ])
        adapter = EasyOcrGeneralAdapter(reader=reader)
        builder = TextOnlyPageIrBuilder(adapter=adapter)
        page = builder.build_page(
            image=image_doc(),
            quality=passing_quality_report(),
            result=adapter.recognize(image_doc()),
        )

        self.assertEqual(len(page["nodes"]), 1)
        self.assertEqual(page["nodes"][0]["normalized_text"], "alpha beta")
        self.assertEqual(page["nodes"][0]["source_engine"], "easyocr-general-ocr")

    def test_bbox_from_points_uses_union(self):
        bbox = bbox_from_points([[30, 40], [80, 35], [90, 70], [25, 75]])
        self.assertEqual(bbox.x, 25)
        self.assertEqual(bbox.y, 35)
        self.assertEqual(bbox.width, 65)
        self.assertEqual(bbox.height, 40)

    def test_cache_key_uses_easyocr_configuration_signature(self):
        reader = FakeEasyOcrReader([
            ([[10, 20], [50, 20], [50, 35], [10, 35]], "alpha", 0.91),
        ])
        image = image_doc()
        ko_result = EasyOcrGeneralAdapter(languages=("ko", "en"), reader=reader).recognize(image)
        en_result = EasyOcrGeneralAdapter(languages=("en",), reader=reader).recognize(image)
        cache = OcrResultCache(Path("cache"))

        self.assertNotEqual(cache.cache_key(image, ko_result), cache.cache_key(image, en_result))


def image_doc():
    return ImageDocument(
        page_id="p001",
        path=Path("p001.png"),
        width=100,
        height=100,
        mode="RGB",
        image_format="PNG",
        size_bytes=1000,
        sha256="sha",
    )


def passing_quality_report():
    from document_parser.preprocess.quality import QualityReport

    return QualityReport(
        page_id="p001",
        source="fixture",
        status="PASS",
        width=100,
        height=100,
        mode="RGB",
        image_format="PNG",
        long_edge=100,
        aspect_ratio=1.0,
        blur_score=999.0,
        issues=[],
    )


if __name__ == "__main__":
    unittest.main()
