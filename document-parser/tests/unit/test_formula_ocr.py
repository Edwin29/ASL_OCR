import tempfile
import unittest
from pathlib import Path

from document_parser.math import FormulaRecognitionResult, recognize_math_candidate_crops
from document_parser.math.formula_ocr import validate_formula_output


class FormulaOutputValidationTests(unittest.TestCase):
    def test_accepts_clean_latex(self):
        issues = validate_formula_output(r"\sqrt[n]{a}\sqrt[n]{b}=\sqrt[n]{ab}")

        self.assertEqual(issues, [])

    def test_flags_empty_output(self):
        issues = validate_formula_output("")

        self.assertEqual({issue["code"] for issue in issues}, {"FORMULA_OCR_EMPTY_OUTPUT"})

    def test_flags_hangul_contamination(self):
        # Real observed failure: feeding a merged Korean+math line produced this kind
        # of garbage, force-fitting Korean glyphs into bogus LaTeX tokens.
        issues = validate_formula_output(r"x{=}{\sqrt[n]{a}}\circ] 吋")

        codes = {issue["code"] for issue in issues}
        self.assertIn("FORMULA_OCR_UNEXPECTED_SCRIPT", codes)
        self.assertTrue(all(issue["severity"] == "error" for issue in issues if issue["code"] == "FORMULA_OCR_UNEXPECTED_SCRIPT"))

    def test_flags_degenerate_repetition(self):
        # Real observed failure: a runaway repeated LaTeX fragment.
        garbage = r"\underline{\quad}" * 50
        issues = validate_formula_output(garbage)

        self.assertIn("FORMULA_OCR_DEGENERATE_REPETITION", {issue["code"] for issue in issues})

    def test_flags_overly_long_output(self):
        issues = validate_formula_output("x=" + "1" * 400)

        self.assertIn("FORMULA_OCR_OUTPUT_TOO_LONG", {issue["code"] for issue in issues})

    def test_clean_short_formula_has_no_false_positive_repetition_flag(self):
        # A legitimate repeated structure (e.g. binomial-like terms) should not trip
        # the degenerate-repetition guard just because it repeats briefly.
        issues = validate_formula_output(r"a+a+a")

        self.assertEqual(issues, [])


class RecognizeMathCandidateCropsTests(unittest.TestCase):
    def test_annotates_crops_with_trust_flag_and_resolves_relative_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "crops" / "p008").mkdir(parents=True)
            good_path = root / "crops" / "p008" / "p008-n001_span01_math_candidate.png"
            bad_path = root / "crops" / "p008" / "p008-n002_math_candidate.png"
            good_path.write_bytes(b"fake-png")
            bad_path.write_bytes(b"fake-png")

            manifest = {
                "mode": "math_candidate_crops",
                "page_count": 1,
                "pages": [{
                    "page_id": "p008",
                    "crops": [
                        {"node_id": "p008-n001", "crop_path": "crops/p008/p008-n001_span01_math_candidate.png", "text": "x=a"},
                        {"node_id": "p008-n002", "crop_path": "crops/p008/p008-n002_math_candidate.png", "text": "merged line"},
                    ],
                }],
            }

            adapter = FixtureFormulaOcrAdapter({
                str(good_path.resolve()): r"\sqrt[n]{a}",
                str(bad_path.resolve()): r"x{=}\circ] 吋",
            })

            recognized = recognize_math_candidate_crops(manifest, adapter=adapter, path_base=root)

            self.assertEqual(recognized["crop_count"], 2)
            self.assertEqual(recognized["trusted_crop_count"], 1)
            self.assertEqual(recognized["untrusted_crop_count"], 1)

            crops = recognized["pages"][0]["crops"]
            good_crop = next(c for c in crops if c["node_id"] == "p008-n001")
            bad_crop = next(c for c in crops if c["node_id"] == "p008-n002")

            self.assertTrue(good_crop["formula_ocr_trusted"])
            self.assertEqual(good_crop["recognized_formula"], r"\sqrt[n]{a}")
            self.assertEqual(good_crop["formula_ocr_issues"], [])

            self.assertFalse(bad_crop["formula_ocr_trusted"])
            self.assertIn(
                "FORMULA_OCR_UNEXPECTED_SCRIPT",
                {issue["code"] for issue in bad_crop["formula_ocr_issues"]},
            )
            # original manifest fields (like "text") are preserved alongside new ones
            self.assertEqual(bad_crop["text"], "merged line")

    def test_rejects_narrow_crop_even_when_output_looks_syntactically_clean(self):
        # Real observed failure: a single-variable region glued to a Korean particle
        # (e.g. the "n" in "n이") produced clean-looking but meaningless LaTeX like
        # "\mathcal{n}^{\circ}]" that no other guard catches.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "crops" / "p009").mkdir(parents=True)
            narrow_path = root / "crops" / "p009" / "p009-n001__formula_region_01.png"
            wide_path = root / "crops" / "p009" / "p009-n001__formula_region_02.png"
            narrow_path.write_bytes(b"fake-png")
            wide_path.write_bytes(b"fake-png")

            manifest = {
                "mode": "formula_region_fallback_crops",
                "page_count": 1,
                "pages": [{
                    "page_id": "p009",
                    "crops": [
                        {
                            "node_id": "p009-n001",
                            "crop_path": "crops/p009/p009-n001__formula_region_01.png",
                            "bbox": {"x": 370.4, "y": 898.5, "width": 62.9, "height": 40.5},
                        },
                        {
                            "node_id": "p009-n001",
                            "crop_path": "crops/p009/p009-n001__formula_region_02.png",
                            "bbox": {"x": 600.4, "y": 899.1, "width": 90.5, "height": 40.2},
                        },
                    ],
                }],
            }

            adapter = FixtureFormulaOcrAdapter({
                str(narrow_path.resolve()): r"\mathcal{n}^{\circ}]",
                str(wide_path.resolve()): r"a\geq0",
            })

            recognized = recognize_math_candidate_crops(manifest, adapter=adapter, path_base=root)

            crops = recognized["pages"][0]["crops"]
            narrow_crop = next(c for c in crops if "01" in c["crop_path"])
            wide_crop = next(c for c in crops if "02" in c["crop_path"])

            self.assertFalse(narrow_crop["formula_ocr_trusted"])
            self.assertIn("FORMULA_OCR_CROP_TOO_NARROW", {i["code"] for i in narrow_crop["formula_ocr_issues"]})
            self.assertTrue(wide_crop["formula_ocr_trusted"])


class FixtureFormulaOcrAdapter:
    engine_id = "fixture-formula-ocr"
    engine_version = "0.1.0"

    def __init__(self, latex_by_path: dict[str, str]) -> None:
        self.latex_by_path = latex_by_path

    def recognize(self, image_path: Path) -> FormulaRecognitionResult:
        raw_latex = self.latex_by_path.get(str(image_path.resolve()), "")
        from document_parser.math.formula_ocr import validate_formula_output

        return FormulaRecognitionResult(raw_latex=raw_latex, issues=validate_formula_output(raw_latex))


if __name__ == "__main__":
    unittest.main()
