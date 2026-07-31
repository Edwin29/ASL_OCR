import unittest
from pathlib import Path

from document_parser.ingest import ImageDocument
from document_parser.ocr.cache import OcrResultCache
from document_parser.ocr.paddleocr_adapter import (
    PaddleOcrGeneralAdapter,
    iter_paddleocr_items,
    token_from_paddleocr_item,
)
from document_parser.serialization.text_ir import TextOnlyPageIrBuilder
from tests.unit.test_easyocr_adapter import passing_quality_report


class FakePaddleOcrReader:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def predict(self, image: str):
        self.calls.append({"image": image})
        return self.results


class PaddleOcrAdapterTests(unittest.TestCase):
    def test_iterates_paddleocr_v3_result_items(self):
        items = iter_paddleocr_items([paddle_result()])

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["text"], "alpha")
        self.assertEqual(items[1]["score"], 0.4)

    def test_converts_paddleocr_item_to_token(self):
        token = token_from_paddleocr_item(iter_paddleocr_items([paddle_result()])[0], "p001", 1)

        self.assertIsNotNone(token)
        self.assertEqual(token.text, "alpha")
        self.assertEqual(token.bbox.x, 10)
        self.assertEqual(token.bbox.y, 20)
        self.assertEqual(token.bbox.width, 40)
        self.assertEqual(token.bbox.height, 15)
        self.assertEqual(token.confidence, 0.91)

    def test_recognize_returns_normalized_ocr_result(self):
        reader = FakePaddleOcrReader([paddle_result()])
        adapter = PaddleOcrGeneralAdapter(reader=reader, low_confidence_threshold=0.5)
        result = adapter.recognize(image_doc())

        self.assertEqual(result.engine_id, "paddleocr-general-ocr")
        self.assertEqual(len(result.tokens), 2)
        self.assertEqual(result.raw_result["result_count"], 1)
        self.assertFalse(result.raw_result["safe_runtime"]["enable_mkldnn"])
        self.assertEqual(result.raw_result["safe_runtime"]["text_det_limit_side_len"], 1600)
        self.assertIn("OCR_LOW_CONFIDENCE", {issue["code"] for issue in result.issues})
        self.assertEqual(reader.calls[0]["image"], "p001.png")

    def test_paddleocr_tokens_flow_into_text_page_ir(self):
        reader = FakePaddleOcrReader([paddle_result()])
        adapter = PaddleOcrGeneralAdapter(reader=reader)
        builder = TextOnlyPageIrBuilder(adapter=adapter)
        page = builder.build_page(
            image=image_doc(),
            quality=passing_quality_report(),
            result=adapter.recognize(image_doc()),
        )

        self.assertEqual(len(page["nodes"]), 1)
        self.assertEqual(page["nodes"][0]["normalized_text"], "alpha beta")
        self.assertEqual(page["nodes"][0]["source_engine"], "paddleocr-general-ocr")

    def test_cache_key_uses_paddleocr_configuration_signature(self):
        reader = FakePaddleOcrReader([paddle_result()])
        image = image_doc()
        fast_result = PaddleOcrGeneralAdapter(text_det_limit_side_len=1600, reader=reader).recognize(image)
        larger_result = PaddleOcrGeneralAdapter(text_det_limit_side_len=2200, reader=reader).recognize(image)
        cache = OcrResultCache(Path("cache"))

        self.assertNotEqual(cache.cache_key(image, fast_result), cache.cache_key(image, larger_result))


def paddle_result():
    return {
        "rec_texts": ["alpha", "beta"],
        "rec_scores": [0.91, 0.4],
        "rec_polys": [
            [[10, 20], [50, 20], [50, 35], [10, 35]],
            [[60, 20], [95, 20], [95, 35], [60, 35]],
        ],
    }


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


if __name__ == "__main__":
    unittest.main()
