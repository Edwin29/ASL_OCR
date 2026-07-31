import unittest

from document_parser.page_policy import decide_intro_guide_page_exclusion, decide_two_column_reading_order


class PagePolicyTests(unittest.TestCase):
    def test_intro_guide_policy_is_not_tied_to_sample_page_id(self):
        decision = decide_intro_guide_page_exclusion(
            nodes=guide_nodes(page_id="p777"),
            page_width=200,
            page_height=300,
        )

        self.assertTrue(decision.should_exclude)
        self.assertEqual(decision.reason_code, "INTRO_GUIDE_PAGE_EXCLUSION_CANDIDATE")

    def test_structure_word_alone_does_not_exclude_sparse_math_page(self):
        nodes = [
            node("p010-n001", 0, 20, 20, 160, 12, "Problem structure"),
            node("p010-n002", 1, 20, 80, 80, 12, "math body"),
            node("p010-n003", 2, 20, 110, 80, 12, "solution"),
        ]
        decision = decide_intro_guide_page_exclusion(nodes, page_width=200, page_height=300)

        self.assertFalse(decision.should_exclude)
        self.assertEqual(decision.evidence["text_node_count"], 3)

    def test_dense_page_without_intro_header_is_not_excluded(self):
        nodes = [node("p020-n001", 0, 20, 20, 160, 12, "logarithm practice")]
        for index in range(30):
            nodes.append(node(
                f"p020-n{index + 2:03d}",
                index + 1,
                20 + (index % 3) * 28,
                60 + (index // 3) * 9,
                20,
                4,
                f"math item {index}",
            ))
        decision = decide_intro_guide_page_exclusion(nodes, page_width=200, page_height=300)

        self.assertFalse(decision.should_exclude)
        self.assertFalse(decision.evidence["has_intro_header"])

    def test_two_column_policy_detects_balanced_left_and_right_nodes(self):
        decision = decide_two_column_reading_order(two_column_nodes(), page_width=200, page_height=300)

        self.assertTrue(decision.should_reorder)
        self.assertEqual(decision.reason_code, "TWO_COLUMN_READING_ORDER_CANDIDATE")
        self.assertGreaterEqual(decision.evidence["left_node_count"], 8)
        self.assertGreaterEqual(decision.evidence["right_node_count"], 8)

    def test_two_column_policy_skips_intro_guide_candidate(self):
        decision = decide_two_column_reading_order(guide_nodes("p777"), page_width=200, page_height=300)

        self.assertFalse(decision.should_reorder)
        self.assertEqual(decision.evidence["skip_reason"], "intro_guide_page_candidate")


def guide_nodes(page_id):
    nodes = [
        node(f"{page_id}-n001", 0, 20, 20, 160, 12, "Book structure and features Structure"),
        node(f"{page_id}-n040", 40, 70, 160, 120, 40, "Publisher guide text should be excluded."),
    ]
    for index in range(30):
        nodes.append(node(
            f"{page_id}-n{index + 2:03d}",
            index + 1,
            20 + (index % 3) * 28,
            60 + (index // 3) * 9,
            20,
            4,
            f"preview {index}",
        ))
    return nodes


def two_column_nodes():
    nodes = [
        node("p200-n001", 0, 20, 10, 80, 8, "header"),
        node("p200-n999", 99, 20, 286, 80, 8, "footer"),
    ]
    for index in range(8):
        y = 36 + index * 30
        nodes.append(node(f"p200-l{index}", index + 1, 20, y, 55, 8, f"left {index}"))
        nodes.append(node(f"p200-r{index}", index + 20, 125, y, 55, 8, f"right {index}"))
    return nodes


def node(node_id, reading_order_index, x, y, width, height, text):
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "normalized_bbox": {
            "x": round(x / 200, 6),
            "y": round(y / 300, 6),
            "width": round(width / 200, 6),
            "height": round(height / 300, 6),
        },
        "reading_order_index": reading_order_index,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "normalized_text": text,
    }


if __name__ == "__main__":
    unittest.main()
