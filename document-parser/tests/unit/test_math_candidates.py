import unittest

from document_parser.math import detect_math_candidates_in_document, math_candidate_report
from document_parser.math.candidates import score_math_candidate_text
from document_parser.validation import validate_document_ir


class MathCandidateTests(unittest.TestCase):
    def test_scores_formula_like_text_as_candidate(self):
        result = score_math_candidate_text("f(x)=x^2+1")

        self.assertTrue(result["is_candidate"])
        self.assertIn("relation_operator", result["reasons"])

    def test_does_not_score_simple_answer_list_as_candidate(self):
        result = score_math_candidate_text("① 2 ② 3 ③ 4 ④ 5")

        self.assertFalse(result["is_candidate"])
        self.assertEqual(result["candidate_kind"], "excluded_answer_list")

    def test_marks_text_nodes_and_keeps_page_ir_valid(self):
        processed = detect_math_candidates_in_document(page_ir_fixture())
        page = processed["pages"][0]
        formula_node = next(node for node in page["nodes"] if node["node_id"] == "p008-n001")
        answer_node = next(node for node in page["nodes"] if node["node_id"] == "p008-n002")

        self.assertTrue(formula_node["layout"]["math_candidate"]["is_candidate"])
        self.assertNotIn("math_candidate", answer_node["layout"])
        self.assertIn("MATH_CANDIDATES_DETECTED", {issue["code"] for issue in page["parse_issues"]})
        self.assertTrue(validate_document_ir(processed)["schema_valid"])

    def test_builds_report(self):
        processed = detect_math_candidates_in_document(page_ir_fixture())
        report = math_candidate_report(processed)

        self.assertEqual(report["total_candidate_count"], 1)
        self.assertEqual(report["pages"][0]["candidates"][0]["node_id"], "p008-n001")

    def test_skips_text_nodes_outside_primary_reading_order(self):
        payload = page_ir_fixture()
        page = payload["pages"][0]
        page["reading_order"] = ["p008-n003"]

        processed = detect_math_candidates_in_document(payload)
        report = math_candidate_report(processed)

        self.assertEqual(report["total_candidate_count"], 0)


def page_ir_fixture():
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "validation_summary": {},
        "pages": [
            {
                "page_id": "p008",
                "page_geometry": {"width": 200, "height": 300},
                "nodes": [
                    text_node("p008-n001", "f(x)=x^2+1", 0),
                    text_node("p008-n002", "① 2 ② 3 ③ 4 ④ 5", 1),
                    text_node("p008-n003", "plain explanation", 2),
                ],
                "reading_order": ["p008-n001", "p008-n002", "p008-n003"],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }
        ],
    }


def text_node(node_id, text, index):
    y = 10 + index * 20
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": {"x": 10, "y": y, "width": 100, "height": 10},
        "normalized_bbox": {"x": 0.05, "y": y / 300, "width": 0.5, "height": 0.033333},
        "reading_order_index": index,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "raw_text": text,
        "normalized_text": text,
        "spans": [{"span_type": "TEXT", "text": text}],
        "layout": {},
    }


if __name__ == "__main__":
    unittest.main()
