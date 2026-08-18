import json
import unittest
from pathlib import Path

from document_parser.accessibility.adapters.page_ir_adapter import (
    PageIrCompatibilityError,
    check_compatibility_profile,
)
from document_parser.validation import validate_document_ir

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "accessibility"
FIXTURE_PAGE_IDS = ["p004", "p018", "p019", "p030", "p038", "p088"]


class PageIrFixtureTests(unittest.TestCase):
    def test_fixture_files_exist(self):
        for page_id in FIXTURE_PAGE_IDS:
            self.assertTrue((FIXTURE_DIR / f"{page_id}.json").is_file(), page_id)

    def test_committed_fixtures_are_schema_valid(self):
        for page_id in FIXTURE_PAGE_IDS:
            payload = load_fixture(page_id)
            self.assertTrue(payload["validation_summary"]["schema_valid"], page_id)
            # The stored summary must match a fresh run, not a stale snapshot.
            fresh = validate_document_ir(payload)
            self.assertEqual(fresh["schema_valid"], payload["validation_summary"]["schema_valid"], page_id)

    def test_committed_fixtures_pass_compatibility_profile(self):
        for page_id in FIXTURE_PAGE_IDS:
            payload = load_fixture(page_id)
            check_compatibility_profile(payload)  # must not raise

    def test_compatibility_profile_rejects_unknown_pipeline_mode(self):
        payload = load_fixture("p018")
        payload["engine_manifest"]["pipeline"]["mode"] = "legacy_token_pipeline"
        with self.assertRaises(PageIrCompatibilityError):
            check_compatibility_profile(payload)

    def test_compatibility_profile_rejects_missing_problem_unit_manifest(self):
        payload = load_fixture("p018")
        del payload["engine_manifest"]["problem_unit_detection"]
        with self.assertRaises(PageIrCompatibilityError):
            check_compatibility_profile(payload)

    def test_compatibility_profile_rejects_missing_engine_manifest(self):
        with self.assertRaises(PageIrCompatibilityError):
            check_compatibility_profile({"pages": []})


def load_fixture(page_id: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / f"{page_id}.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
