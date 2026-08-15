import tempfile
import unittest
from pathlib import Path

from document_parser.serialization.vl_page_ir import build_document_ir_from_vl, build_page_ir_from_vl_result
from document_parser.validation import validate_document_ir


class VlPageIrTests(unittest.TestCase):
    def test_builds_text_node_with_inline_math_spans(self):
        # Real block content from p004 (verified GPU run).
        content = "② n이 짝수이면 a≥0일 때에만 실수 x가 존재하고 x = $\\sqrt[n]{a}$ 또는 x = $-\\sqrt[n]{a}$이다."
        vl_result = fixture_result([text_block(1, content, order=1, bbox=[100, 100, 900, 160])])

        page = build_page_ir_from_vl_result(vl_result, page_id="p004")

        node = page["nodes"][0]
        self.assertEqual(node["content_type"], "TEXT")
        span_types = [s["span_type"] for s in node["spans"]]
        self.assertIn("UNKNOWN", span_types)
        math_spans = [s for s in node["spans"] if s.get("math_span_candidate")]
        self.assertEqual([s["text"] for s in math_spans], ["\\sqrt[n]{a}", "-\\sqrt[n]{a}"])

    def test_builds_display_formula_node(self):
        content = " $$ f(x)=a\\sin^{2}x+\\left|\\cos x-\\frac{1}{2a}\\right| $$ "
        vl_result = fixture_result([
            {"block_label": "display_formula", "block_content": content, "block_bbox": [100, 100, 500, 150], "block_id": 0, "block_order": 1},
        ])

        page = build_page_ir_from_vl_result(vl_result, page_id="p050")

        node = page["nodes"][0]
        self.assertEqual(node["content_type"], "MATH")
        self.assertEqual(node["formula_format"], "LATEX")
        self.assertTrue(node["raw_formula"].startswith("f(x)="))
        self.assertNotIn("$", node["raw_formula"])

    def test_builds_table_node_with_row_col_cell_structure(self):
        html = "<table><tr><td>a&gt;0</td></tr></table>"
        vl_result = fixture_result([
            {"block_label": "table", "block_content": html, "block_bbox": [100, 100, 500, 300], "block_id": 0, "block_order": 1},
        ])

        page = build_page_ir_from_vl_result(vl_result, page_id="p004")

        node = page["nodes"][0]
        self.assertEqual(node["content_type"], "TABLE")
        self.assertEqual(node["raw_html"], html)
        self.assertEqual(node["row_count"], 1)
        self.assertEqual(node["column_count"], 1)
        self.assertEqual(len(node["cells"]), 1)
        cell = node["cells"][0]
        self.assertEqual((cell["row_index"], cell["column_index"]), (1, 1))
        self.assertEqual(cell["content_nodes"][0]["normalized_text"], "a>0")
        self.assertGreaterEqual(node["structure_confidence"], 0.8)

    def test_parses_real_p004_table_with_math_cells(self):
        # Real raw_html from p004's GPU-verified output: a 3-row x 4-col table
        # ("n이 홀수/짝수" x "a>0/a=0/a<0") with inline math in several cells.
        html = (
            "<table border=1><tr><td></td><td>a&gt;0</td><td>a=0</td><td>a&lt;0</td></tr>"
            "<tr><td>n이 홀수</td><td>$ \\sqrt[n]{a} $</td><td>0</td><td>$ \\sqrt[n]{a} $</td></tr>"
            "<tr><td>n이 짝수</td><td>$ \\sqrt[n]{a}, -\\sqrt[n]{a} $</td><td>0</td><td>없다.</td></tr>"
            "</table>"
        )
        vl_result = fixture_result([
            {"block_label": "table", "block_content": html, "block_bbox": [400, 900, 1600, 1200], "block_id": 0, "block_order": 1},
        ])

        page = build_page_ir_from_vl_result(vl_result, page_id="p004")

        node = page["nodes"][0]
        self.assertEqual(node["row_count"], 3)
        self.assertEqual(node["column_count"], 4)
        self.assertEqual(len(node["cells"]), 12)
        self.assertGreaterEqual(node["structure_confidence"], 0.8)

        math_cell = next(c for c in node["cells"] if c["row_index"] == 2 and c["column_index"] == 2)
        self.assertEqual(len(math_cell["content_nodes"]), 1)
        math_node = math_cell["content_nodes"][0]
        self.assertEqual(math_node["content_type"], "MATH")
        self.assertEqual(math_node["presentation_ast"]["type"], "Radical")
        self.assertEqual(math_node["unconsumed_tokens"], [])

        text_cell = next(c for c in node["cells"] if c["row_index"] == 2 and c["column_index"] == 1)
        self.assertEqual(text_cell["content_nodes"][0]["content_type"], "TEXT")
        self.assertEqual(text_cell["content_nodes"][0]["normalized_text"], "n이 홀수")

    def test_builds_visual_node_with_no_captured_text_is_honest_about_it(self):
        vl_result = fixture_result([
            {"block_label": "image", "block_content": "", "block_bbox": [400, 1400, 900, 1800], "block_id": 0, "block_order": 1},
        ])

        page = build_page_ir_from_vl_result(vl_result, page_id="p004")

        node = page["nodes"][0]
        self.assertEqual(node["content_type"], "UNSUPPORTED_VISUAL")
        self.assertEqual(node["embedded_content_nodes"], [])
        # Must not claim text preservation it did not actually do.
        self.assertEqual(node["handling"], "ANNOUNCE_ONLY_NO_TEXT_CAPTURED")

    def test_builds_visual_node_preserving_embedded_graph_text_and_math(self):
        # Real block content from p004 with use_ocr_for_image_block=True: axis
        # labels and formulas recognized inside the graph image.
        content = "$ y \\uparrow $\n $ y = x^n $\nO\n $ \\sqrt[n]{a} $"
        vl_result = fixture_result([
            {"block_label": "image", "block_content": content, "block_bbox": [400, 1400, 900, 1800], "block_id": 0, "block_order": 1},
        ])

        page = build_page_ir_from_vl_result(vl_result, page_id="p004")

        node = page["nodes"][0]
        self.assertEqual(node["handling"], "ANNOUNCE_AND_PRESERVE_TEXT")
        embedded = node["embedded_content_nodes"]
        self.assertTrue(any(n["content_type"] == "MATH" and n["raw_formula"] == "y = x^n" for n in embedded))
        self.assertTrue(any(n["content_type"] == "MATH" and n["presentation_ast"]["type"] == "Radical" for n in embedded))
        self.assertTrue(any(n["content_type"] == "TEXT" and n["normalized_text"] == "O" for n in embedded))

    def test_flags_partial_choice_markers_but_not_full_set(self):
        # Real full 5-choice content from p050 -- must NOT be flagged.
        full = "①2 ② $ \\frac{11}{5} $ ③ $ \\frac{12}{5} $ ④ $ \\frac{13}{5} $ ⑤ $ \\frac{14}{5} $"
        # Same shape with one choice missing -- the exact failure shape verified on
        # p019 ("f(8)=" silently missing its value with no other signal.
        partial = "①2 ② $ \\frac{11}{5} $ ③ $ \\frac{12}{5} $ ④ $ \\frac{13}{5} $"

        full_page = build_page_ir_from_vl_result(fixture_result([text_block(1, full, order=1)]), page_id="p050")
        partial_page = build_page_ir_from_vl_result(fixture_result([text_block(1, partial, order=1)]), page_id="p050")

        self.assertNotIn(
            "VL_POSSIBLE_CHOICE_OMISSION",
            {i["code"] for i in full_page["nodes"][0]["issues"]},
        )
        self.assertIn(
            "VL_POSSIBLE_CHOICE_OMISSION",
            {i["code"] for i in partial_page["nodes"][0]["issues"]},
        )

    def test_does_not_flag_single_numbered_property_item_as_choice_omission(self):
        # Real block content from p004: each property in "거듭제곱근의 성질" is its
        # own block with exactly one circled-number marker. This is a numbered
        # list item, not a multiple-choice row, and must not be flagged.
        content = "①  $ (\\sqrt[n]{a})^{n}{=}a $ "
        vl_result = fixture_result([text_block(1, content, order=1)])

        page = build_page_ir_from_vl_result(vl_result, page_id="p004")

        self.assertNotIn(
            "VL_POSSIBLE_CHOICE_OMISSION",
            {i["code"] for i in page["nodes"][0]["issues"]},
        )

    def test_flags_leading_digit_glued_to_stem(self):
        # Real block content from p050 (verified GPU run): the margin problem
        # number "1" fused onto "4 이하의 자연수..." to read "14 이하의...".
        content = "14 이하의 자연수 k와 a>3, b>0인 두 실수 a, b에 대하여..."
        vl_result = fixture_result([text_block(1, content, order=1)])

        page = build_page_ir_from_vl_result(vl_result, page_id="p050")

        self.assertIn(
            "VL_POSSIBLE_PROBLEM_NUMBER_PREFIX",
            {i["code"] for i in page["nodes"][0]["issues"]},
        )

    def test_does_not_flag_normal_stem_start(self):
        content = "함수 y=f(x)의 그래프가 그림과 같다."
        vl_result = fixture_result([text_block(1, content, order=1)])

        page = build_page_ir_from_vl_result(vl_result, page_id="p004")

        self.assertNotIn(
            "VL_POSSIBLE_PROBLEM_NUMBER_PREFIX",
            {i["code"] for i in page["nodes"][0]["issues"]},
        )

    def test_headers_sort_first_and_footers_sort_last_despite_no_order(self):
        vl_result = fixture_result([
            {"block_label": "footer", "block_content": "2027학년도 EBS 수능특강 수학 I", "block_bbox": [200, 2900, 600, 2950], "block_id": 0, "block_order": None},
            text_block(1, "본문 내용", order=1, bbox=[200, 400, 900, 500]),
            {"block_label": "header", "block_content": "www.ebsi.co.kr", "block_bbox": [1900, 160, 2100, 200], "block_id": 2, "block_order": None},
        ])

        page = build_page_ir_from_vl_result(vl_result, page_id="p004")

        labels = [n["layout"]["vl_block_label"] for n in page["nodes"]]
        self.assertEqual(labels, ["header", "text", "footer"])

    def test_schema_valid_end_to_end(self):
        vl_result = fixture_result([
            text_block(1, "[26008-0011]", order=1, bbox=[380, 240, 550, 300]),
            text_block(2, "1 문제 지문 ①1 ②2 ③3 ④4 ⑤5", order=2, bbox=[250, 380, 1900, 570]),
            {"block_label": "display_formula", "block_content": "$$x^2+1$$", "block_bbox": [400, 600, 800, 650], "block_id": 3, "block_order": 3},
        ])

        document = {
            "document_manifest": {"book_id": "book", "page_count": 1},
            "engine_manifest": {},
            "pages": [build_page_ir_from_vl_result(vl_result, page_id="p014")],
        }
        summary = validate_document_ir(document)

        self.assertTrue(summary["schema_valid"], summary)


