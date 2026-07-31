import tempfile
import unittest
from pathlib import Path

from PIL import Image

from document_parser.ocr.base import BBox, OcrPageResult, OcrToken
from document_parser.structure import recognize_barrier_split_work_units
from document_parser.structure.barrier_split_ocr import resolve_crop_path


class LayoutBarrierSplitOcrTests(unittest.TestCase):
    def test_recognizes_split_work_units_with_source_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            crop_dir = root / "crops"
            crop_dir.mkdir()
            Image.new("RGB", (80, 24), "white").save(crop_dir / "left.png")
            Image.new("RGB", (80, 24), "white").save(crop_dir / "right.png")

            manifest = split_manifest_fixture(root)
            ocr_manifest = recognize_barrier_split_work_units(
                manifest,
                adapter=EchoPathOcrAdapter(),
                path_base=root,
            )

            units = ocr_manifest["pages"][0]["recognized_work_units"]
            self.assertEqual(ocr_manifest["mode"], "layout_barrier_split_crop_reocr")
            self.assertEqual(ocr_manifest["work_unit_count"], 2)
            self.assertEqual(ocr_manifest["engine_manifest"]["ocr_engine"], "fixture-echo-path")
            self.assertEqual(units[0]["source_text_node_id"], "p102-n004")
            self.assertEqual(units[0]["barrier_node_id"], "p102-structure-left")
            self.assertEqual(units[0]["recognized_text"], "left")
            self.assertEqual(units[1]["recognized_text"], "right")
            self.assertEqual(units[1]["token_count"], 1)
            self.assertEqual(units[1]["tokens"][0]["bbox"], {"x": 1, "y": 2, "width": 3, "height": 4})

    def test_resolves_relative_crop_paths_against_path_base(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.assertEqual(resolve_crop_path("crops/page.png", root), (root / "crops" / "page.png").resolve())


class EchoPathOcrAdapter:
    engine_id = "fixture-echo-path"
    engine_version = "0.1.0"

    def recognize(self, image):
        return OcrPageResult(
            page_id=image.page_id,
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            tokens=[
                OcrToken(
                    text=image.path.stem,
                    bbox=BBox(x=1, y=2, width=3, height=4),
                    confidence=0.95,
                )
            ],
            raw_result={"status": "fixture"},
            issues=[],
        )


def split_manifest_fixture(root: Path):
    return {
        "split_manifest_version": 1,
        "mode": "layout_barrier_crossing_split_crops",
        "pages": [
            {
                "page_id": "p102",
                "work_units": [
                    {
                        "page_id": "p102",
                        "source_text_node_id": "p102-n004",
                        "barrier_node_id": "p102-structure-left",
                        "structure_label": "PROBLEM_BOX_CANDIDATE",
                        "layout_barrier_role": "problem_region_boundary",
                        "crop_path": str(Path("crops") / "left.png"),
                        "source_text": "joined original",
                        "source_text_bbox": {"x": 20, "y": 30, "width": 140, "height": 12},
                        "barrier_bbox": {"x": 10, "y": 20, "width": 70, "height": 50},
                        "intersection_bbox": {"x": 20, "y": 30, "width": 60, "height": 12},
                        "crop_bbox": {"x": 16, "y": 26, "width": 68, "height": 20},
                    },
                    {
                        "page_id": "p102",
                        "source_text_node_id": "p102-n004",
                        "barrier_node_id": "p102-structure-right",
                        "structure_label": "PROBLEM_BOX_CANDIDATE",
                        "layout_barrier_role": "problem_region_boundary",
                        "crop_path": str(root / "crops" / "right.png"),
                        "source_text": "joined original",
                    },
                ],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
