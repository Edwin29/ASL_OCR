import unittest
from pathlib import Path

from document_parser.assets.audit import analyze_zip, build_audit, detect_project_root, find_assets
from document_parser.assets.render import parse_page_spec


class AssetAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = detect_project_root(Path(__file__).resolve())
        cls.assets = find_assets(cls.project_root)

    def test_zip_has_160_canonical_pages_and_three_extras(self):
        zip_info = analyze_zip(self.assets.zip_path)
        self.assertEqual(zip_info["canonical_page_count"], 160)
        self.assertEqual(zip_info["canonical_page_min"], 1)
        self.assertEqual(zip_info["canonical_page_max"], 160)
        self.assertEqual(zip_info["missing_pages"], [])
        self.assertEqual(len(zip_info["duplicate_or_extra_files"]), 3)

    def test_manifest_marks_zip_pages_low_quality(self):
        _audit, manifest = build_audit(self.project_root)
        self.assertEqual(manifest["page_count"], 160)
        self.assertTrue(all(page["quality_status"] == "LOW_QUALITY" for page in manifest["pages"]))

    def test_page_spec_parser(self):
        self.assertEqual(parse_page_spec("3,4,8,12-14"), [3, 4, 8, 12, 13, 14])


if __name__ == "__main__":
    unittest.main()

