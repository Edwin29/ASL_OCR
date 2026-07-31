import tempfile
import unittest
from pathlib import Path

from PIL import Image

from document_parser.math import export_math_candidate_crops
from document_parser.math.crops import padded_crop_box


class MathCandidateCropTests(unittest.TestCase):
    def test_padded_crop_box_clamps_to_image_bounds(self):
        crop_box = padded_crop_box(
            {"x": 2, "y": 3, "width": 20, "height": 10},
            image_width=30,
            image_height=30,
            padding=8,
        )

        self.assertEqual(crop_box, (0, 0, 30, 21))

    def test_exports_math_candidate_crops_in_reading_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "images"
            crops_dir = root / "crops"
            images_dir.mkdir()
            Image.new("RGB", (200, 100), "white").save(images_dir / "book_p008.png")

            manifest = export_math_candidate_crops(
                crop_page_ir_fixture(),
                images_dir=images_dir,
                output_dir=crops_dir,
                padding=4,
            )

            self.assertEqual(manifest["crop_count"], 2)
            self.assertEqual([crop["node_id"] for crop in manifest["pages"][0]["crops"]], ["p008-n002", "p008-n001"])
            for crop in manifest["pages"][0]["crops"]:
                self.assertTrue(Path(crop["crop_path"]).exists())
                self.assertGreater(crop["crop_bbox"]["width"], 0)
                self.assertGreater(crop["crop_bbox"]["height"], 0)


def crop_page_ir_fixture():
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "validation_summary": {},
        "pages": [
            {
                "page_id": "p008",
                "page_geometry": {"width": 200, "height": 100},
                "nodes": [
                    text_node("p008-n001", 60, 20, "f(x)=x^2+1"),
                    text_node("p008-n002", 10, 10, "x=1"),
                    text_node("p008-n003", 10, 60, "not candidate", candidate=False),
                ],
                "reading_order": ["p008-n002", "p008-n001", "p008-n003"],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }
        ],
    }


def text_node(node_id, x, y, text, candidate=True):
    layout = {}
    if candidate:
        layout["math_candidate"] = {
            "is_candidate": True,
            "score": 8,
            "candidate_kind": "display_or_expression",
            "reasons": ["relation_operator"],
        }
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": {"x": x, "y": y, "width": 40, "height": 12},
        "normalized_bbox": {"x": x / 200, "y": y / 100, "width": 0.2, "height": 0.12},
        "reading_order_index": 0,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "raw_text": text,
        "normalized_text": text,
        "spans": [{"span_type": "TEXT", "text": text}],
        "layout": layout,
    }


if __name__ == "__main__":
    unittest.main()
