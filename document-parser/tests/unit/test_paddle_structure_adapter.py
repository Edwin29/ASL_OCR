import unittest
from pathlib import Path

from document_parser.structure.paddle_structure_adapter import (
    PaddleStructureRegionAdapter,
    StructureRegion,
    apply_structure_regions_to_document,
    structure_regions_from_results,
)
from document_parser.structure.domain_mapping import map_region_to_ebs_math_domain
from document_parser.structure.barriers import apply_layout_barriers
from document_parser.structure.linking import link_structure_regions_to_text
from document_parser.structure.promotion import promote_structure_candidates_to_primary_order
from document_parser.validation import validate_document_ir


class FakeStructureReader:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def predict(self, image):
        self.calls.append(image)
        return self.results


class PaddleStructureAdapterTests(unittest.TestCase):
    def test_extracts_layout_regions_from_ppstructure_json(self):
        regions = structure_regions_from_results([structure_result()])

        self.assertEqual(len(regions), 3)
        self.assertEqual(regions[0].label, "table")
        self.assertEqual(regions[0].bbox, {"x": 10.0, "y": 20.0, "width": 90.0, "height": 20.0})
        self.assertEqual(regions[1].label, "image")
        self.assertEqual(regions[2].label, "formula")

    def test_adapter_uses_reader_predict(self):
        reader = FakeStructureReader([structure_result()])
        adapter = PaddleStructureRegionAdapter(reader=reader)

        regions = adapter.detect_regions(Path("p004.png"))

        self.assertEqual(len(regions), 3)
        self.assertEqual(reader.calls, ["p004.png"])

    def test_applies_structure_regions_as_experimental_page_ir_nodes(self):
        payload = baseline_payload()
        regions = structure_regions_from_results([structure_result()])

        processed = apply_structure_regions_to_document(payload, {"p004": regions})
        page = processed["pages"][0]
        structure_nodes = [
            node for node in page["nodes"]
            if node.get("source_engine") == "paddleocr-ppstructurev3-layout"
        ]

        self.assertEqual(len(structure_nodes), 3)
        self.assertEqual(structure_nodes[0]["content_type"], "TABLE")
        self.assertEqual(structure_nodes[1]["content_type"], "UNSUPPORTED_VISUAL")
        self.assertEqual(structure_nodes[2]["content_type"], "MATH")
        self.assertTrue(structure_nodes[0]["layout"]["is_structure_region_candidate"])
        self.assertEqual(structure_nodes[0]["layout"]["structure_label"], "TABLE_CANDIDATE")
        self.assertEqual(structure_nodes[1]["layout"]["structure_label"], "GRAPH_OR_DIAGRAM_CANDIDATE")
        self.assertEqual(structure_nodes[2]["layout"]["structure_label"], "DISPLAY_FORMULA_CANDIDATE")
        self.assertTrue(validate_document_ir(processed)["schema_valid"])

    def test_maps_large_table_like_region_to_problem_box_candidate(self):
        region = StructureRegion(
            label="table",
            bbox={"x": 100.0, "y": 300.0, "width": 950.0, "height": 620.0},
            confidence=0.96,
            raw={},
        )

        mapped = map_region_to_ebs_math_domain(region, page_width=2434, page_height=3071)

        self.assertEqual(mapped.domain_label, "PROBLEM_BOX_CANDIDATE")
        self.assertEqual(mapped.content_type, "UNKNOWN")

    def test_maps_compact_table_like_region_to_table_candidate(self):
        region = StructureRegion(
            label="table",
            bbox={"x": 300.0, "y": 900.0, "width": 1300.0, "height": 220.0},
            confidence=0.96,
            raw={},
        )

        mapped = map_region_to_ebs_math_domain(region, page_width=2434, page_height=3071)

        self.assertEqual(mapped.domain_label, "TABLE_CANDIDATE")
        self.assertEqual(mapped.content_type, "TABLE")

    def test_links_structure_candidates_to_contained_text_nodes(self):
        page = linked_page_fixture()

        processed = link_structure_regions_to_text(page)
        table_node = next(node for node in processed["nodes"] if node["node_id"] == "p004-structure-r001")
        graph_node = next(node for node in processed["nodes"] if node["node_id"] == "p004-structure-r002")
        table_text = next(node for node in processed["nodes"] if node["node_id"] == "p004-n001")
        outside_text = next(node for node in processed["nodes"] if node["node_id"] == "p004-n003")

        self.assertEqual(table_node["contained_text_nodes"], ["p004-n001"])
        self.assertEqual(graph_node["contained_text_nodes"], ["p004-n002"])
        self.assertEqual(table_text["layout"]["primary_parent_structure_node_id"], "p004-structure-r001")
        self.assertNotIn("parent_structure_node_ids", outside_text.get("layout", {}))
        self.assertIn("STRUCTURE_TEXT_LINKS_ADDED", {issue["code"] for issue in processed["parse_issues"]})

    def test_promotes_table_and_graph_candidates_into_primary_reading_order(self):
        linked = link_structure_regions_to_text(linked_page_fixture())

        promoted = promote_structure_candidates_to_primary_order(linked)
        table_node = next(node for node in promoted["nodes"] if node["node_id"] == "p004-structure-r001")
        graph_node = next(node for node in promoted["nodes"] if node["node_id"] == "p004-structure-r002")
        table_text = next(node for node in promoted["nodes"] if node["node_id"] == "p004-n001")

        self.assertEqual(promoted["reading_order"], ["p004-structure-r001", "p004-structure-r002", "p004-n003"])
        self.assertEqual(table_node["embedded_text_nodes"], ["p004-n001"])
        self.assertEqual(graph_node["embedded_text_nodes"], ["p004-n002"])
        self.assertEqual(table_text["parent_structure_node_id"], "p004-structure-r001")
        self.assertFalse(table_text["is_primary_reading_order_candidate"])
        self.assertTrue(validate_document_ir(wrap_page(promoted))["schema_valid"])

    def test_does_not_promote_problem_box_candidate_by_default(self):
        page = linked_page_fixture()
        page["nodes"][3]["content_type"] = "UNKNOWN"
        page["nodes"][3]["layout"]["structure_label"] = "PROBLEM_BOX_CANDIDATE"
        linked = link_structure_regions_to_text(page)

        promoted = promote_structure_candidates_to_primary_order(linked)

        self.assertIn("p004-n001", promoted["reading_order"])
        self.assertIn("p004-structure-r001", promoted["reading_order"])
        self.assertNotIn("embedded_text_nodes", promoted["nodes"][3])

    def test_can_promote_problem_box_candidate_when_explicitly_requested(self):
        page = linked_page_fixture()
        page["nodes"][3]["content_type"] = "UNKNOWN"
        page["nodes"][3]["layout"]["structure_label"] = "PROBLEM_BOX_CANDIDATE"
        linked = link_structure_regions_to_text(page)

        promoted = promote_structure_candidates_to_primary_order(
            linked,
            promotable_labels={"PROBLEM_BOX_CANDIDATE"},
        )
        problem_node = next(node for node in promoted["nodes"] if node["node_id"] == "p004-structure-r001")

        self.assertEqual(problem_node["embedded_text_nodes"], ["p004-n001"])
        self.assertNotIn("p004-n001", promoted["reading_order"])
        self.assertIn("p004-structure-r001", promoted["reading_order"])
        self.assertTrue(validate_document_ir(wrap_page(promoted))["schema_valid"])

    def test_problem_box_preview_can_use_geometry_order(self):
        linked = link_structure_regions_to_text(problem_box_preview_fixture())

        promoted = promote_structure_candidates_to_primary_order(
            linked,
            promotable_labels={"PROBLEM_BOX_CANDIDATE"},
            order_mode="geometry",
        )

        self.assertEqual(
            promoted["reading_order"][:4],
            ["p102-title", "p102-left-top", "p102-left-bottom", "p102-right-top"],
        )

    def test_problem_box_preview_links_nearby_caption_candidates(self):
        linked = link_structure_regions_to_text(problem_box_caption_fixture())

        promoted = promote_structure_candidates_to_primary_order(
            linked,
            promotable_labels={"PROBLEM_BOX_CANDIDATE"},
            order_mode="geometry",
        )
        left_box = next(node for node in promoted["nodes"] if node["node_id"] == "p102-left-box")
        right_box = next(node for node in promoted["nodes"] if node["node_id"] == "p102-right-box")
        left_caption = next(node for node in promoted["nodes"] if node["node_id"] == "p102-left-caption")
        far_caption = next(node for node in promoted["nodes"] if node["node_id"] == "p102-far-caption")

        self.assertEqual(left_box["layout"]["caption_structure_node_ids"], ["p102-left-caption"])
        self.assertEqual(right_box["layout"]["caption_structure_node_ids"], ["p102-right-caption"])
        self.assertEqual(left_caption["layout"]["parent_problem_box_structure_node_id"], "p102-left-box")
        self.assertNotIn("parent_problem_box_structure_node_id", far_caption["layout"])
        self.assertIn("PROBLEM_BOX_CAPTIONS_LINKED", {issue["code"] for issue in promoted["parse_issues"]})
        self.assertTrue(validate_document_ir(wrap_page(promoted))["schema_valid"])

    def test_marks_structure_regions_as_layout_barriers(self):
        linked = link_structure_regions_to_text(linked_page_fixture())

        processed = apply_layout_barriers(linked)
        table_node = next(node for node in processed["nodes"] if node["node_id"] == "p004-structure-r001")
        graph_node = next(node for node in processed["nodes"] if node["node_id"] == "p004-structure-r002")
        table_text = next(node for node in processed["nodes"] if node["node_id"] == "p004-n001")

        self.assertTrue(table_node["layout"]["is_layout_barrier"])
        self.assertEqual(table_node["layout"]["layout_barrier_role"], "table_region_boundary")
        self.assertEqual(graph_node["layout"]["layout_barrier_role"], "visual_region_boundary")
        self.assertEqual(table_text["layout"]["primary_layout_barrier_node_id"], "p004-structure-r001")
        self.assertIn("LAYOUT_BARRIERS_APPLIED", {issue["code"] for issue in processed["parse_issues"]})
        self.assertTrue(validate_document_ir(wrap_page(processed))["schema_valid"])

    def test_reports_text_crossing_multiple_layout_barriers(self):
        page = barrier_crossing_fixture()

        processed = apply_layout_barriers(page)
        crossing_text = next(node for node in processed["nodes"] if node["node_id"] == "p004-n001")

        self.assertEqual(
            crossing_text["layout"]["layout_barrier_crossing_candidate"],
            ["p004-structure-r001", "p004-structure-r002"],
        )
        self.assertIn("LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE", {issue["code"] for issue in processed["parse_issues"]})