class BuildDocumentIrFromVlTests(unittest.TestCase):
    def test_builds_document_from_multiple_page_images_via_adapter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "book_p001.png").write_bytes(b"fake-png")
            (root / "book_p002.png").write_bytes(b"fake-png")

            adapter = FixtureVlAdapter({
                str((root / "book_p001.png").resolve()): fixture_result([text_block(1, "1 첫 페이지 내용", order=1)]),
                str((root / "book_p002.png").resolve()): fixture_result([text_block(1, "2 두 번째 페이지 내용", order=1)]),
            })

            document = build_document_ir_from_vl(
                [root / "book_p001.png", root / "book_p002.png"], adapter=adapter, book_id="test-book"
            )

            self.assertEqual(document["document_manifest"]["page_count"], 2)
            self.assertEqual([p["page_id"] for p in document["pages"]], ["p001", "p002"])
            self.assertTrue(document["validation_summary"]["schema_valid"])
            self.assertEqual(document["engine_manifest"]["pipeline"]["mode"], "paddleocr_vl_baseline")


class FixtureVlAdapter:
    engine_id = "fixture-paddleocr-vl"
    engine_version = "0.0.0"

    def __init__(self, result_by_path):
        self.result_by_path = result_by_path

    def parse_page(self, image_path):
        return self.result_by_path[str(Path(image_path).resolve())]


def text_block(block_id, content, order, bbox=None):
    return {
        "block_label": "text",
        "block_content": content,
        "block_bbox": bbox or [100, 100 + block_id * 100, 900, 160 + block_id * 100],
        "block_id": block_id,
        "block_order": order,
    }


def fixture_result(blocks):
    return {"width": 2434, "height": 3071, "parsing_res_list": blocks}


if __name__ == "__main__":
    unittest.main()
