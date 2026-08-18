import unittest

from document_parser.accessibility.braille.cell_encoding import cell
from document_parser.accessibility.braille.hangul import (
    COMPOUND_FINAL_PARTS,
    decompose_syllable,
    translate_hangul_text,
)


class SyllableDecompositionTests(unittest.TestCase):
    """표준 유니코드 한글 음절 분해 -- 규정 사실이 아니라 산술이므로,
    유니코드 자체의 코드포인트 배치가 맞는지만 확인한다."""

    def test_simple_syllable_with_no_final(self):
        self.assertEqual(decompose_syllable("가"), ("ㄱ", "ㅏ", None))

    def test_syllable_with_simple_final(self):
        self.assertEqual(decompose_syllable("국"), ("ㄱ", "ㅜ", "ㄱ"))

    def test_syllable_with_compound_final(self):
        # 닭 = ㄷ+ㅏ+ㄺ(겹받침)
        self.assertEqual(decompose_syllable("닭"), ("ㄷ", "ㅏ", "ㄺ"))
        self.assertIn("ㄺ", COMPOUND_FINAL_PARTS)


class WordDecompositionTests(unittest.TestCase):
    """한글 점자 규정 제1항-제7항(초성/중성/종성/겹받침), 위임 문서에서 받은
    9개 실제 단어 예시로 전부 교차검증했다."""

    def test_geori_no_final(self):
        self.assertEqual(translate_hangul_text("거리"), [
            cell(4), cell(2, 3, 4), cell(5), cell(1, 3, 5),
        ])

    def test_abeoji_initial_ieung_omitted(self):
        # 아버지: 첫 음절 '아'는 초성 ㅇ이 생략되어 모음만 남는다.
        self.assertEqual(translate_hangul_text("아버지"), [
            cell(1, 2, 6), cell(4, 5), cell(2, 3, 4), cell(4, 6), cell(1, 3, 5),
        ])

    def test_gukbo_simple_final(self):
        self.assertEqual(translate_hangul_text("국보"), [
            cell(4), cell(1, 3, 4), cell(1), cell(4, 5), cell(1, 3, 6),
        ])

    def test_kkurumi_tense_initial(self):
        # 꾸러미: ㄲ(된소리) = 된소리표{6} + 기본 자음 ㄱ{4}.
        self.assertEqual(translate_hangul_text("꾸러미"), [
            cell(6), cell(4), cell(1, 3, 4), cell(5), cell(2, 3, 4), cell(1, 5), cell(1, 3, 5),
        ])

    def test_arirang_final_ieung(self):
        self.assertEqual(translate_hangul_text("아리랑"), [
            cell(1, 2, 6), cell(5), cell(1, 3, 5), cell(5), cell(1, 2, 6), cell(2, 3, 5, 6),
        ])

    def test_maemi_double_width_vowel_ae(self):
        self.assertEqual(translate_hangul_text("매미"), [
            cell(1, 5), cell(1, 2, 3, 5), cell(1, 5), cell(1, 3, 5),
        ])

    def test_yaegi_two_cell_vowel_yae(self):
        # 얘: ㅑㅔ 합성 모음 ㅒ는 2칸.
        self.assertEqual(translate_hangul_text("얘기"), [
            cell(3, 4, 5), cell(1, 2, 3, 5), cell(4), cell(1, 3, 5),
        ])

    def test_shwimteo_two_cell_vowel_wi_and_final(self):
        self.assertEqual(translate_hangul_text("쉼터"), [
            cell(6), cell(1, 3, 4), cell(1, 2, 3, 5), cell(2, 6), cell(1, 2, 5), cell(2, 3, 4),
        ])


