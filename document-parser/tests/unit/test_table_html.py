import unittest

from document_parser.serialization.table_html import build_table_ir, parse_table_html


class ParseTableHtmlTests(unittest.TestCase):
    def test_parses_simple_grid(self):
        rows = parse_table_html("<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>")

        self.assertEqual(len(rows), 2)
        self.assertEqual([c["text"] for c in rows[0]], ["a", "b"])
        self.assertEqual([c["text"] for c in rows[1]], ["c", "d"])

    def test_decodes_html_entities(self):
        rows = parse_table_html("<table><tr><td>a&gt;0</td><td>a&lt;0</td></tr></table>")

        self.assertEqual([c["text"] for c in rows[0]], ["a>0", "a<0"])

    def test_reads_colspan_and_rowspan_attributes(self):
        rows = parse_table_html('<table><tr><td colspan="2">wide</td></tr></table>')

        self.assertEqual(rows[0][0]["colspan"], 2)
        self.assertEqual(rows[0][0]["rowspan"], 1)


class BuildTableIrTests(unittest.TestCase):
    def test_assigns_row_and_column_indices(self):
        html = "<table><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></table>"

        table_ir = build_table_ir(
            html,
            table_bbox={"x": 0, "y": 0, "width": 200, "height": 100},
            node_id_prefix="p001-table1",
            content_node_builder=lambda text, prefix, bbox: [{"text": text, "bbox": bbox}],
        )

        self.assertEqual(table_ir["row_count"], 2)
        self.assertEqual(table_ir["column_count"], 2)
        positions = {(c["row_index"], c["column_index"]) for c in table_ir["cells"]}
        self.assertEqual(positions, {(1, 1), (1, 2), (2, 1), (2, 2)})

    def test_colspan_shifts_following_cells_in_the_same_row(self):
        # A merged first cell spanning 2 columns must push the next real cell to
        # column 3, not column 2 (verified against p004's real header row, which
        # has a genuinely blank first cell rather than a colspan, but the same
        # occupancy-tracking logic is what keeps that row's columns aligned with
        # the data rows below it).
        html = '<table><tr><td colspan="2">wide</td><td>c</td></tr></table>'

        table_ir = build_table_ir(
            html,
            table_bbox={"x": 0, "y": 0, "width": 300, "height": 100},
            node_id_prefix="p001-table1",
            content_node_builder=lambda text, prefix, bbox: [{"text": text, "bbox": bbox}],
        )

        self.assertEqual(table_ir["column_count"], 3)
        wide_cell = table_ir["cells"][0]
        self.assertEqual(wide_cell["column_span"], 2)
        self.assertEqual(wide_cell["column_index"], 1)
        narrow_cell = table_ir["cells"][1]
        self.assertEqual(narrow_cell["column_index"], 3)

    def test_rowspan_reserves_the_cell_below_in_the_next_row(self):
        html = (
            '<table>'
            '<tr><td rowspan="2">tall</td><td>b</td></tr>'
            '<tr><td>d</td></tr>'
            '</table>'
        )

        table_ir = build_table_ir(
            html,
            table_bbox={"x": 0, "y": 0, "width": 200, "height": 200},
            node_id_prefix="p001-table1",
            content_node_builder=lambda text, prefix, bbox: [{"text": text, "bbox": bbox}],
        )

        # Row 2's real cell ("d") must land in column 2, since column 1 is
        # occupied by row 1's rowspan="2" cell.
        row2_cell = next(c for c in table_ir["cells"] if c["row_index"] == 2)
        self.assertEqual(row2_cell["column_index"], 2)

    def test_cell_bbox_is_proportionally_estimated_within_table_bbox(self):
        html = "<table><tr><td>a</td><td>b</td></tr></table>"

        table_ir = build_table_ir(
            html,
            table_bbox={"x": 100, "y": 200, "width": 400, "height": 50},
            node_id_prefix="p001-table1",
            content_node_builder=lambda text, prefix, bbox: [{"text": text, "bbox": bbox}],
        )

        first_cell, second_cell = table_ir["cells"]
        self.assertEqual(first_cell["bbox"]["x"], 100)
        self.assertEqual(second_cell["bbox"]["x"], 300)
        self.assertEqual(first_cell["bbox"]["width"], 200)
        self.assertTrue(first_cell["bbox_is_estimated"])

    def test_high_confidence_for_clean_rectangular_grid(self):
        html = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"

        table_ir = build_table_ir(
            html,
            table_bbox={"x": 0, "y": 0, "width": 200, "height": 100},
            node_id_prefix="p001-table1",
            content_node_builder=lambda text, prefix, bbox: [],
        )

        self.assertGreaterEqual(table_ir["structure_confidence"], 0.8)

    def test_lower_confidence_for_ragged_rows(self):
        html = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>"

        table_ir = build_table_ir(
            html,
            table_bbox={"x": 0, "y": 0, "width": 200, "height": 100},
            node_id_prefix="p001-table1",
            content_node_builder=lambda text, prefix, bbox: [],
        )

        self.assertLess(table_ir["structure_confidence"], 0.8)

    def test_empty_html_returns_zero_confidence_empty_table(self):
        table_ir = build_table_ir(
            "",
            table_bbox={"x": 0, "y": 0, "width": 200, "height": 100},
            node_id_prefix="p001-table1",
            content_node_builder=lambda text, prefix, bbox: [],
        )

        self.assertEqual(table_ir["row_count"], 0)
        self.assertEqual(table_ir["cells"], [])
        self.assertEqual(table_ir["structure_confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