def structure_result():
    return {
        "layout_det_res": {
            "boxes": [
                {"label": "table", "score": 0.91, "coordinate": [10, 20, 100, 40]},
                {"label": "image", "score": 0.82, "coordinate": [[120, 30], [180, 30], [180, 100], [120, 100]]},
                {"block_label": "formula", "confidence": 0.75, "bbox": [20, 150, 80, 190]},
            ]
        }
    }


def baseline_payload():
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "validation_summary": {},
        "pages": [
            {
                "page_id": "p004",
                "page_geometry": {"width": 200, "height": 300},
                "nodes": [
                    {
                        "node_id": "p004-n001",
                        "content_type": "TEXT",
                        "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
                        "normalized_bbox": {"x": 0.005, "y": 0.006667, "width": 0.015, "height": 0.013333},
                        "reading_order_index": 0,
                        "confidence": 0.9,
                        "source_engine": "fixture",
                        "issues": [],
                        "normalized_text": "text",
                    }
                ],
                "reading_order": ["p004-n001"],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }
        ],
    }


def linked_page_fixture():
    return {
        "page_id": "p004",
        "page_geometry": {"width": 200, "height": 300},
        "nodes": [
            text_node("p004-n001", 20, 30, 40, 10),
            text_node("p004-n002", 130, 45, 35, 12),
            text_node("p004-n003", 10, 250, 20, 10),
            structure_node("p004-structure-r001", "TABLE", "TABLE_CANDIDATE", 10, 20, 90, 40),
            structure_node("p004-structure-r002", "UNSUPPORTED_VISUAL", "GRAPH_OR_DIAGRAM_CANDIDATE", 120, 30, 60, 70),
        ],
        "reading_order": ["p004-n001", "p004-n002", "p004-n003", "p004-structure-r001", "p004-structure-r002"],
        "parse_issues": [],
        "quality_report": {"status": "PASS"},
    }


