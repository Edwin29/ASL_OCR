import tempfile
import unittest
from pathlib import Path

from PIL import Image

from document_parser.structure import export_barrier_split_work_units
from document_parser.structure.barrier_splits import intersection_bbox


class LayoutBarrierSplitTests(unittest.TestCase):
    def test_intersection_bbox(self):
        box = intersection_bbox(
            {"x": 20, "y": 10, "width": 80, "height": 10},
            {"x": 60, "y": 0, "width": 50, "height": 30},
        )

        self.assertEqual(box, {"x": 60, "y": 10, "width": 40, "height": 10})

    def test_exports_split_work_units_for_crossing_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "images"
            output_dir = root / "splits"
            images_dir.mkdir()
            Image.new("RGB", (200, 120), "white").save(images_dir / "book_p102.png")

            manifest = export_barrier_split_work_units(
                crossing_page_ir_fixture(),
                images_dir=images_dir,
                output_dir=output_dir,
                padding=4,
            )

            units = manifest["pages"][0]["work_units"]
            self.assertEqual(manifest["work_unit_count"], 2)
            self.assertEqual([unit["barrier_node_id"] for unit in units], ["p102-structure-left", "p102-structure-right"])
            self.assertEqual(units[0]["intersection_bbox"], {"x": 20.0, "y": 30.0, "width": 60.0, "height": 12.0})
            self.assertEqual(units[1]["intersection_bbox"], {"x": 100.0, "y": 30.0, "width": 60.0, "height": 12.0})
            for unit in units:
                self.assertTrue(Path(unit["crop_path"]).exists())


def crossing_page_ir_fixture():
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "validation_summary": {},
        "pages": [
            {
                "page_id": "p102",
                "page_geometry": {"width": 200, "height": 120},
                "nodes": [
                    text_node(),
                    barrier_node("p102-structure-left", 10, 20, 70, 50),
                    barrier_node("p102-structure-right", 100, 20, 70, 50),
                ],
                "reading_order": ["p102-n001"],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }
        ],
    }


def text_node():
    return {
        "node_id": "p102-n001",
        "content_type": "TEXT",
        "bbox": {"x": 20, "y": 30, "width": 140, "height": 12},
        "normalized_bbox": {"x": 0.1, "y": 0.25, "width": 0.7, "height": 0.1},
        "reading_order_index": 0,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "normalized_text": "left text right text",
        "layout": {
            "layout_barrier_crossing_candidate": ["p102-structure-left", "p102-structure-right"],
        },
    }


def barrier_node(node_id, x, y, width, height):
    return {
        "node_id": node_id,
        "content_type": "UNKNOWN",
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "normalized_bbox": {"x": x / 200, "y": y / 120, "width": width / 200, "height": height / 120},
        "confidence": 0.9,
        "source_engine": "fixture-layout",
        "issues": [],
        "layout": {
            "is_structure_region_candidate": True,
            "is_layout_barrier": True,
            "structure_label": "PROBLEM_BOX_CANDIDATE",
            "layout_barrier_role": "problem_region_boundary",
        },
    }


if __name__ == "__main__":
    unittest.main()
