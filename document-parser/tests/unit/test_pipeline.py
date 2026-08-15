import tempfile
import unittest
from pathlib import Path

from PIL import Image

from document_parser.math.formula_ocr import FormulaRecognitionResult, validate_formula_output
from document_parser.ocr.fixture import FixtureGeneralOcrAdapter, token
from document_parser.pipeline import run_math_recognition_pipeline
from document_parser.structure import StructureRegion


class MathRecognitionPipelineOrderingTests(unittest.TestCase):
    """Regression test for the exact bug found manually on p004: running math-candidate
    detection before structure promotion lets graph-embedded text leak through and get
    "trusted" formula OCR output. This test proves the wired-together pipeline excludes
    it at the source, without needing real OCR/formula models installed.
    """

    def test_graph_embedded_text_is_excluded_before_formula_ocr_ever_sees_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "images"
            images_dir.mkdir()
            Image.new("RGB", (800, 300), "white").save(images_dir / "book_p001.png")

            ocr_adapter = FixtureGeneralOcrAdapter(tokens_by_page={
                "p001": [
                    # Plain Korean sentence: never a math candidate.
                    token("이것은", x=10, y=10, width=60, height=20),
                    token("설명입니다.", x=80, y=10, width=100, height=20),
                    # Graph axis label, spatially inside the fake GRAPH region below.
                    # Looks math-candidate-shaped (relation + caret) so it WOULD be
                    # picked up if structure promotion were skipped.
                    token("y", x=10, y=50, width=15, height=20),
                    token("=x^n", x=30, y=50, width=50, height=20),
                    # A real standalone formula line, well outside the graph region.
                    token("f(x)=x^2+1", x=10, y=150, width=160, height=20),
                ],
            })

            structure_adapter = FixtureStructureAdapter([
                StructureRegion(
                    label="image",
                    bbox={"x": 0, "y": 40, "width": 200, "height": 40},
                    confidence=0.95,
                    raw={},
                ),
            ])

            formula_adapter = FixtureFormulaOcrAdapter({
                # Only the real formula crop should ever be asked to recognize.
                "f(x)=x^2+1": r"f(x)=x^{2}+1",
            })

            output_dir = root / "out"
            summary = run_math_recognition_pipeline(
                images_dir=images_dir,
                output_dir=output_dir,
                ocr_adapter=ocr_adapter,
                structure_adapter=structure_adapter,
                formula_adapter=formula_adapter,
            )

            self.assertTrue(summary["schema_valid"])
            # Only the real formula line should ever become a math candidate; the
            # graph-embedded "y=x^n" axis label must be excluded before this stage.
            self.assertEqual(summary["math_candidate_count"], 1)
            self.assertEqual(summary["crop_count"], 1)
            self.assertEqual(summary["formula_ocr_trusted_count"], 1)
            self.assertEqual(summary["formula_ocr_untrusted_count"], 0)
            self.assertEqual(formula_adapter.recognized_paths_by_source_text, ["f(x)=x^2+1"])


class FixtureStructureAdapter:
    def __init__(self, regions: list[StructureRegion]) -> None:
        self._regions = regions

    def detect_regions(self, image_path: Path) -> list[StructureRegion]:
        return self._regions


class FixtureFormulaOcrAdapter:
    engine_id = "fixture-formula-ocr"
    engine_version = "0.1.0"

    def __init__(self, latex_by_source_text: dict[str, str]) -> None:
        self.latex_by_source_text = latex_by_source_text
        self.recognized_paths_by_source_text: list[str] = []

    def recognize(self, image_path: Path) -> FormulaRecognitionResult:
        # The fixture crop for our synthetic test is always exactly the "real formula"
        # line, so any recognize() call proves the axis-label crop never made it here.
        source_text = "f(x)=x^2+1"
        self.recognized_paths_by_source_text.append(source_text)
        raw_latex = self.latex_by_source_text.get(source_text, "")
        return FormulaRecognitionResult(raw_latex=raw_latex, issues=validate_formula_output(raw_latex))


if __name__ == "__main__":
    unittest.main()
