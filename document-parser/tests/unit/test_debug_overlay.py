import tempfile
import unittest
from pathlib import Path

from PIL import Image

from document_parser.debug import render_document_overlays


class DebugOverlayTests(unittest.TestCase):
    def test_renders_page_ir_overlay_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images_dir = root / "images"
            output_dir = root / "overlays"
            images_dir.mkdir()
            image_path = images_dir / "sample_p001.png"
            Image.new("RGB", (120, 90), "white").save(image_path)

            results = render_document_overlays(valid_payload(), images_dir, output_dir)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].page_id, "p001")
            self.assertEqual(results[0].node_count, 1)
            self.assertEqual(results[0].quality_status, "PASS")
            self.assertTrue(Path(results[0].output_path).exists())

            with Image.open(results[0].output_path) as overlay:
                self.assertEqual(overlay.size, (120, 90))

    def test_filters_page_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images_dir = root / "images"
            output_dir = root / "overlays"
            images_dir.mkdir()
            Image.new("RGB", (120, 90), "white").save(images_dir / "sample_p001.png")

            results = render_document_overlays(valid_payload(), images_dir, output_dir, page_ids={"p999"})

            self.assertEqual(results, [])

    def test_renders_split_ocr_draft_nodes_with_distinct_color(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images_dir = root / "images"
            output_dir = root / "overlays"
            images_dir.mkdir()
            Image.new("RGB", (120, 90), "white").save(images_dir / "sample_p001.png")

            results = render_document_overlays(split_draft_payload(), images_dir, output_dir)

            with Image.open(results[0].output_path) as overlay:
                self.assertEqual(overlay.getpixel((10, 27)), (214, 84, 0))
                self.assertEqual(overlay.getpixel((70, 27)), (98, 98, 98))


def valid_payload():
    return {
        "pages": [
            {
                "page_id": "p001",
                "nodes": [
                    {
                        "node_id": "p001-n001",
                        "content_type": "TEXT",
                        "bbox": {"x": 10, "y": 15, "width": 40, "height": 12},
                    }
                ],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }
        ]
    }


def split_draft_payload():
    return {
        "pages": [
            {
                "page_id": "p001",
                "nodes": [
                    {
                        "node_id": "p001-s001",
                        "content_type": "TEXT",
                        "bbox": {"x": 10, "y": 15, "width": 20, "height": 12},
                        "layout": {"is_split_ocr_replacement_draft": True},
                    },
                    {
                        "node_id": "p001-n001",
                        "content_type": "TEXT",
                        "bbox": {"x": 70, "y": 15, "width": 20, "height": 12},
                        "layout": {"split_ocr_replaced_by_node_ids": ["p001-s001"]},
                    },
                ],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }
        ]
    }


if __name__ == "__main__":
    unittest.main()
