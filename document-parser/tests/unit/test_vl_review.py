import unittest

from document_parser.evaluation import build_vl_review_report


class VlReviewReportTests(unittest.TestCase):
    def test_ranks_pages_by_priority_score_descending(self):
        document = {
            "pages": [
                page_with_issues("p_clean", []),
                page_with_issues("p_bad", [
                    ("CROSS_VALIDATION_CONFIRMS_OMISSION", "error"),
                    ("VL_POSSIBLE_CHOICE_OMISSION", "warning"),
                ]),
                page_with_issues("p_mild", [("AST_UNKNOWN_NODE", "info")]),
            ]
        }

        report = build_vl_review_report(document)

        self.assertEqual(report["review_priority_order"], ["p_bad", "p_mild", "p_clean"])

    def test_confirmed_omission_outweighs_several_minor_issues(self):
        # A single confirmed omission is worse than several unconfirmed/expected
        # noise issues -- the weighting must reflect that, not just raw counts.
        document = {
            "pages": [
                page_with_issues("p_one_confirmed", [("CROSS_VALIDATION_CONFIRMS_OMISSION", "error")]),
                page_with_issues("p_many_minor", [("AST_UNKNOWN_NODE", "info")] * 5),
            ]
        }

        report = build_vl_review_report(document)

        self.assertEqual(report["review_priority_order"][0], "p_one_confirmed")

    def test_total_counts_and_page_summary_fields(self):
        document = {"pages": [page_with_issues("p001", [("VL_POSSIBLE_CHOICE_OMISSION", "warning")])]}

        report = build_vl_review_report(document)

        self.assertEqual(report["page_count"], 1)
        self.assertEqual(report["total_node_count"], 1)
        page = report["pages"][0]
        self.assertEqual(page["issue_count"], 1)
        self.assertEqual(page["issue_code_counts"], {"VL_POSSIBLE_CHOICE_OMISSION": 1})
        self.assertEqual(page["top_issues"][0]["code"], "VL_POSSIBLE_CHOICE_OMISSION")

    def test_zero_weight_codes_are_counted_but_not_listed_as_top_issues(self):
        document = {"pages": [page_with_issues("p001", [("CROSS_VALIDATION_RECORDED", "info")])]}

        report = build_vl_review_report(document)

        page = report["pages"][0]
        self.assertEqual(page["review_priority_score"], 0)
        self.assertEqual(page["issue_code_counts"], {"CROSS_VALIDATION_RECORDED": 1})
        self.assertEqual(page["top_issues"], [])

    def test_page_with_no_issues_has_zero_score_and_sorts_last(self):
        document = {"pages": [page_with_issues("p001", [])]}

        report = build_vl_review_report(document)

        page = report["pages"][0]
        self.assertEqual(page["review_priority_score"], 0)
        self.assertEqual(page["issue_count"], 0)


def page_with_issues(page_id, code_severity_pairs):
    nodes = []
    for index, (code, severity) in enumerate(code_severity_pairs, start=1):
        nodes.append({
            "node_id": f"{page_id}-n{index}",
            "content_type": "TEXT",
            "issues": [{"code": code, "severity": severity, "message": "test"}],
        })
    if not nodes:
        nodes = [{"node_id": f"{page_id}-n1", "content_type": "TEXT", "issues": []}]
    return {"page_id": page_id, "nodes": nodes}


if __name__ == "__main__":
    unittest.main()
