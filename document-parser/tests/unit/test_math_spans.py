import unittest

from document_parser.math import (
    build_line_spans,
    detect_math_spans_in_document,
    math_span_report,
)
from document_parser.validation import validate_document_ir


class MathSpanTests(unittest.TestCase):
    def test_splits_mixed_korean_and_math_tokens(self):
        tokens = [
            token("함수", x=0),
            token("f(x)=x^2+1", x=60),
            token("이다.", x=200),
        ]

        runs = build_line_spans(tokens)

        self.assertEqual([cls for cls, _ in runs], ["TEXT", "MATH", "TEXT"])

    def test_demotes_lone_plain_digit_to_text(self):
        tokens = [token("문제", x=0), token("2", x=50), token("번", x=70)]

        runs = build_line_spans(tokens)

        self.assertEqual([cls for cls, _ in runs], ["TEXT"])

    def test_confirms_single_token_math_run_with_relation_operator(self):
        tokens = [token("답은", x=0), token("x=2", x=50), token("이다.", x=110)]

        runs = build_line_spans(tokens)

        self.assertEqual([cls for cls, _ in runs], ["TEXT", "MATH", "TEXT"])

    def test_updates_node_spans_and_keeps_page_ir_valid(self):
        processed = detect_math_spans_in_document(page_ir_fixture())
        page = processed["pages"][0]
        node = next(node for node in page["nodes"] if node["node_id"] == "p008-n001")

        self.assertEqual(
            [span["span_type"] for span in node["spans"]],
            ["TEXT", "UNKNOWN", "TEXT"],
        )
        math_span = node["spans"][1]
        self.assertTrue(math_span["math_span_candidate"])
        self.assertEqual(math_span["text"], "f(x)=x^2+1")
        self.assertIn("bbox", math_span)
        self.assertEqual(node["layout"]["math_span_count"], 1)
        self.assertIn(
            "MATH_SPAN_CANDIDATE_SPLIT",
            {issue["code"] for issue in node["issues"]},
        )
        self.assertTrue(validate_document_ir(processed)["schema_valid"])

    def test_leaves_plain_text_node_untouched(self):
        processed = detect_math_spans_in_document(page_ir_fixture())
        page = processed["pages"][0]
        node = next(node for node in page["nodes"] if node["node_id"] == "p008-n002")

        self.assertEqual(len(node["spans"]), 1)
        self.assertEqual(node["spans"][0]["span_type"], "TEXT")
        self.assertNotIn("math_span_count", node["layout"])

    def test_flags_known_math_candidate_without_token_data(self):
        processed = detect_math_spans_in_document(page_ir_fixture())
        page = processed["pages"][0]
        node = next(node for node in page["nodes"] if node["node_id"] == "p008-n003")

        self.assertIn(
            "MATH_SPAN_SPLIT_UNAVAILABLE_NO_TOKEN_DATA",
            {issue["code"] for issue in node["issues"]},
        )

    def test_builds_report(self):
        processed = detect_math_spans_in_document(page_ir_fixture())
        report = math_span_report(processed)

        self.assertEqual(report["total_split_node_count"], 1)
        self.assertEqual(report["total_math_span_count"], 1)
        self.assertEqual(report["pages"][0]["nodes"][0]["math_span_texts"], ["f(x)=x^2+1"])


def token(text, x, width=None, y=0, height=20):
    return {
        "text": text,
        "bbox": {"x": x, "y": y, "width": width if width is not None else max(len(text) * 12, 10), "height": height},
    }


def page_ir_fixture():
    return {
        "document_manifest": {"book_id": "book", "page_count": 1},
        "engine_manifest": {},
        "validation_summary": {},
        "pages": [{
            "page_id": "p008",
            "page_geometry": {"width": 1000, "height": 1000},
            "nodes": [
                text_node_with_tokens(
                    "p008-n001",
                    "함수 f(x)=x^2+1 이다.",
                    0,
                    [token("함수", x=10), token("f(x)=x^2+1", x=70), token("이다.", x=220)],
                ),
                text_node_with_tokens(
                    "p008-n002",
                    "그림과 같이 삼각형을 그린다.",
                    1,
                    [token("그림과", x=10), token("같이", x=90), token("삼각형을", x=140), token("그린다.", x=230)],
                ),
                math_candidate_node_without_tokens("p008-n003", "x=na 또는 x=-na이다.", 2),
            ],
            "reading_order": ["p008-n001", "p008-n002", "p008-n003"],
            "parse_issues": [],
            "quality_report": {"status": "PASS"},
        }],
    }


def text_node_with_tokens(node_id, text, index, tokens):
    y = 10 + index * 30
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": {"x": 10, "y": y, "width": 500, "height": 20},
        "normalized_bbox": {"x": 0.01, "y": y / 1000, "width": 0.5, "height": 0.02},
        "reading_order_index": index,
        "confidence": 0.9,
        "source_engine": "fixture",
        "issues": [],
        "raw_text": text,
        "normalized_text": text,
        "spans": [{"span_type": "TEXT", "text": text}],
        "layout": {"tokens": tokens},
    }


def math_candidate_node_without_tokens(node_id, text, index):
    node = text_node_with_tokens(node_id, text, index, [])
    node["layout"] = {"math_candidate": {"is_candidate": True, "score": 6}}
    return node


if __name__ == "__main__":
    unittest.main()
