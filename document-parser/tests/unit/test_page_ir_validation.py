import unittest

from document_parser.validation import validate_document_ir


class PageIrValidationTests(unittest.TestCase):
    def test_validates_minimal_text_page_ir(self):
        summary = validate_document_ir(valid_payload())
        self.assertTrue(summary["schema_valid"])
        self.assertEqual(summary["page_count"], 1)
        self.assertEqual(summary["bbox_invalid_count"], 0)
        self.assertEqual(summary["missing_reading_order_node_count"], 0)

    def test_reports_missing_reading_order_node(self):
        payload = valid_payload()
        page = payload["pages"][0]
        page["reading_order"] = []
        page["nodes"][0]["reading_order_index"] = 4
        summary = validate_document_ir(payload)
        self.assertFalse(summary["schema_valid"])
        self.assertEqual(summary["missing_reading_order_node_count"], 1)
        self.assertEqual(summary["reading_order_index_mismatch_count"], 0)

    def test_reports_reading_order_index_mismatch(self):
        payload = valid_payload()
        page = payload["pages"][0]
        page["nodes"].append({
            "node_id": "p001-n002",
            "content_type": "TEXT",
            "bbox": {"x": 10, "y": 40, "width": 30, "height": 10},
            "normalized_bbox": {"x": 0.1, "y": 0.4, "width": 0.3, "height": 0.1},
            "reading_order_index": 0,
            "confidence": 0.9,
            "source_engine": "fixture",
            "issues": [],
        })
        page["reading_order"] = ["p001-n001", "p001-n002"]
        summary = validate_document_ir(payload)
        self.assertFalse(summary["schema_valid"])
        self.assertEqual(summary["reading_order_index_mismatch_count"], 1)

    def test_reports_invalid_geometry_bbox_confidence_and_issue(self):
        payload = valid_payload()
        page = payload["pages"][0]
        page["page_geometry"]["width"] = 50
        page["nodes"][0]["bbox"]["x"] = 90
        page["nodes"][0]["normalized_bbox"]["x"] = 0.95
        page["nodes"][0]["confidence"] = 1.2
        page["parse_issues"].append({"code": "UNKNOWN", "severity": "notice"})
        summary = validate_document_ir(payload)
        self.assertFalse(summary["schema_valid"])
        self.assertEqual(summary["bbox_invalid_count"], 1)
        self.assertEqual(summary["normalized_bbox_out_of_range_count"], 1)
        self.assertEqual(summary["confidence_invalid_count"], 1)
        self.assertEqual(summary["issue_invalid_count"], 1)

    def test_reports_duplicate_and_invalid_reading_order_refs(self):
        payload = valid_payload()
        page = payload["pages"][0]
        page["reading_order"] = ["p001-n001", "p001-n001", "p001-n999"]
        summary = validate_document_ir(payload)
        self.assertFalse(summary["schema_valid"])
        self.assertEqual(summary["reading_order_cycle_count"], 1)
        self.assertEqual(summary["invalid_reading_order_ref_count"], 1)

    def test_allows_embedded_text_nodes_outside_primary_reading_order(self):
        payload = valid_payload()
        page = payload["pages"][0]
        page["nodes"].append({
            "node_id": "p001-v001",
            "content_type": "UNSUPPORTED_VISUAL",
            "bbox": {"x": 5, "y": 10, "width": 50, "height": 40},
            "normalized_bbox": {"x": 0.05, "y": 0.1, "width": 0.5, "height": 0.4},
            "reading_order_index": 0,
            "confidence": 0.9,
            "source_engine": "fixture",
            "issues": [],
            "visual_type_candidate": "INTRO_GUIDE_PAGE_UNSUPPORTED",
            "embedded_text_nodes": ["p001-n001"],
        })
        page["nodes"][0].pop("reading_order_index")
        page["reading_order"] = ["p001-v001"]
        summary = validate_document_ir(payload)

        self.assertTrue(summary["schema_valid"])
        self.assertEqual(summary["missing_reading_order_node_count"], 0)
        self.assertEqual(summary["invalid_embedded_text_ref_count"], 0)


def valid_payload():
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "pages": [
            {
                "page_id": "p001",
                "page_geometry": {"width": 100, "height": 100},
                "nodes": [
                    {
                        "node_id": "p001-n001",
                        "content_type": "TEXT",
                        "bbox": {"x": 10, "y": 20, "width": 30, "height": 10},
                        "normalized_bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1},
                        "reading_order_index": 0,
                        "confidence": 0.9,
                        "source_engine": "fixture",
                        "issues": [],
                    }
                ],
                "reading_order": ["p001-n001"],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }
        ],
        "engine_manifest": {},
        "validation_summary": {},
    }


if __name__ == "__main__":
    unittest.main()
