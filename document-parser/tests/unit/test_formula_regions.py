import tempfile
import unittest
from pathlib import Path

from PIL import Image

from document_parser.math import export_formula_region_crops


class FormulaRegionCropTests(unittest.TestCase):
    def test_exports_one_crop_per_formula_region_inside_an_unsplit_candidate_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "images"
            crops_dir = root / "crops"
            images_dir.mkdir()
            Image.new("RGB", (400, 200), "white").save(images_dir / "book_p008.png")

            manifest = export_formula_region_crops(
                page_ir_fixture(),
                images_dir=images_dir,
                output_dir=crops_dir,
                padding=2,
            )

            crops = manifest["pages"][0]["crops"]
            self.assertEqual(manifest["crop_count"], 2)
            self.assertTrue(all(crop["node_id"] == "p008-n001" for crop in crops))
            # left-to-right order, matching reading order within the line
            self.assertEqual([crop["region_index"] for crop in crops], [1, 2])
            self.assertEqual([crop["region_node_id"] for crop in crops], ["p008-structure-r001", "p008-structure-r002"])
            for crop in crops:
                self.assertTrue(Path(crop["crop_path"]).exists())

    def test_skips_nodes_already_split_by_token_based_spans(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "images"
            crops_dir = root / "crops"
            images_dir.mkdir()
            Image.new("RGB", (400, 200), "white").save(images_dir / "book_p008.png")

            payload = page_ir_fixture()
            # Simulate a node that math/spans.py already split successfully.
            payload["pages"][0]["nodes"][0]["layout"]["math_span_count"] = 1

            manifest = export_formula_region_crops(payload, images_dir=images_dir, output_dir=crops_dir, padding=2)

            self.assertEqual(manifest["crop_count"], 0)

    def test_skips_candidate_with_no_overlapping_formula_region(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "images"
            crops_dir = root / "crops"
            images_dir.mkdir()
            Image.new("RGB", (400, 200), "white").save(images_dir / "book_p008.png")

            payload = page_ir_fixture()
            # Move the candidate line far away from both formula regions.
            payload["pages"][0]["nodes"][0]["bbox"] = {"x": 10, "y": 150, "width": 100, "height": 20}

            manifest = export_formula_region_crops(payload, images_dir=images_dir, output_dir=crops_dir, padding=2)

            self.assertEqual(manifest["crop_count"], 0)


def page_ir_fixture():
    candidate_node = {
        "node_id": "p008-n001",
        "content_type": "TEXT",
        "bbox": {"x": 10, "y": 10, "width": 300, "height": 30},
        "normalized_bbox": {"x": 0.025, "y": 0.05, "width": 0.75, "height": 0.15},
        "reading_order_index": 0,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "raw_text": "존재하고 x=na 또는 x=-na이다.",
        "normalized_text": "존재하고 x=na 또는 x=-na이다.",
        "spans": [{"span_type": "TEXT", "text": "존재하고 x=na 또는 x=-na이다."}],
        "layout": {
            "math_candidate": {"is_candidate": True, "score": 6},
        },
    }
    region_1 = {
        "node_id": "p008-structure-r001",
        "content_type": "MATH",
        "bbox": {"x": 60, "y": 12, "width": 40, "height": 26},
        "normalized_bbox": {"x": 0.15, "y": 0.06, "width": 0.1, "height": 0.13},
        "reading_order_index": 1,
        "confidence": 0.9,
        "source_engine": "paddleocr-ppstructurev3-layout",
        "issues": [],
        "layout": {"structure_label": "DISPLAY_FORMULA_CANDIDATE"},
    }
    region_2 = {
        "node_id": "p008-structure-r002",
        "content_type": "MATH",
        "bbox": {"x": 200, "y": 12, "width": 50, "height": 26},
        "normalized_bbox": {"x": 0.5, "y": 0.06, "width": 0.125, "height": 0.13},
        "reading_order_index": 2,
        "confidence": 0.9,
        "source_engine": "paddleocr-ppstructurev3-layout",
        "issues": [],
        "layout": {"structure_label": "DISPLAY_FORMULA_CANDIDATE"},
    }
    nodes = [candidate_node, region_1, region_2]
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "validation_summary": {},
        "pages": [{
            "page_id": "p008",
            "page_geometry": {"width": 400, "height": 200},
            "nodes": nodes,
            "reading_order": ["p008-n001"],
            "parse_issues": [],
            "quality_report": {"status": "PASS"},
        }],
    }


if __name__ == "__main__":
    unittest.main()