class AbbreviationTests(unittest.TestCase):
    """한글 점자 규정 제13항-제17항(약자), 위임 문서의 실제 예시로
    교차검증했다. 핵심 발견: 제13항 약자(가나다마바사자카타파하)는 받침이
    없는 기본형뿐 아니라, 받침이 붙은 실제 단어에도 적용되고(예: "강"=
    가약자+ㅇ받침) 그 받침은 약자 셀 뒤에 그대로 이어 적는다."""

    def test_naui_exception_blocks_abbreviation(self):
        # 나이: '나' 뒤에 초성 ㅇ 음절('이')이 와서 제14항 예외가 적용 --
        # 약자 대신 ㄴ+ㅏ로 그대로 적는다.
        self.assertEqual(translate_hangul_text("나이"), [
            cell(1, 4), cell(1, 2, 6), cell(1, 3, 5),
        ])

    def test_gaji_ga_always_abbreviates(self):
        # 가지: '가'는 제14항 예외 대상이 아니라(가/사는 명시적으로 제외)
        # 뒤에 오는 음절과 무관하게 항상 약자로 적힌다.
        self.assertEqual(translate_hangul_text("가지"), [
            cell(1, 2, 4, 6), cell(4, 6), cell(1, 3, 5),
        ])

    def test_gangsan_abbreviation_with_appended_final(self):
        # 강산: 강=가약자+ㅇ받침, 산=사약자+ㄴ받침 -- 약자에 받침이 붙는
        # 핵심 사례.
        self.assertEqual(translate_hangul_text("강산"), [
            cell(1, 2, 4, 6), cell(2, 3, 5, 6), cell(1, 2, 3), cell(2, 5),
        ])

    def test_eoksae_syllable_15_abbreviation(self):
        self.assertEqual(translate_hangul_text("억새"), [
            cell(1, 4, 5, 6), cell(6), cell(1, 2, 3, 5),
        ])

    def test_jayeon_exception_applies_to_ja(self):
        # 자연: '자'는 제14항 예외 대상이고 뒤가 '연'(초성 ㅇ)이라 예외
        # 적용 -- 약자 대신 ㅈ+ㅏ로 적고, '연'은 제15항 약자로 적는다.
        self.assertEqual(translate_hangul_text("자연"), [
            cell(4, 6), cell(1, 2, 6), cell(1, 6),
        ])

    def test_igeot_syllable_15_two_cell_abbreviation(self):
        self.assertEqual(translate_hangul_text("이것"), [
            cell(1, 3, 5), cell(4, 5, 6), cell(2, 3, 4),
        ])

    def test_kkachi_tense_abbreviation(self):
        # 까치: 까 = 된소리표 + 가약자 (제16항).
        self.assertEqual(translate_hangul_text("까치"), [
            cell(6), cell(1, 2, 4, 6), cell(5, 6), cell(1, 3, 5),
        ])

    def test_seongga_yeong_suffix_rule(self):
        # 성가: 성 = ㅅ초성 + 영약자 (제17항), 가 = 약자.
        self.assertEqual(translate_hangul_text("성가"), [
            cell(6), cell(1, 2, 4, 5, 6), cell(1, 2, 4, 6),
        ])


class WordAbbreviationTests(unittest.TestCase):
    """한글 점자 규정 제18항(약어), 위임 문서의 실제 예시로 교차검증했다.
    긴 단어의 접두부로도 매칭된다(예: "그래서인지"는 "그래서"만 줄이고
    "인지"는 그대로 이어 적는다)."""

    def test_word_abbreviation_as_prefix_of_longer_word(self):
        self.assertEqual(translate_hangul_text("그래서인지"), [
            cell(1), cell(2, 3, 4), cell(1, 2, 3, 4, 5), cell(4, 6), cell(1, 3, 5),
        ])

    def test_geureomyeonseo(self):
        self.assertEqual(translate_hangul_text("그러면서"), [
            cell(1), cell(2, 5), cell(6), cell(2, 3, 4),
        ])

    def test_geureondedo(self):
        self.assertEqual(translate_hangul_text("그런데도"), [
            cell(1), cell(1, 3, 4, 5), cell(2, 4), cell(1, 3, 6),
        ])

    def test_geurihayeodo(self):
        self.assertEqual(translate_hangul_text("그리하여도"), [
            cell(1), cell(1, 5, 6), cell(2, 4), cell(1, 3, 6),
        ])


class UnsupportedInputTests(unittest.TestCase):
    def test_non_hangul_character_raises(self):
        with self.assertRaises(NotImplementedError):
            translate_hangul_text("A")

    def test_space_is_skipped_without_producing_a_cell(self):
        self.assertEqual(translate_hangul_text(" "), [])


if __name__ == "__main__":
    unittest.main()
