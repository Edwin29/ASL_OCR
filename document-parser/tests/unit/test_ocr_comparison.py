import unittest

from document_parser.evaluation import build_ocr_comparison_report


class OcrComparisonTests(unittest.TestCase):
    def test_prefers_candidate_with_lower_diagnostic_score(self):
        report = build_ocr_comparison_report(
            payload("easyocr-general-ocr", confidence=0.4, low_confidence_count=1),
            payload("paddleocr-general-ocr", confidence=0.9, low_confidence_count=0),
        )

        self.assertEqual(report["baseline_engine"]["engine_id"], "easyocr-general-ocr")
        self.assertEqual(report["candidate_engine"]["engine_id"], "paddleocr-general-ocr")
        self.assertEqual(report["pages"][0]["verdict"], "CANDIDATE_PREFERRED")
        self.assertEqual(report["recommendation"], "CANDIDATE_CAN_ADVANCE_TO_OVERLAY_REVIEW")

    def test_marks_sharp_node_count_change_for_review(self):
        baseline = payload("easyocr-general-ocr", node_count=10, confidence=0.9)
        candidate = payload("paddleocr-general-ocr", node_count=3, confidence=0.9)
        report = build_ocr_comparison_report(baseline, candidate)

        self.assertEqual(report["pages"][0]["verdict"], "REVIEW")

    def test_reports_missing_candidate_page(self):
        baseline = payload("easyocr-general-ocr", page_id="p001")
        candidate = payload("paddleocr-general-ocr", page_id="p002")
        report = build_ocr_comparison_report(baseline, candidate)

        verdicts = {page["page_id"]: page["verdict"] for page in report["pages"]}
        self.assertEqual(verdicts["p001"], "BASELINE_PREFERRED")
        self.assertEqual(verdicts["p002"], "REVIEW")


def payload(
    engine_id,
    page_id="p001",
    node_count=1,
    confidence=0.9,
    low_confidence_count=0,
):
    nodes = []
    for index in range(node_count):
        node_confidence = 0.3 if index < low_confidence_count else confidence
        nodes.append({
            "node_id": f"{page_id}-n{index + 1:03d}",
            "bbox": {"x": 10, "y": 20 + index * 14, "width": 30, "height": 10},
            "reading_order_index": index,
            "confidence": node_confidence,
            "normalized_text": f"text {index}",
        })
    return {
        "engine_manifest": {
            "general_ocr": {
                "engine_id": engine_id,
                "engine_version": "test",
            }
        },
        "pages": [
            {
                "page_id": page_id,
                "page_geometry": {"width": 100, "height": 200},
                "nodes": nodes,
                "parse_issues": [],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
