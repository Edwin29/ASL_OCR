import unittest

from document_parser.structure import build_split_ocr_replacement_review_report


class SplitOcrReplacementReviewTests(unittest.TestCase):
    def test_reports_replacement_before_after_and_unresolved_candidates(self):
        report = build_split_ocr_replacement_review_report(page_ir_fixture())

        self.assertEqual(report["replacement_source_count"], 1)
        self.assertEqual(report["replacement_segment_count"], 2)
        self.assertEqual(report["unresolved_candidate_count"], 1)
        replacement = report["pages"][0]["replacements"][0]
        self.assertEqual(replacement["source_text"], "left right")
        self.assertEqual(replacement["replacement_text"], "left answer right answer")
        self.assertEqual(replacement["replacement_node_ids"], ["p102-n001-splitocr-s001", "p102-n001-splitocr-s002"])
        self.assertEqual(replacement["replacement_segments"][0]["barrier_node_id"], "left-box")
        unresolved = report["pages"][0]["unresolved_candidates"][0]
        self.assertEqual(unresolved["source_text_node_id"], "p102-n002")
        self.assertEqual(unresolved["status"], "REVIEW_REQUIRED_LOW_CONFIDENCE")


def page_ir_fixture():
    return {
        "pages": [
            {
                "page_id": "p102",
                "nodes": [
                    source_node(),
                    segment_node("p102-n001-splitocr-s001", "left answer", 0, "left-box"),
                    segment_node("p102-n001-splitocr-s002", "right answer", 1, "right-box"),
                    unresolved_node(),
                ],
                "reading_order": ["p102-n001-splitocr-s001", "p102-n001-splitocr-s002", "p102-n002"],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }
        ]
    }


def source_node():
    return {
        "node_id": "p102-n001",
        "content_type": "TEXT",
        "bbox": {"x": 20, "y": 30, "width": 140, "height": 12},
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [{"code": "TEXT_REPLACED_BY_SPLIT_OCR_DRAFT", "severity": "info"}],
        "normalized_text": "left right",
        "is_primary_reading_order_candidate": False,
        "layout": {
            "split_ocr_replacement_draft_status": "DRAFT_REPLACED_IN_PRIMARY_READING_ORDER",
            "split_ocr_replaced_by_node_ids": ["p102-n001-splitocr-s001", "p102-n001-splitocr-s002"],
        },
    }


def segment_node(node_id, text, index, barrier_id):
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": {"x": 20 + index * 80, "y": 30, "width": 60, "height": 12},
        "confidence": 0.9,
        "source_engine": "split-ocr-reconciliation-draft",
        "issues": [],
        "normalized_text": text,
        "reading_order_index": index,
        "layout": {
            "is_split_ocr_replacement_draft": True,
            "split_ocr_source_text_node_id": "p102-n001",
            "split_ocr_source_barrier_node_id": barrier_id,
            "split_ocr_crop_path": f"{barrier_id}.png",
        },
    }


def unresolved_node():
    return {
        "node_id": "p102-n002",
        "content_type": "TEXT",
        "bbox": {"x": 20, "y": 50, "width": 140, "height": 12},
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "normalized_text": "low confidence",
        "reading_order_index": 2,
        "layout": {
            "split_ocr_reconciliation": {
                "status": "REVIEW_REQUIRED_LOW_CONFIDENCE",
                "segment_count": 2,
                "combined_recognized_text": "low confidence split",
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
