import unittest

from document_parser.layout import LayoutBuilder
from document_parser.ocr.fixture import token


class LayoutBuilderTests(unittest.TestCase):
    def test_groups_tokens_on_same_baseline_into_one_line(self):
        tokens = [
            token("log", 200, 300, 80, 30),
            token("rule", 300, 302, 80, 30),
            token("next", 200, 370, 80, 30),
        ]
        lines = LayoutBuilder().build_lines(tokens, "p008")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].text, "log rule")
        self.assertEqual(lines[1].text, "next")

    def test_keeps_same_baseline_columns_in_separate_lines_and_blocks(self):
        tokens = [
            token("left-1", 100, 100, 80, 30),
            token("left-2", 100, 145, 80, 30),
            token("right-1", 520, 100, 90, 30),
            token("right-2", 520, 145, 90, 30),
        ]
        builder = LayoutBuilder(line_x_gap_ratio=6.0)
        lines = builder.build_lines(tokens, "p102")
        self.assertEqual([line.text for line in lines], ["left-1", "right-1", "left-2", "right-2"])

        blocks = builder.build_blocks(lines, "p102")
        self.assertEqual([[line.text for line in block.lines] for block in blocks], [
            ["left-1", "left-2"],
            ["right-1", "right-2"],
        ])

    def test_builds_blocks_from_vertical_gaps(self):
        builder = LayoutBuilder(block_gap_ratio=1.0)
        lines = builder.build_lines([
            token("first", 100, 100, 80, 30),
            token("second", 100, 140, 80, 30),
            token("third", 100, 260, 80, 30),
        ], "p001")
        blocks = builder.build_blocks(lines, "p001")
        self.assertEqual(len(blocks), 2)
        self.assertEqual([line.text for line in blocks[0].lines], ["first", "second"])
        self.assertEqual([line.text for line in blocks[1].lines], ["third"])

    def test_reading_order_is_top_to_bottom_then_left_to_right(self):
        builder = LayoutBuilder()
        lines = builder.build_lines([
            token("bottom", 100, 200, 80, 30),
            token("top", 100, 100, 80, 30),
        ], "p001")
        blocks = builder.build_blocks(lines, "p001")
        ordered = builder.resolve_reading_order(blocks)
        self.assertEqual([line.text for line in ordered], ["top", "bottom"])


if __name__ == "__main__":
    unittest.main()
