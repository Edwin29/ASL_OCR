import unittest

from document_parser.structure import apply_split_ocr_reconciliation_to_document


class LayoutBarrierReconciliationTests(unittest.TestCase):
    def test_attaches_split_ocr_segments_to_source_text_node(self):
        processed, summary = apply_split_ocr_reconciliation_to_document(
            page_ir_fixture(),
            split_ocr_manifest_fixture(),
            min_token_confidence=0.5,
        )

        node = processed["pages"][0]["nodes"][0]
        preview = node["layout"]["split_ocr_reconciliation"]

        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(summary["segment_count"], 2)
        self.assertEqual(summary["statuses"], {"REVIEW_REPLACE_CANDIDATE": 1})
        self.assertEqual(preview["status"], "REVIEW_REPLACE_CANDIDATE")
        self.assertEqual(preview["combined_recognized_text"], "left answer right answer")
        self.assertEqual([segment["barrier_node_id"] for segment in preview["segments"]], ["left-box", "right-box"])
        self.assertEqual(preview["segments"][0]["min_confidence"], 0.91)
        self.assertEqual(processed["pages"][0]["parse_issues"][-1]["code"], "SPLIT_OCR_RECONCILIATION_PREVIEW_APPLIED")

    def test_marks_low_confidence_preview_for_review(self):
        manifest = split_ocr_manifest_fixture()
        manifest["pages"][0]["recognized_work_units"][1]["tokens"][0]["confidence"] = 0.25

        processed, summary = apply_split_ocr_reconciliation_to_document(
            page_ir_fixture(),
            manifest,
            min_token_confidence=0.5,
        )

        preview = processed["pages"][0]["nodes"][0]["layout"]["split_ocr_reconciliation"]
        self.assertEqual(preview["status"], "REVIEW_REQUIRED_LOW_CONFIDENCE")
        self.assertEqual(preview["low_confidence_segment_count"], 1)
        self.assertEqual(summary["statuses"], {"REVIEW_REQUIRED_LOW_CONFIDENCE": 1})


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
                    {
                        "node_id": "p102-n001",
                        "content_type": "TEXT",
                        "bbox": {"x": 20, "y": 30, "width": 140, "height": 12},
                        "normalized_bbox": {"x": 0.1, "y": 0.25, "width": 0.7, "height": 0.1},
                        "reading_order_index": 0,
                        "confidence": 0.9,
                        "source_engine": "fixture",
                        "issues": [],
                        "normalized_text": "left right",
                        "layout": {
                            "layout_barrier_crossing_candidate": ["left-box", "right-box"],
                        },
                    }
                ],
                "reading_order": ["p102-n001"],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }
        ],
    }


def split_ocr_manifest_fixture():
    return {
        "split_ocr_manifest_version": 1,
        "mode": "layout_barrier_split_crop_reocr",
        "pages": [
            {
                "page_id": "p102",
                "recognized_work_units": [
                    {
                        "page_id": "p102",
                        "source_text_node_id": "p102-n001",
                        "barrier_node_id": "right-box",
                        "structure_label": "PROBLEM_BOX_CANDIDATE",
                        "layout_barrier_role": "problem_region_boundary",
                        "recognized_text": "right answer",
                        "token_count": 1,
                        "tokens": [{"text": "right answer", "confidence": 0.93}],
                        "crop_path": "right.png",
                        "barrier_bbox": {"x": 100, "y": 20, "width": 70, "height": 50},
                        "intersection_bbox": {"x": 100, "y": 30, "width": 60, "height": 12},
                    },
                    {
                        "page_id": "p102",
                        "source_text_node_id": "p102-n001",
                        "barrier_node_id": "left-box",
                        "structure_label": "PROBLEM_BOX_CANDIDATE",
                        "layout_barrier_role": "problem_region_boundary",
                        "recognized_text": "left answer",
                        "token_count": 1,
                        "tokens": [{"text": "left answer", "confidence": 0.91}],
                        "crop_path": "left.png",
                        "barrier_bbox": {"x": 10, "y": 20, "width": 70, "height": 50},
                        "intersection_bbox": {"x": 20, "y": 30, "width": 60, "height": 12},
                    },
                ],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