def problem_box_preview_fixture():
    return {
        "page_id": "p102",
        "page_geometry": {"width": 200, "height": 300},
        "nodes": [
            text_node_with_index("p102-title", 10, 5, 100, 10, 0),
            text_node_with_index("p102-rtext", 130, 50, 30, 10, 1),
            text_node_with_index("p102-ltext1", 20, 50, 30, 10, 2),
            text_node_with_index("p102-ltext2", 20, 170, 30, 10, 3),
            structure_node("p102-right-top", "UNKNOWN", "PROBLEM_BOX_CANDIDATE", 120, 40, 60, 60),
            structure_node("p102-left-top", "UNKNOWN", "PROBLEM_BOX_CANDIDATE", 10, 40, 60, 60),
            structure_node("p102-left-bottom", "UNKNOWN", "PROBLEM_BOX_CANDIDATE", 10, 160, 60, 60),
        ],
        "reading_order": ["p102-title", "p102-rtext", "p102-ltext1", "p102-ltext2", "p102-right-top", "p102-left-top", "p102-left-bottom"],
        "parse_issues": [],
        "quality_report": {"status": "PASS"},
    }


def problem_box_caption_fixture():
    return {
        "page_id": "p102",
        "page_geometry": {"width": 200, "height": 300},
        "nodes": [
            text_node_with_index("p102-title", 10, 5, 100, 10, 0),
            text_node_with_index("p102-left-text", 20, 50, 30, 10, 1),
            text_node_with_index("p102-right-text", 130, 50, 30, 10, 2),
            structure_node("p102-left-caption", "UNKNOWN", "VISUAL_OR_PROBLEM_CAPTION_CANDIDATE", 10, 25, 50, 10),
            structure_node("p102-right-caption", "UNKNOWN", "VISUAL_OR_PROBLEM_CAPTION_CANDIDATE", 120, 25, 50, 10),
            structure_node("p102-far-caption", "UNKNOWN", "VISUAL_OR_PROBLEM_CAPTION_CANDIDATE", 10, 120, 50, 10),
            structure_node("p102-left-box", "UNKNOWN", "PROBLEM_BOX_CANDIDATE", 10, 40, 60, 60),
            structure_node("p102-right-box", "UNKNOWN", "PROBLEM_BOX_CANDIDATE", 120, 40, 60, 60),
        ],
        "reading_order": [
            "p102-title",
            "p102-left-caption",
            "p102-right-caption",
            "p102-far-caption",
            "p102-left-text",
            "p102-right-text",
            "p102-left-box",
            "p102-right-box",
        ],
        "parse_issues": [],
        "quality_report": {"status": "PASS"},
    }


