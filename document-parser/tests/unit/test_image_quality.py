import unittest
from pathlib import Path

from document_parser.assets.audit import detect_project_root, find_assets
from document_parser.preprocess.quality import (
    ImageQualityGate,
    evaluate_rendered_pages,
    evaluate_zip_pages,
    parse_page_spec,
)


class ImageQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = detect_project_root(Path(__file__).resolve())
        cls.package_root = cls.project_root / "document-parser"
        cls.assets = find_assets(cls.project_root)

    def test_zip_page_is_low_quality(self):
        reports = evaluate_zip_pages(self.assets.zip_path, [3])
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].status, "LOW_QUALITY")
        self.assertEqual(reports[0].width, 584)
        self.assertEqual(reports[0].height, 737)
        self.assertIn("LOW_RESOLUTION", {issue.code for issue in reports[0].issues})

    def test_rendered_pages_pass_or_need_only_correction(self):
        reports = evaluate_rendered_pages(self.package_root / "data" / "pages_pdf300")
        self.assertGreaterEqual(len(reports), 1)
        statuses = {report.status for report in reports}
        self.assertTrue(statuses <= {"PASS", "PASS_WITH_CORRECTION"})
        self.assertTrue(all(report.width == 2434 and report.height == 3071 for report in reports))

    def test_quality_gate_does_not_mutate_source(self):
        image_path = self.package_root / "data" / "pages_pdf300" / "ebs_2027_math1_p008.png"
        before = image_path.stat().st_mtime_ns
        report = ImageQualityGate().evaluate_path(image_path)
        after = image_path.stat().st_mtime_ns
        self.assertEqual(before, after)
        self.assertIn(report.status, {"PASS", "PASS_WITH_CORRECTION"})

    def test_page_spec_parser(self):
        self.assertEqual(parse_page_spec("3,4,8-10"), [3, 4, 8, 9, 10])


if __name__ == "__main__":
    unittest.main()

