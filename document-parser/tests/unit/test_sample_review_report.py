import unittest

from document_parser.evaluation import build_sample_review_report


class SampleReviewReportTests(unittest.TestCase):
    def test_builds_priority_sorted_sample_review(self):
        report = build_sample_review_report(
            page_ir=page_ir(),
            quality_report=quality_report(),
            validation_summary={"schema_valid": True},
            overlay_summary=overlay_summary(),
        )

        self.assertEqual(report["page_count"], 2)
        self.assertTrue(report["schema_valid"])
        self.assertEqual(report["total_node_count"], 5)
        self.assertEqual(report["total_low_confidence_node_count"], 3)
        self.assertEqual(report["total_region_separation_warning_count"], 1)
        self.assertEqual([page["page_id"] for page in report["pages"]], ["p002", "p001"])
        self.assertEqual(report["pages"][0]["review_priority_score"], 11)
        self.assertEqual(report["pages"][0]["overlay_path"], "p002_overlay.png")


def page_ir():
    return {
        "pages": [
            {"page_id": "p001", "nodes": [{"node_id": "p001-n001"}, {"node_id": "p001-n002"}]},
            {
                "page_id": "p002",
                "nodes": [{"node_id": "p002-n001"}, {"node_id": "p002-n002"}, {"node_id": "p002-n003"}],
            },
        ]
    }


def quality_report():
    return {
        "pages": [
            {
                "page_id": "p001",
                "low_confidence_node_count": 1,
                "reading_order_warning_count": 0,
                "overlap_warning_count": 0,
                "suspicious_shape_node_count": 0,
                "region_separation_warning_count": 0,
                "low_confidence_nodes": [{"node_id": "p001-n002"}],
                "reading_order_warnings": [],
                "region_separation_warnings": [],
                "parse_issue_codes": ["OCR_LOW_CONFIDENCE"],
            },
            {
                "page_id": "p002",
                "low_confidence_node_count": 2,
                "reading_order_warning_count": 1,
                "overlap_warning_count": 0,
                "suspicious_shape_node_count": 1,
                "region_separation_warning_count": 1,
                "low_confidence_nodes": [{"node_id": "p002-n001"}],
                "reading_order_warnings": [{"type": "LARGE_VERTICAL_GAP"}],
                "region_separation_warnings": [{"type": "MIXED_REGION_CANDIDATE"}],
                "parse_issue_codes": ["OCR_LOW_CONFIDENCE"],
            },
        ]
    }


def overlay_summary():
    return {
        "overlays": [
            {"page_id": "p001", "output_path": "p001_overlay.png"},
            {"page_id": "p002", "output_path": "p002_overlay.png"},
        ]
    }


if __name__ == "__main__":
    unittest.main()
