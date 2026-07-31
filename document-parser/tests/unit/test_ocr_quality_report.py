import unittest

from document_parser.evaluation import build_ocr_quality_report


class OcrQualityReportTests(unittest.TestCase):
    def test_reports_low_confidence_nodes(self):
        report = build_ocr_quality_report(valid_payload(), low_confidence_threshold=0.5)
        page = report["pages"][0]

        self.assertEqual(report["total_node_count"], 3)
        self.assertEqual(report["total_low_confidence_node_count"], 1)
        self.assertEqual(page["low_confidence_nodes"][0]["node_id"], "p001-n002")

    def test_reports_large_vertical_reading_order_gap(self):
        report = build_ocr_quality_report(valid_payload())
        warnings = report["pages"][0]["reading_order_warnings"]

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["type"], "LARGE_VERTICAL_GAP")
        self.assertEqual(warnings[0]["from_node_id"], "p001-n002")
        self.assertEqual(warnings[0]["to_node_id"], "p001-n003")

    def test_reports_bbox_overlap(self):
        payload = valid_payload()
        page = payload["pages"][0]
        page["nodes"][2]["bbox"] = {"x": 18, "y": 20, "width": 40, "height": 12}
        report = build_ocr_quality_report(payload, overlap_threshold=0.2)
        warnings = report["pages"][0]["overlap_warnings"]

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["type"], "BBOX_OVERLAP")

    def test_reports_suspicious_shape(self):
        payload = valid_payload()
        page = payload["pages"][0]
        page["nodes"][0]["bbox"]["width"] = 90
        report = build_ocr_quality_report(payload, wide_node_ratio=0.8)

        self.assertEqual(report["pages"][0]["suspicious_shape_node_count"], 1)

    def test_reports_mixed_region_candidate_for_wide_noisy_text(self):
        payload = valid_payload()
        page = payload["pages"][0]
        page["nodes"][0]["bbox"] = {"x": 10, "y": 20, "width": 80, "height": 12}
        page["nodes"][0]["normalized_text"] = "body text @ 1 2 3 = 4"
        report = build_ocr_quality_report(payload)
        warnings = report["pages"][0]["region_separation_warnings"]

        self.assertEqual(warnings[0]["type"], "MIXED_REGION_CANDIDATE")

    def test_reports_table_like_candidate_for_answer_list_line(self):
        payload = valid_payload()
        page = payload["pages"][0]
        page["nodes"][0]["bbox"] = {"x": 10, "y": 20, "width": 70, "height": 12}
        page["nodes"][0]["normalized_text"] = "1 @ 2 @ 3 4 5 6 7 8"
        report = build_ocr_quality_report(payload)
        warning_types = {warning["type"] for warning in report["pages"][0]["region_separation_warnings"]}

        self.assertIn("TABLE_LIKE_CANDIDATE", warning_types)

    def test_reports_intro_guide_page_exclusion_candidate(self):
        report = build_ocr_quality_report(intro_guide_payload())
        warning_types = {warning["type"] for warning in report["pages"][0]["region_separation_warnings"]}

        self.assertIn("INTRO_GUIDE_PAGE_EXCLUSION_CANDIDATE", warning_types)


def valid_payload():
    return {
        "pages": [
            {
                "page_id": "p001",
                "page_geometry": {"width": 100, "height": 200},
                "nodes": [
                    {
                        "node_id": "p001-n001",
                        "bbox": {"x": 10, "y": 20, "width": 40, "height": 12},
                        "reading_order_index": 0,
                        "confidence": 0.95,
                        "normalized_text": "first",
                    },
                    {
                        "node_id": "p001-n002",
                        "bbox": {"x": 10, "y": 45, "width": 40, "height": 12},
                        "reading_order_index": 1,
                        "confidence": 0.3,
                        "normalized_text": "second",
                    },
                    {
                        "node_id": "p001-n003",
                        "bbox": {"x": 10, "y": 160, "width": 40, "height": 12},
                        "reading_order_index": 2,
                        "confidence": 0.88,
                        "normalized_text": "third",
                    },
                ],
                "parse_issues": [{"code": "OCR_LOW_CONFIDENCE", "severity": "warning"}],
            }
        ]
    }


def intro_guide_payload():
    nodes = [
        {
            "node_id": "p777-n001",
            "bbox": {"x": 10, "y": 20, "width": 80, "height": 8},
            "reading_order_index": 0,
            "confidence": 0.95,
            "normalized_text": "Book structure and features Structure",
        }
    ]
    for index in range(45):
        nodes.append({
            "node_id": f"p777-n{index + 2:03d}",
            "bbox": {
                "x": 8 + (index % 4) * 22,
                "y": 40 + (index // 4) * 10,
                "width": 16,
                "height": 4,
            },
            "reading_order_index": index + 1,
            "confidence": 0.7,
            "normalized_text": f"preview text {index}",
        })
    return {
        "pages": [
            {
                "page_id": "p777",
                "page_geometry": {"width": 100, "height": 200},
                "nodes": nodes,
                "parse_issues": [],
            }
        ]
    }


if __name__ == "__main__":
    unittest.main()
