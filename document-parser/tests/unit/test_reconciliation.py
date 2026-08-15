import tempfile
import unittest
from pathlib import Path

from PIL import Image

from document_parser.math.formula_ocr import FormulaRecognitionResult
from document_parser.ocr.fixture import FixtureGeneralOcrAdapter, token
from document_parser.reconciliation import cross_validate_document


class CrossValidateMathNodeTests(unittest.TestCase):
    def test_records_trusted_alternative_when_legacy_agrees(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            Image.new("RGB", (400, 200), "white").save(root / "book_p001.png")

            payload = document_with_math_node(
                issues=[{"code": "AST_UNCONSUMED_TOKENS", "severity": "warning", "message": "..."}],
            )
            formula_adapter = FixtureFormulaOcrAdapter(r"\sqrt[n]{a}")

            result = cross_validate_document(
                payload, images_dir=root, formula_adapter=formula_adapter, ocr_adapter=FixtureGeneralOcrAdapter({})
            )

            node = result["pages"][0]["nodes"][0]
            self.assertEqual(len(node["alternative_candidates"]), 1)
            candidate = node["alternative_candidates"][0]
            self.assertTrue(candidate["trusted"])
            self.assertEqual(candidate["raw_formula"], r"\sqrt[n]{a}")
            self.assertIn("CROSS_VALIDATION_RECORDED", {i["code"] for i in node["issues"]})

    def test_records_untrusted_alternative_when_legacy_also_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            Image.new("RGB", (400, 200), "white").save(root / "book_p001.png")

            payload = document_with_math_node(
                issues=[{"code": "AST_UNKNOWN_COMMAND", "severity": "warning", "message": "..."}],
            )
            formula_adapter = FixtureFormulaOcrAdapter("x{=}口")  # contains a stray CJK char

            result = cross_validate_document(
                payload, images_dir=root, formula_adapter=formula_adapter, ocr_adapter=FixtureGeneralOcrAdapter({})
            )

            candidate = result["pages"][0]["nodes"][0]["alternative_candidates"][0]
            self.assertFalse(candidate["trusted"])

    def test_skips_math_node_without_ast_issues(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            Image.new("RGB", (400, 200), "white").save(root / "book_p001.png")

            payload = document_with_math_node(issues=[])
            formula_adapter = FixtureFormulaOcrAdapter(r"\sqrt[n]{a}")

            result = cross_validate_document(
                payload, images_dir=root, formula_adapter=formula_adapter, ocr_adapter=FixtureGeneralOcrAdapter({})
            )

            node = result["pages"][0]["nodes"][0]
            self.assertNotIn("alternative_candidates", node)


class CrossValidateChoiceNodeTests(unittest.TestCase):
    def test_confirms_omission_when_legacy_finds_more_markers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            Image.new("RGB", (400, 200), "white").save(root / "book_p001.png")

            payload = document_with_choice_node(
                normalized_text="① 37 ② 42 ③ 47 ④ 52",  # 4 markers, missing ⑤
                issues=[{"code": "VL_POSSIBLE_CHOICE_OMISSION", "severity": "warning", "message": "..."}],
            )
            ocr_adapter = FixtureGeneralOcrAdapter({
                "p001-crossval": [token("① 37 ② 42 ③ 47 ④ 52 ⑤ 57", x=0, y=0, width=200, height=20)],
            })

            result = cross_validate_document(
                payload, images_dir=root, formula_adapter=FixtureFormulaOcrAdapter(""), ocr_adapter=ocr_adapter
            )

            node = result["pages"][0]["nodes"][0]
            confirmed = [i for i in node["issues"] if i["code"] == "CROSS_VALIDATION_CONFIRMS_OMISSION"]
            self.assertEqual(len(confirmed), 1)
            self.assertEqual(confirmed[0]["severity"], "error")

    def test_inconclusive_when_legacy_also_finds_the_same_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            Image.new("RGB", (400, 200), "white").save(root / "book_p001.png")

            payload = document_with_choice_node(
                normalized_text="① 37 ② 42 ③ 47 ④ 52",
                issues=[{"code": "VL_POSSIBLE_CHOICE_OMISSION", "severity": "warning", "message": "..."}],
            )
            ocr_adapter = FixtureGeneralOcrAdapter({
                "p001-crossval": [token("① 37 ② 42 ③ 47 ④ 52", x=0, y=0, width=200, height=20)],
            })

            result = cross_validate_document(
                payload, images_dir=root, formula_adapter=FixtureFormulaOcrAdapter(""), ocr_adapter=ocr_adapter
            )

            node = result["pages"][0]["nodes"][0]
            self.assertIn("CROSS_VALIDATION_INCONCLUSIVE", {i["code"] for i in node["issues"]})
            self.assertNotIn("CROSS_VALIDATION_CONFIRMS_OMISSION", {i["code"] for i in node["issues"]})

    def test_skips_text_node_without_choice_omission_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            Image.new("RGB", (400, 200), "white").save(root / "book_p001.png")

            payload = document_with_choice_node(normalized_text="평범한 지문 텍스트", issues=[])
            ocr_adapter = FixtureGeneralOcrAdapter({"p001-crossval": [token("평범한 지문 텍스트", x=0, y=0, width=200, height=20)]})

            result = cross_validate_document(
                payload, images_dir=root, formula_adapter=FixtureFormulaOcrAdapter(""), ocr_adapter=ocr_adapter
            )

            node = result["pages"][0]["nodes"][0]
            self.assertEqual(node["issues"], [])


class FixtureFormulaOcrAdapter:
    engine_id = "fixture-formula-ocr"
    engine_version = "0.0.0"

    def __init__(self, raw_latex: str) -> None:
        self.raw_latex = raw_latex

    def recognize(self, image_path: Path) -> FormulaRecognitionResult:
        return FormulaRecognitionResult(raw_latex=self.raw_latex, issues=[])


def document_with_math_node(issues):
    node = {
        "node_id": "p001-vl001",
        "content_type": "MATH",
        "bbox": {"x": 50, "y": 50, "width": 100, "height": 40},
        "normalized_bbox": {"x": 0.125, "y": 0.25, "width": 0.25, "height": 0.2},
        "reading_order_index": 0,
        "confidence": 1.0,
        "source_engine": "paddleocr-vl",
        "issues": issues,
        "raw_formula": "x=na",
        "formula_format": "LATEX",
    }
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "pages": [{
            "page_id": "p001",
            "page_geometry": {"width": 400, "height": 200},
            "nodes": [node],
            "reading_order": ["p001-vl001"],
            "parse_issues": [],
            "quality_report": {"status": "PASS"},
        }],
    }


def document_with_choice_node(normalized_text, issues):
    node = {
        "node_id": "p001-vl001",
        "content_type": "TEXT",
        "bbox": {"x": 50, "y": 50, "width": 200, "height": 40},
        "normalized_bbox": {"x": 0.125, "y": 0.25, "width": 0.5, "height": 0.2},
        "reading_order_index": 0,
        "confidence": 1.0,
        "source_engine": "paddleocr-vl",
        "issues": issues,
        "raw_text": normalized_text,
        "normalized_text": normalized_text,
        "spans": [{"span_type": "TEXT", "text": normalized_text}],
    }
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "pages": [{
            "page_id": "p001",
            "page_geometry": {"width": 400, "height": 200},
            "nodes": [node],
            "reading_order": ["p001-vl001"],
            "parse_issues": [],
            "quality_report": {"status": "PASS"},
        }],
    }


if __name__ == "__main__":
    unittest.main()
