import unittest

from document_parser.serialization.visual_regions import INTRO_GUIDE_PAGE_VISUAL_TYPE, apply_intro_page_exclusion
from document_parser.validation import validate_document_ir


class VisualRegionPostprocessTests(unittest.TestCase):
    def test_intro_guide_page_is_report_only_without_approval(self):
        page = intro_page()
        processed = apply_intro_page_exclusion(page)

        self.assertEqual(processed["reading_order"], page["reading_order"])
        self.assertEqual(
            [
                node
                for node in processed["nodes"]
                if node["content_type"] == "UNSUPPORTED_VISUAL"
            ],
            [],
        )

    def test_intro_guide_page_is_excluded_from_primary_reading_order(self):
        page = intro_page()
        processed = apply_intro_page_exclusion(page, approved_exclusion_types={INTRO_GUIDE_PAGE_VISUAL_TYPE})
        visual_nodes = [
            node
            for node in processed["nodes"]
            if node["content_type"] == "UNSUPPORTED_VISUAL"
        ]
        visual_node = visual_nodes[0]
        embedded_ids = set(visual_node["embedded_text_nodes"])

        self.assertEqual(len(visual_nodes), 1)
        self.assertEqual(visual_node["visual_type_candidate"], "INTRO_GUIDE_PAGE_UNSUPPORTED")
        self.assertEqual(visual_node["bbox"], {"x": 0, "y": 0, "width": 200, "height": 300})
        self.assertEqual(processed["reading_order"], [visual_node["node_id"]])
        self.assertEqual(processed["reading_order"], ["p777-intro-guide"])
        self.assertIn("p777-n002", embedded_ids)
        self.assertNotIn("p777-n002", processed["reading_order"])
        self.assertNotIn("p777-n040", processed["reading_order"])
        self.assertIn("INTRO_GUIDE_PAGE_EXCLUDED", {issue["code"] for issue in processed["parse_issues"]})

        payload = {
            "document_manifest": {"book_id": "book", "page_count": 1},
            "pages": [processed],
            "engine_manifest": {},
            "validation_summary": {},
        }
        self.assertTrue(validate_document_ir(payload)["schema_valid"])


def intro_page():
    nodes = [
        text_node("p777-n001", 0, 20, 20, 160, 12, "Book structure and features Structure"),
        text_node("p777-n040", 40, 70, 160, 120, 40, "Publisher guide text should be excluded too."),
    ]
    for index in range(30):
        nodes.append(text_node(
            f"p777-n{index + 2:03d}",
            index + 1,
            20 + (index % 3) * 28,
            60 + (index // 3) * 9,
            20,
            4,
            f"preview {index}",
        ))
    return {
        "page_id": "p777",
        "page_geometry": {"width": 200, "height": 300},
        "nodes": nodes,
        "reading_order": [node["node_id"] for node in nodes],
        "parse_issues": [],
        "quality_report": {"status": "PASS"},
    }


def text_node(
    node_id,
    reading_order_index,
    x,
    y,
    width,
    height,
    text,
):
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "normalized_bbox": {
            "x": round(x / 200, 6),
            "y": round(y / 300, 6),
            "width": round(width / 200, 6),
            "height": round(height / 300, 6),
        },
        "reading_order_index": reading_order_index,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "raw_text": text,
        "normalized_text": text,
        "spans": [{"span_type": "TEXT", "text": text}],
    }


if __name__ == "__main__":
    unittest.main()
