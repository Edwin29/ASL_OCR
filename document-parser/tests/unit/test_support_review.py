import unittest

from document_parser.serialization.visual_regions import INTRO_GUIDE_PAGE_VISUAL_TYPE
from document_parser.support_review import (
    approved_exclusion_types_from_config,
    build_support_review_report,
)
from tests.unit.test_visual_regions import intro_page


class SupportReviewTests(unittest.TestCase):
    def test_reports_pending_candidate_without_approval(self):
        report = build_support_review_report(payload())
        candidate = report["pages"][0]["exclusion_candidates"][0]

        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["pending_approval_count"], 1)
        self.assertEqual(candidate["candidate_type"], INTRO_GUIDE_PAGE_VISUAL_TYPE)
        self.assertEqual(candidate["approval_status"], "PENDING_APPROVAL")
        self.assertFalse(candidate["will_apply_with_current_approvals"])

    def test_reports_approved_candidate_with_config(self):
        approved = {INTRO_GUIDE_PAGE_VISUAL_TYPE}
        report = build_support_review_report(payload(), approved_exclusion_types=approved)
        candidate = report["pages"][0]["exclusion_candidates"][0]

        self.assertEqual(report["approved_candidate_count"], 1)
        self.assertEqual(candidate["approval_status"], "APPROVED")
        self.assertTrue(candidate["will_apply_with_current_approvals"])

    def test_reads_approved_exclusion_types_from_config(self):
        approved = approved_exclusion_types_from_config({
            "approved_exclusion_types": [INTRO_GUIDE_PAGE_VISUAL_TYPE, 42],
        })

        self.assertEqual(approved, {INTRO_GUIDE_PAGE_VISUAL_TYPE})


def payload():
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "pages": [intro_page()],
        "engine_manifest": {},
        "validation_summary": {},
    }


if __name__ == "__main__":
    unittest.main()