def barrier_crossing_fixture():
    return {
        "page_id": "p004",
        "page_geometry": {"width": 200, "height": 300},
        "nodes": [
            text_node_with_index("p004-n001", 25, 30, 85, 10, 0),
            structure_node("p004-structure-r001", "TABLE", "TABLE_CANDIDATE", 10, 20, 70, 40),
            structure_node("p004-structure-r002", "UNSUPPORTED_VISUAL", "GRAPH_OR_DIAGRAM_CANDIDATE", 70, 20, 70, 40),
        ],
        "reading_order": ["p004-n001", "p004-structure-r001", "p004-structure-r002"],
        "parse_issues": [],
        "quality_report": {"status": "PASS"},
    }


def wrap_page(page):
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "validation_summary": {},
        "pages": [page],
    }


def text_node(node_id, x, y, width, height):
    return text_node_with_index(node_id, x, y, width, height, int(node_id.rsplit("n", 1)[1]) - 1)


def text_node_with_index(node_id, x, y, width, height, reading_order_index):
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "normalized_bbox": {"x": x / 200, "y": y / 300, "width": width / 200, "height": height / 300},
        "reading_order_index": reading_order_index,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "normalized_text": node_id,
        "layout": {},
    }


def structure_node(node_id, content_type, structure_label, x, y, width, height):
    return {
        "node_id": node_id,
        "content_type": content_type,
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "normalized_bbox": {"x": x / 200, "y": y / 300, "width": width / 200, "height": height / 300},
        "reading_order_index": 3 if node_id.endswith("001") else 4,
        "confidence": 0.9,
        "source_engine": "paddleocr-ppstructurev3-layout",
        "issues": [],
        "layout": {
            "is_structure_region_candidate": True,
            "structure_label": structure_label,
        },
    }


if __name__ == "__main__":
    unittest.main()
