import unittest

from document_parser.accessibility.naturalization import (
    KoreanMathSpeechNaturalizer,
    adjacent_inline_math_lexical_suffix,
)
from document_parser.accessibility.braille import braille_scrollable_spans
from document_parser.accessibility.speech import math_ast_to_speech, text_focus_item_to_speech
from document_parser.datapack.ingest import enumerate_utterances

from .support import load_accessible_document


class KoreanMathSpeechNaturalizerTests(unittest.TestCase):
    def setUp(self):
        self.naturalizer = KoreanMathSpeechNaturalizer()

    def test_all_supported_particle_pairs_follow_hangul_jongseong(self):
        self.assertEqual(self.naturalizer.attach_particle("값", "topic"), "값은")
        self.assertEqual(self.naturalizer.attach_particle("사과", "topic"), "사과는")
        self.assertEqual(self.naturalizer.attach_particle("값", "subject"), "값이")
        self.assertEqual(self.naturalizer.attach_particle("사과", "subject"), "사과가")
        self.assertEqual(self.naturalizer.attach_particle("값", "object"), "값을")
        self.assertEqual(self.naturalizer.attach_particle("사과", "object"), "사과를")
        self.assertEqual(self.naturalizer.attach_particle("값", "comitative"), "값과")
        self.assertEqual(self.naturalizer.attach_particle("사과", "comitative"), "사과와")

    def test_numbers_follow_their_korean_pronunciation(self):
        self.assertEqual(self.naturalizer.attach_particle("1", "comitative"), "1과")
        self.assertEqual(self.naturalizer.attach_particle("2", "comitative"), "2와")
        self.assertEqual(self.naturalizer.attach_particle("10", "comitative"), "10과")
        self.assertEqual(self.naturalizer.attach_particle("10000", "topic"), "10000은")
        self.assertEqual(self.naturalizer.attach_particle("2.5", "topic"), "2.5는")

    def test_latin_identifiers_follow_their_korean_letter_names(self):
        self.assertEqual(self.naturalizer.attach_particle("m", "topic"), "m은")
        self.assertEqual(self.naturalizer.attach_particle("x", "topic"), "x는")

    def test_math_renderer_accepts_a_replacement_naturalizer(self):
        class ReplacementNaturalizer:
            def attach_particle(self, phrase, role):
                return f"{phrase}<{role}>"

            def fraction(self, numerator, denominator):
                return f"fraction({denominator},{numerator})"

        ast = {
            "type": "Fraction",
            "numerator": {"type": "Number", "value": "1"},
            "denominator": {"type": "Number", "value": "2"},
        }
        self.assertEqual(math_ast_to_speech(ast, ReplacementNaturalizer()), "fraction(2,1)")


class InlineMathLexicalSuffixTests(unittest.TestCase):
    def test_registered_suffix_must_be_directly_adjacent(self):
        self.assertEqual(adjacent_inline_math_lexical_suffix("축과 만난다"), "축")
        self.assertIsNone(adjacent_inline_math_lexical_suffix(" 축과 만난다"))

    def test_unregistered_korean_particle_does_not_hide_a_real_variable(self):
        self.assertIsNone(adjacent_inline_math_lexical_suffix("의 값"))
        self.assertIsNone(adjacent_inline_math_lexical_suffix("이라 하자"))

    def test_p030_y_axis_stays_in_sentence_but_is_not_a_standalone_target(self):
        document = load_accessible_document("p030")
        item = next(
            item
            for item in document["pages"][0]["focus_items"]
            if item["id"] == "p030-vl006-L01"
        )
        y_axis_span = next(
            span
            for span in item["spans"]
            if span.get("kind") == "MATH" and span.get("text") == "y"
        )

        self.assertIs(y_axis_span["standalone_accessibility"], False)
        self.assertEqual(y_axis_span["standalone_suppression_reason"], "ADJACENT_LEXICAL_SUFFIX:축")
        self.assertIn("y축과 만나는", text_focus_item_to_speech(item))

        standalone_formulae = [span["text"] for span in braille_scrollable_spans(item)]
        self.assertNotIn("y", standalone_formulae)
        self.assertIn("x=2", standalone_formulae)

        utterances = enumerate_utterances({"pages": [{"focus_items": [item]}]})
        self.assertIn(item["id"], utterances)
        self.assertNotIn("y", [text for key, text in utterances.items() if key != item["id"]])

    def test_p030_choice_fraction_is_naturalized_before_piper(self):
        document = load_accessible_document("p030")
        item = next(
            item
            for item in document["pages"][0]["focus_items"]
            if item["id"] == "p030-vl006-L02"
        )

        spoken = text_focus_item_to_speech(item)
        self.assertIn("① 4분의 루트 71", spoken)
        self.assertNotIn("분수 시작", spoken)


if __name__ == "__main__":
    unittest.main()
