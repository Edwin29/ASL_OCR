import unittest

from document_parser.structure import apply_split_ocr_replacement_draft_to_document
from document_parser.validation import validate_document_ir


class LayoutBarrierReplacementDraftTests(unittest.TestCase):
    def test_replaces_primary_order_with_split_text_segments_and_preserves_source(self):
        processed, summary = apply_split_ocr_replacement_draft_to_document(page_ir_fixture())

        page = processed["pages"][0]
        self.assertEqual(page["reading_order"], ["p102-n001-splitocr-s001", "p102-n001-splitocr-s002", "p102-n002"])
        self.assertEqual(summary["source_candidate_count"], 1)
        self.assertEqual(summary["replacement_node_count"], 2)
        self.assertEqual(summary["pages"][0]["resolved_crossing_issue_count"], 1)
        self.assertEqual(summary["pages"][0]["unresolved_crossing_issue_count"], 0)
        source_node = node_by_id(page)["p102-n001"]
        first_segment = node_by_id(page)["p102-n001-splitocr-s001"]
        self.assertFalse(source_node["is_primary_reading_order_candidate"])
        self.assertEqual(
            source_node["layout"]["split_ocr_replaced_by_node_ids"],
            ["p102-n001-splitocr-s001", "p102-n001-splitocr-s002"],
        )
        self.assertEqual(first_segment["normalized_text"], "left answer")
        self.assertEqual(first_segment["bbox"], {"x": 20.0, "y": 30.0, "width": 60.0, "height": 12.0})
        self.assertNotIn("LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE", parse_issue_codes(page))
        self.assertTrue(validate_document_ir(processed)["schema_valid"])

    def test_leaves_low_confidence_preview_in_primary_order(self):
        payload = page_ir_fixture()
        payload["pages"][0]["nodes"][0]["layout"]["split_ocr_reconciliation"]["status"] = "REVIEW_REQUIRED_LOW_CONFIDENCE"

        processed, summary = apply_split_ocr_replacement_draft_to_document(payload)

        page = processed["pages"][0]
        self.assertEqual(page["reading_order"], ["p102-n001", "p102-n002"])
        self.assertEqual(summary["source_candidate_count"], 0)
        self.assertEqual(summary["skipped_candidate_count"], 1)
        self.assertEqual(summary["pages"][0]["resolved_crossing_issue_count"], 0)
        self.assertEqual(summary["pages"][0]["unresolved_crossing_issue_count"], 1)
        self.assertIn("LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE", parse_issue_codes(page))
        self.assertTrue(validate_document_ir(processed)["schema_valid"])

    def test_reapplies_two_column_order_after_splitting_crossing_text(self):
        processed, _ = apply_split_ocr_replacement_draft_to_document(two_column_replacement_fixture())

        order = processed["pages"][0]["reading_order"]
        self.assertLess(order.index("p200-left-7"), order.index("p200-n001-splitocr-s002"))
        self.assertLess(order.index("p200-right-2"), order.index("p200-n001-splitocr-s002"))
        self.assertLess(order.index("p200-n001-splitocr-s002"), order.index("p200-right-3"))
        self.assertTrue(validate_document_ir(processed)["schema_valid"])


def page_ir_fixture():
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "validation_summary": {},
        "pages": [
            {
                "page_id": "p102",
                "page_geometry": {"width": 200, "height": 120},
                "nodes": [
                    text_node("p102-n001", 0, "left right", split_preview()),
                    text_node("p102-n002", 1, "tail", None),
                ],
                "reading_order": ["p102-n001", "p102-n002"],
                "parse_issues": [
                    {
                        "code": "LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE",
                        "severity": "warning",
                        "message": "TEXT node p102-n001 overlaps multiple layout barriers.",
                        "node_id": "p102-n001",
                        "barrier_node_ids": ["left-box", "right-box"],
                    }
                ],
                "quality_report": {"status": "PASS"},
            }
        ],
    }


def two_column_replacement_fixture():
    page = page_ir_fixture()["pages"][0]
    page["page_id"] = "p200"
    page["page_geometry"] = {"width": 200, "height": 300}
    source = text_node("p200-n001", 0, "left right", split_preview())
    source["bbox"] = {"x": 20, "y": 100, "width": 160, "height": 12}
    source["normalized_bbox"] = {"x": 0.1, "y": 0.333, "width": 0.8, "height": 0.04}
    source["layout"]["split_ocr_reconciliation"]["segments"][0]["intersection_bbox"] = {"x": 20, "y": 100, "width": 50, "height": 12}
    source["layout"]["split_ocr_reconciliation"]["segments"][1]["intersection_bbox"] = {"x": 130, "y": 100, "width": 50, "height": 12}
    nodes = [source]
    for index in range(8):
        y = 35 + index * 30
        nodes.append(column_text_node(f"p200-left-{index}", index + 1, 20, y))
        nodes.append(column_text_node(f"p200-right-{index}", index + 9, 130, y))
    page["nodes"] = nodes
    page["reading_order"] = [node["node_id"] for node in nodes]
    page["parse_issues"] = [
        {
            "code": "LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE",
            "severity": "warning",
            "message": "TEXT node p200-n001 overlaps multiple layout barriers.",
            "node_id": "p200-n001",
            "barrier_node_ids": ["left-box", "right-box"],
        }
    ]
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "validation_summary": {},
        "pages": [page],
    }


def text_node(node_id, index, text, preview):
    layout = {}
    if preview is not None:
        layout["split_ocr_reconciliation"] = preview
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": {"x": 20, "y": 30 + index * 20, "width": 140, "height": 12},
        "normalized_bbox": {"x": 0.1, "y": 0.25, "width": 0.7, "height": 0.1},
        "reading_order_index": index,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "normalized_text": text,
        "layout": layout,
    }


def column_text_node(node_id, index, x, y):
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": {"x": x, "y": y, "width": 40, "height": 10},
        "normalized_bbox": {"x": x / 200, "y": y / 300, "width": 0.2, "height": 0.033},
        "reading_order_index": index,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "normalized_text": node_id,
        "layout": {},
    }


def split_preview():
    return {
        "mode": "split_ocr_reconciliation_preview",
        "status": "REVIEW_REPLACE_CANDIDATE",
        "source_text_node_id": "p102-n001",
        "source_text": "left right",
        "combined_recognized_text": "left answer right answer",
        "segment_count": 2,
        "segments": [
            {
                "barrier_node_id": "left-box",
                "recognized_text": "left answer",
                "token_count": 1,
                "min_confidence": 0.91,
                "average_confidence": 0.91,
                "intersection_bbox": {"x": 20, "y": 30, "width": 60, "height": 12},
            },
            {
                "barrier_node_id": "right-box",
                "recognized_text": "right answer",
                "token_count": 1,
                "min_confidence": 0.93,
                "average_confidence": 0.93,
                "intersection_bbox": {"x": 100, "y": 30, "width": 60, "height": 12},
            },
        ],
    }


def node_by_id(page):
    return {node["node_id"]: node for node in page["nodes"]}


def parse_issue_codes(page):
    return [issue.get("code") for issue in page.get("parse_issues", []) if isinstance(issue, dict)]


if __name__ == "__main__":
    unittest.main()
