import unittest

from document_parser.accessibility.flattening import classify_ast_status

from .support import load_accessible_document, load_fixture


class ExactlyOnceConsumptionTests(unittest.TestCase):
    """Every real page-level node must be represented exactly once in the
    flattened focus items, whether it reached the top level directly through
    `reading_order` or only through a PROBLEM_UNIT's role lists."""

    def test_no_duplicate_focus_item_ids_across_all_fixtures(self):
        for page_id in ["p004", "p018", "p019", "p030", "p038", "p088"]:
            document = load_accessible_document(page_id)
            ids = document["global_reading_order"]
            self.assertEqual(len(ids), len(set(ids)), page_id)

    def test_every_text_node_in_page_ir_is_represented_exactly_once(self):
        # Cross-check against the raw Page IR: every TEXT/MATH/TABLE/
        # UNSUPPORTED_VISUAL node that is either in `reading_order` or
        # embedded in a PROBLEM_UNIT must show up as a focus item's sole
        # `source_node_ids` entry, and nothing else should.
        payload = load_fixture("p018")
        page = payload["pages"][0]
        node_by_id = {n["node_id"]: n for n in page["nodes"]}
        expected_ids = set()
        for node_id in page["reading_order"]:
            node = node_by_id[node_id]
            if node.get("layout", {}).get("structure_label") == "PROBLEM_UNIT":
                expected_ids.update(node["embedded_text_nodes"])
            else:
                expected_ids.add(node_id)

        document = load_accessible_document("p018")
        flattened_ids = set(document["global_reading_order"])
        self.assertEqual(expected_ids, flattened_ids)


class ProblemUnitExpansionTests(unittest.TestCase):
    def test_role_order_is_marker_stem_condition_bogi_choices(self):
        document = load_accessible_document("p018")
        ids = document["global_reading_order"]
        # problem-001 (code p018-vl006): marker -> stem -> condition -> choices, no 보기.
        start = ids.index("p018-vl006")
        self.assertEqual(
            ids[start:start + 4],
            ["p018-vl006", "p018-vl007-L01", "p018-vl007-L02", "p018-vl007-L03"],
        )

    def test_choices_split_across_multiple_blocks_stay_together_in_order(self):
        # Real p018 case this session fixed: choices ①③④⑤② arrived as three
        # separate sibling blocks and were reassembled into one choice group.
        document = load_accessible_document("p018")
        ids = document["global_reading_order"]
        start = ids.index("p018-vl010")
        self.assertEqual(ids[start:start + 3], ["p018-vl010", "p018-vl011", "p018-vl012"])

    def test_problem_unit_members_are_not_independently_reachable(self):
        # The PROBLEM_UNIT wrapper node itself (`p018-problem-001`) carries no
        # readable content and must not appear as a focus item.
        document = load_accessible_document("p018")
        ids = set(document["global_reading_order"])
        self.assertNotIn("p018-problem-001", ids)
        self.assertNotIn("p018-problem-002", ids)
        self.assertNotIn("p018-problem-003", ids)


class ProblemIdTaggingTests(unittest.TestCase):
    def test_problem_unit_members_share_the_same_problem_id(self):
        document = load_accessible_document("p018")
        items_by_id = {item["id"]: item for item in document["pages"][0]["focus_items"]}
        member_ids = ["p018-vl006", "p018-vl007-L01", "p018-vl007-L02", "p018-vl007-L03"]
        problem_ids = {items_by_id[member_id]["problem_id"] for member_id in member_ids}
        self.assertEqual(len(problem_ids), 1)
        self.assertIsNotNone(next(iter(problem_ids)))

    def test_document_has_three_distinct_problem_groups_on_p018(self):
        # p018 is known to contain 3 detected problem units (see
        # ProblemUnitExpansionTests.test_problem_unit_members_are_not_independently_reachable).
        document = load_accessible_document("p018")
        problem_ids = {
            item["problem_id"]
            for item in document["pages"][0]["focus_items"]
            if item["problem_id"] is not None
        }
        self.assertEqual(len(problem_ids), 3)

    def test_items_outside_any_problem_unit_have_null_problem_id(self):
        document = load_accessible_document("p004")  # no PROBLEM_UNIT nodes in this fixture
        focus_items = document["pages"][0]["focus_items"]
        self.assertTrue(focus_items)
        self.assertTrue(all(item["problem_id"] is None for item in focus_items))


class TableFlatteningTests(unittest.TestCase):
    def test_table_cell_indices_and_content_are_preserved(self):
        document = load_accessible_document("p038")
        table_item = next(item for item in document["pages"][0]["focus_items"] if item["kind"] == "TABLE")
        self.assertEqual(table_item["row_count"], 4)
        self.assertEqual(table_item["column_count"], 5)
        cell = next(c for c in table_item["cells"] if c["row_index"] == 2 and c["column_index"] == 2)
        self.assertEqual(cell["content_nodes"], [{"kind": "TEXT", "text": "+"}])
        # ASL_OCR table cells are already 1-based; this must not be re-offset.
        self.assertTrue(all(c["row_index"] >= 1 and c["column_index"] >= 1 for c in table_item["cells"]))

    def test_math_cell_gets_ast_status(self):
        document = load_accessible_document("p038")
        table_item = next(item for item in document["pages"][0]["focus_items"] if item["kind"] == "TABLE")
        math_cell = next(c for c in table_item["cells"] if c["row_index"] == 2 and c["column_index"] == 1)
        self.assertEqual(math_cell["content_nodes"][0]["kind"], "MATH")
        self.assertEqual(math_cell["content_nodes"][0]["ast_status"], "VALID")


class UnsupportedVisualFlatteningTests(unittest.TestCase):
    def test_preserved_text_is_carried_without_becoming_navigable(self):
        document = load_accessible_document("p004")
        visual_items = [item for item in document["pages"][0]["focus_items"] if item["kind"] == "UNSUPPORTED_VISUAL"]
        self.assertTrue(visual_items)
        self.assertTrue(any(item["preserved_content"] for item in visual_items))


class AstStatusClassificationTests(unittest.TestCase):
    def test_clean_ast_is_valid(self):
        self.assertEqual(classify_ast_status([], []), "VALID")

    def test_unconsumed_tokens_is_invalid(self):
        self.assertEqual(classify_ast_status(["x"], []), "INVALID")

    def test_error_issue_is_invalid_even_without_unconsumed_tokens(self):
        issues = [{"code": "AST_UNMATCHED_PAREN", "severity": "error"}]
        self.assertEqual(classify_ast_status([], issues), "INVALID")

    def test_unknown_node_alone_is_partial(self):
        issues = [{"code": "AST_UNKNOWN_NODE", "severity": "info"}]
        self.assertEqual(classify_ast_status([], issues), "PARTIAL")

    def test_error_outranks_unknown_node(self):
        issues = [
            {"code": "AST_UNKNOWN_NODE", "severity": "info"},
            {"code": "AST_UNMATCHED_BRACE", "severity": "error"},
        ]
        self.assertEqual(classify_ast_status([], issues), "INVALID")

    def test_real_unsupported_sum_command_is_invalid_not_silently_valid(self):
        # Real p088 formula: \sum is not a recognized command. This must never
        # be presented to the user as trustworthy braille.
        document = load_accessible_document("p088")
        math_items = [item for item in document["pages"][0]["focus_items"] if item["kind"] == "MATH"]
        sum_items = [item for item in math_items if "\\sum" in item["raw_formula"]]
        self.assertTrue(sum_items)
        for item in sum_items:
            self.assertEqual(item["ast_status"], "INVALID")


if __name__ == "__main__":
    unittest.main()
