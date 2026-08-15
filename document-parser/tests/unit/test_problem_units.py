import unittest

from document_parser.structure import (
    PROBLEM_UNIT_STRUCTURE_LABEL,
    detect_problem_units_in_document,
    problem_unit_report,
)
from document_parser.validation import validate_document_ir


class ProblemUnitTests(unittest.TestCase):
    def test_detects_choice_and_condition_problems_and_keeps_page_ir_valid(self):
        processed = detect_problem_units_in_document(page_ir_fixture())
        page = processed["pages"][0]
        problems = problem_unit_nodes(page)

        self.assertEqual(len(problems), 6)
        self.assertTrue(validate_document_ir(processed)["schema_valid"])

        p1 = problem_by_marker(problems, "n001")
        self.assertEqual(p1["layout"]["answer_structure_type"], "choices")
        self.assertEqual(p1["layout"]["stem_node_ids"], ["n002"])
        self.assertEqual(p1["layout"]["choice_node_id"], "n003")
        self.assertEqual(p1["embedded_text_nodes"], ["n001", "n002", "n003"])
        self.assertEqual(
            p1["layout"]["choice_options"],
            [
                {"label": "①", "text": "√2"},
                {"label": "②", "text": "√3"},
                {"label": "③", "text": "2"},
                {"label": "④", "text": "√5"},
                {"label": "⑤", "text": "√6"},
            ],
        )
        self.assertNotIn(
            "CHOICE_OPTION_SPLIT_INCOMPLETE",
            {issue["code"] for issue in p1["issues"]},
        )

        p2 = problem_by_marker(problems, "n005")
        self.assertEqual(p2["layout"]["condition_node_ids"], ["n007", "n008"])
        self.assertEqual(p2["layout"]["choice_node_id"], "n009")
        self.assertEqual(
            p2["layout"]["condition_items"],
            [
                {"node_id": "n007", "label": "(가)", "text": "3^a=27^b이고 그 값은 자연수이다."},
                {"node_id": "n008", "label": "(나)", "text": "1/a+1/b은 자연수이다."},
            ],
        )
        self.assertIn(
            "다음 조건을 만족시키는 두 양수 a, b에 대하여",
            p2["layout"]["stem_text"],
        )

    def test_flags_incomplete_choice_split_from_ocr_marker_corruption(self):
        # Real OCR sample (EBS 2027 수능특강 수학I, p019): the fifth circled digit was
        # misread as a plain "5" instead of "⑤", so only 4 options can be split out.
        processed = detect_problem_units_in_document(page_ir_fixture())
        page = processed["pages"][0]
        problems = problem_unit_nodes(page)

        garbled = problem_by_marker(problems, "n025")
        self.assertEqual(len(garbled["layout"]["choice_options"]), 4)
        self.assertIn(
            "CHOICE_OPTION_SPLIT_INCOMPLETE",
            {issue["code"] for issue in garbled["issues"]},
        )

    def test_rejects_dangling_marker_without_answer_structure(self):
        processed = detect_problem_units_in_document(page_ir_fixture())
        page = processed["pages"][0]
        problems = problem_unit_nodes(page)

        self.assertIsNone(problem_by_marker(problems, "n010", required=False))
        n010 = node_by_id(page, "n010")
        n011 = node_by_id(page, "n011")
        self.assertNotIn("parent_structure_node_id", n010)
        self.assertNotIn("parent_structure_node_id", n011)
        self.assertIn("n010", page["reading_order"])
        self.assertIn("n011", page["reading_order"])

    def test_leaves_trailing_solution_text_outside_problem(self):
        processed = detect_problem_units_in_document(page_ir_fixture())
        page = processed["pages"][0]
        problems = problem_unit_nodes(page)

        exam_problem = problem_by_marker(problems, "n012")
        self.assertEqual(exam_problem["layout"]["problem_start_kind"], "exam_reprint")
        self.assertEqual(exam_problem["layout"]["choice_node_id"], "n014")
        self.assertNotIn("n015", exam_problem["embedded_text_nodes"])

        n015 = node_by_id(page, "n015")
        self.assertNotIn("parent_structure_node_id", n015)
        self.assertIn("n015", page["reading_order"])

    def test_detects_short_answer_problem(self):
        processed = detect_problem_units_in_document(page_ir_fixture())
        page = processed["pages"][0]
        problems = problem_unit_nodes(page)

        short_answer_problem = problem_by_marker(problems, "n016")
        self.assertEqual(short_answer_problem["layout"]["answer_structure_type"], "short_answer")
        self.assertIsNone(short_answer_problem["layout"]["choice_node_id"])
        self.assertEqual(short_answer_problem["layout"]["stem_node_ids"], ["n017"])

    def test_detects_bogi_substructure(self):
        processed = detect_problem_units_in_document(page_ir_fixture())
        page = processed["pages"][0]
        problems = problem_unit_nodes(page)

        bogi_problem = problem_by_marker(problems, "n018")
        self.assertEqual(
            bogi_problem["layout"]["bogi_node_ids"],
            ["n020", "n021", "n022", "n023"],
        )
        self.assertEqual(bogi_problem["layout"]["choice_node_id"], "n024")

    def test_reassembles_choices_split_across_multiple_blocks(self):
        # Real PaddleOCR-VL output (EBS 2027 수능특강 수학I, p018): one choice row
        # came out as three separate sibling blocks in scrambled order --
        # "① ..." / "③ ... ④ ... ⑤ ..." / "② ..." -- none individually reaching
        # MIN_CHOICE_MARKER_COUNT, so the old single-node check found nothing.
        payload = {
            "document_manifest": {"book_id": "book", "page_count": 1},
            "engine_manifest": {},
            "validation_summary": {},
            "pages": [{
                "page_id": "p018",
                "page_geometry": {"width": 1000, "height": 1000},
                "nodes": [
                    text_node("m1", "[26008-0030]", 0),
                    text_node("m2", "삼각형 ABE의 넓이는?", 1),
                    text_node("m3", "① (log 2)^2", 2),
                    text_node("m4", "③ 3(log 2)^2 ④ 4(log 2)^2 ⑤ 5(log 2)^2", 3),
                    text_node("m5", "② 2(log 2)^2", 4),
                ],
                "reading_order": ["m1", "m2", "m3", "m4", "m5"],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }],
        }

        processed = detect_problem_units_in_document(payload)
        page = processed["pages"][0]
        problems = problem_unit_nodes(page)

        problem = problem_by_marker(problems, "m1")
        self.assertEqual(problem["layout"]["choice_node_ids"], ["m3", "m4", "m5"])
        self.assertEqual(problem["layout"]["choice_node_id"], "m3")
        self.assertEqual(
            [option["label"] for option in problem["layout"]["choice_options"]],
            ["①", "②", "③", "④", "⑤"],
        )
        self.assertIn(
            "VL_CHOICE_OPTIONS_REORDERED",
            {issue["code"] for issue in problem["issues"]},
        )
        self.assertNotIn(
            "CHOICE_OPTION_SPLIT_INCOMPLETE",
            {issue["code"] for issue in problem["issues"]},
        )

    def test_splits_multiline_block_bundling_stem_condition_and_choices(self):
        # Real PaddleOCR-VL output: one text block can bundle a problem's stem,
        # its (가)/(나) conditions, and its ①-⑤ choices, joined by literal "\n".
        bundled_text = (
            "다음 조건을 만족시키는 두 양수 a, b에 대하여 p-q의 값은?\n"
            "(가) 3^a=27^b이고 그 값은 자연수이다. (나) 1/a+1/b은 자연수이다.\n"
            "① 220 ② 225 ③ 230 ④ 235 ⑤ 240"
        )
        payload = {
            "document_manifest": {"book_id": "book", "page_count": 1},
            "engine_manifest": {},
            "validation_summary": {},
            "pages": [{
                "page_id": "p019",
                "page_geometry": {"width": 1000, "height": 1000},
                "nodes": [
                    text_node("b1", "[26008-0012]", 0),
                    text_node("b2", bundled_text, 1),
                ],
                "reading_order": ["b1", "b2"],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }],
        }

        processed = detect_problem_units_in_document(payload)
        page = processed["pages"][0]
        problems = problem_unit_nodes(page)

        problem = problem_by_marker(problems, "b1")
        self.assertIn("다음 조건을 만족시키는", problem["layout"]["stem_text"])
        self.assertEqual(
            problem["layout"]["condition_items"],
            [
                {"node_id": "b2-L02", "label": "(가)", "text": "3^a=27^b이고 그 값은 자연수이다."},
                {"node_id": "b2-L02", "label": "(나)", "text": "1/a+1/b은 자연수이다."},
            ],
        )
        self.assertEqual(len(problem["layout"]["choice_options"]), 5)

        # b2 itself must no longer be a standalone node -- it was replaced by its
        # split lines, all now embedded in the problem unit.
        self.assertIsNone(node_by_id(page, "b2", required=False))
        self.assertNotIn("b2", page["reading_order"])
        split_line = node_by_id(page, "b2-L01")
        self.assertEqual(split_line["layout"]["problem_unit_role"], "stem")
        self.assertTrue(split_line["bbox_is_estimated"])

    def test_ignores_marker_dense_text_without_start_signal(self):
        payload = {
            "document_manifest": {"book_id": "book", "page_count": 1},
            "engine_manifest": {},
            "validation_summary": {},
            "pages": [{
                "page_id": "p999",
                "page_geometry": {"width": 1000, "height": 1000},
                "nodes": [text_node("only", "① a ② b ③ c ④ d", 0)],
                "reading_order": ["only"],
                "parse_issues": [],
                "quality_report": {"status": "PASS"},
            }],
        }

        processed = detect_problem_units_in_document(payload)
        report = problem_unit_report(processed)

        self.assertEqual(report["total_problem_count"], 0)

    def test_builds_report(self):
        processed = detect_problem_units_in_document(page_ir_fixture())
        report = problem_unit_report(processed)

        self.assertEqual(report["total_problem_count"], 6)
        self.assertEqual(report["pages"][0]["page_id"], "p014")


