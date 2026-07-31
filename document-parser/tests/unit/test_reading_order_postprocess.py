import unittest

from document_parser.serialization.reading_order import apply_two_column_reading_order
from document_parser.validation import validate_document_ir
from tests.unit.test_page_policy import two_column_nodes


class ReadingOrderPostprocessTests(unittest.TestCase):
    def test_reorders_two_column_page_left_column_before_right_column(self):
        page = {
            "page_id": "p200",
            "page_geometry": {"width": 200, "height": 300},
            "nodes": two_column_nodes(),
            "reading_order": [node["node_id"] for node in two_column_nodes()],
            "parse_issues": [],
            "quality_report": {"status": "PASS"},
        }
        processed = apply_two_column_reading_order(page)

        self.assertEqual(processed["reading_order"][0], "p200-n001")
        self.assertEqual(processed["reading_order"][1:9], [f"p200-l{index}" for index in range(8)])
        self.assertEqual(processed["reading_order"][9:17], [f"p200-r{index}" for index in range(8)])
        self.assertEqual(processed["reading_order"][-1], "p200-n999")
        self.assertIn("TWO_COLUMN_READING_ORDER_APPLIED", {issue["code"] for issue in processed["parse_issues"]})
        self.assertEqual(processed["nodes"][2]["layout"]["reading_order_group"], "LEFT")

        payload = {
            "document_manifest": {"book_id": "book", "page_count": 1},
            "pages": [processed],
            "engine_manifest": {},
            "validation_summary": {},
        }
        self.assertTrue(validate_document_ir(payload)["schema_valid"])

    def test_reapplying_two_column_postprocess_does_not_duplicate_issue(self):
        page = {
            "page_id": "p200",
            "page_geometry": {"width": 200, "height": 300},
            "nodes": two_column_nodes(),
            "reading_order": [node["node_id"] for node in two_column_nodes()],
            "parse_issues": [],
            "quality_report": {"status": "PASS"},
        }

        processed = apply_two_column_reading_order(apply_two_column_reading_order(page))
        issue_codes = [issue["code"] for issue in processed["parse_issues"]]

        self.assertEqual(issue_codes.count("TWO_COLUMN_READING_ORDER_APPLIED"), 1)


if __name__ == "__main__":
    unittest.main()