def problem_unit_nodes(page):
    return [
        node
        for node in page["nodes"]
        if isinstance(node.get("layout"), dict)
        and node["layout"].get("structure_label") == PROBLEM_UNIT_STRUCTURE_LABEL
    ]


def problem_by_marker(problems, marker_node_id, required=True):
    for problem in problems:
        if problem["layout"]["problem_marker_node_id"] == marker_node_id:
            return problem
    if required:
        raise AssertionError(f"No problem unit found for marker {marker_node_id}")
    return None


def node_by_id(page, node_id, required=True):
    for node in page["nodes"]:
        if node["node_id"] == node_id:
            return node
    if required:
        raise AssertionError(f"No node found for id {node_id}")
    return None


def page_ir_fixture():
    nodes = [
        text_node("n001", "[26008-0011]", 0),
        text_node("n002", "8제곱근 81 곱하기 6제곱근 8의 값은?", 1),
        text_node("n003", "① √2 ② √3 ③ 2 ④ √5 ⑤ √6", 2),
        text_node("n004", "① (na)n=a ② n a n b=nab ③ (na)m=nam ④ pna p=na", 3),
        text_node("n005", "[26008-0012]", 4),
        text_node(
            "n006",
            "다음 조건을 만족시키는 두 양수 a, b에 대하여 3^a×3^b의 최댓값을 p, 최솟값을 q라 할 때, p-q의 값은?",
            5,
        ),
        text_node("n007", "(가) 3^a=27^b이고 그 값은 자연수이다.", 6),
        text_node("n008", "(나) 1/a+1/b은 자연수이다.", 7),
        text_node("n009", "① 220 ② 225 ③ 230 ④ 235 ⑤ 240", 8),
        text_node("n010", "[26008-0013]", 9),
        text_node("n011", "이 문제는 준비 중입니다", 10),
        text_node("n012", "2023학년도 수능", 11),
        text_node("n013", "자연수 m(m≥2)에 대하여 f(m)의 값은? [4점]", 12),
        text_node("n014", "① 37 ② 42 ③ 47 ④ 52 ⑤ 57", 13),
        text_node("n015", "출제의도 a의 n제곱근의 뜻을 이해하고 묻는 문제이다.", 14),
        text_node("n016", "[26008-0015]", 15),
        text_node("n017", "100 이하의 모든 자연수 n의 값의 합을 구하시오.", 16),
        text_node("n018", "[26008-0016]", 17),
        text_node("n019", "보기에서 옳은 것만을 있는 대로 고른 것은?", 18),
        text_node("n020", "보기", 19),
        text_node("n021", "ㄱ. x1>-2", 20),
        text_node("n022", "ㄴ. y2<1", 21),
        text_node("n023", "ㄷ. 7(x1-x2)<6(y2-y1)", 22),
        text_node("n024", "① ㄱ ② ㄴ ③ ㄱ,ㄴ ④ ㄴ,ㄷ ⑤ ㄱ,ㄴ,ㄷ", 23),
        text_node("n025", "[26008-0017]", 24),
        text_node("n026", "자연수 m(m≥2)에 대하여 f(m)의 값은?", 25),
        # Real OCR output for this row misread the fifth circled digit as a plain "5".
        text_node("n027", "① 37 ②42 ③ 47 ④ 52 5 57", 26),
    ]
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "validation_summary": {},
        "pages": [{
            "page_id": "p014",
            "page_geometry": {"width": 1000, "height": 4000},
            "nodes": nodes,
            "reading_order": [node["node_id"] for node in nodes],
            "parse_issues": [],
            "quality_report": {"status": "PASS"},
        }],
    }


def text_node(node_id, text, index):
    y = 10 + index * 30
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": {"x": 50, "y": y, "width": 500, "height": 20},
        "normalized_bbox": {"x": 0.05, "y": y / 4000, "width": 0.5, "height": 0.005},
        "reading_order_index": index,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "raw_text": text,
        "normalized_text": text,
        "spans": [{"span_type": "TEXT", "text": text}],
        "layout": {},
    }


if __name__ == "__main__":
    unittest.main()
