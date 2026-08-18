"""한글 자모 결합 -> 점자 (한글 점자 규정 제1장, printed p.3-13).

Values here come from a delegated extraction pass against the same source
PDF as `cell_encoding.py` (문화체육관광부고시 제2024-0005호), delivered as
`2024_한국점자규정_요청양식_점형추출.md`. Every table/rule below was cross-
checked by hand-deriving all 9 worked example words (거리, 아버지, 국보,
꾸러미, 아리랑, 매미, 얘기, 쉼터, 나이) and all 7 abbreviation/약어 worked
examples (가지, 강산, 억새, 자연, 이것, 까치, 성가, 그래서인지, 그러면서,
그런데도, 그리하여도) through the algorithm implemented here and confirming
every cell matches the document's own decode -- see
`project-braille-hangul-jamo` memory for the full derivation log. The
Unicode syllable-decomposition tables (초성/중성/종성 index order) are the
standard Unicode Hangul Syllable algorithm, not a regulation fact -- nothing
to verify there beyond arithmetic.

Unverified/unsupported input raises `NotImplementedError` rather than
guessing, per this project's braille policy (see `cell_encoding.py`'s module
docstring).
"""

from __future__ import annotations

from document_parser.accessibility.braille.cell_encoding import (
    BrailleCell,
    FINAL_CONSONANT_CELLS,
    INITIAL_CONSONANT_CELLS,
    cell,
)

# ---- Unicode Hangul syllable decomposition (standard algorithm, not a
# regulation fact) ----
_INITIAL_JAMO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_MEDIAL_JAMO = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_FINAL_JAMO = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
_SYLLABLE_BASE = 0xAC00
_SYLLABLE_COUNT = 19 * 21 * 28


def is_hangul_syllable(ch: str) -> bool:
    return len(ch) == 1 and 0 <= (ord(ch) - _SYLLABLE_BASE) < _SYLLABLE_COUNT


def decompose_syllable(ch: str) -> tuple[str, str, str | None]:
    """A precomposed Hangul syllable -> (초성, 중성, 종성 or None)."""
    code = ord(ch) - _SYLLABLE_BASE
    final_idx = code % 28
    medial_idx = (code // 28) % 21
    initial_idx = code // (28 * 21)
    final = _FINAL_JAMO[final_idx] if final_idx > 0 else None
    return _INITIAL_JAMO[initial_idx], _MEDIAL_JAMO[medial_idx], final


# ---- 한글 점자 규정 제6항-제7항: 모음자(중성) 21개, printed p.5-6 ----
# 기본 모음 10개(제6항) + 그 밖의 모음 11개(제7항). ㅒ/ㅙ/ㅞ/ㅟ는 2칸.
VOWEL_CELLS: dict[str, tuple[BrailleCell, ...]] = {
    "ㅏ": (cell(1, 2, 6),),
    "ㅑ": (cell(3, 4, 5),),
    "ㅓ": (cell(2, 3, 4),),
    "ㅕ": (cell(1, 5, 6),),
    "ㅗ": (cell(1, 3, 6),),
    "ㅛ": (cell(3, 4, 6),),
    "ㅜ": (cell(1, 3, 4),),
    "ㅠ": (cell(1, 4, 6),),
    "ㅡ": (cell(2, 4, 6),),
    "ㅣ": (cell(1, 3, 5),),
    "ㅐ": (cell(1, 2, 3, 5),),
    "ㅒ": (cell(3, 4, 5), cell(1, 2, 3, 5)),
    "ㅔ": (cell(1, 3, 4, 5),),
    "ㅖ": (cell(3, 4),),
    "ㅘ": (cell(1, 2, 3, 6),),
    "ㅙ": (cell(1, 2, 3, 6), cell(1, 2, 3, 5)),
    "ㅚ": (cell(1, 3, 4, 5, 6),),
    "ㅝ": (cell(1, 2, 3, 4),),
    "ㅞ": (cell(1, 2, 3, 4), cell(1, 2, 3, 5)),
    "ㅟ": (cell(1, 3, 4), cell(1, 2, 3, 5)),
    "ㅢ": (cell(2, 4, 5, 6),),
}

# ---- 한글 점자 규정: 된소리(경음) 초성 ----
# 된소리 초성은 된소리표 {6} + 기본 자음자로 적는다 ("꾸러미" 예시로 확인:
# ㄲ -> {6};{4}(ㄱ)).
TENSE_MARKER_CELL: BrailleCell = cell(6)
TENSE_INITIAL_BASE: dict[str, str] = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}

# ---- 한글 점자 규정 제5항: 겹받침, printed p.4 ----
# 각 받침 글자를 어울러(풀어서) 이어 적는다 -- 조합 자체는 표준 유니코드
# 자모 분해에서 나오는 사실이고, 여기 11개 목록만 정확히 대응 관계다.
COMPOUND_FINAL_PARTS: dict[str, tuple[str, str]] = {
    "ㄳ": ("ㄱ", "ㅅ"), "ㄵ": ("ㄴ", "ㅈ"), "ㄶ": ("ㄴ", "ㅎ"),
    "ㄺ": ("ㄹ", "ㄱ"), "ㄻ": ("ㄹ", "ㅁ"), "ㄼ": ("ㄹ", "ㅂ"),
    "ㄽ": ("ㄹ", "ㅅ"), "ㄾ": ("ㄹ", "ㅌ"), "ㄿ": ("ㄹ", "ㅍ"),
    "ㅀ": ("ㄹ", "ㅎ"), "ㅄ": ("ㅂ", "ㅅ"),
}

# ---- 한글 점자 규정 제13항: 약자 11개 (가나다마바사자카타파하), printed p.9 ----
# 이 11개는 전부 "자음+ㅏ, 받침 없음" 형태라 초성으로 키를 잡는다. 실제
# 단어에 받침이 붙으면(예: "강"=가+ㅇ받침) 이 약자 셀 뒤에 받침 셀을 그대로
# 이어 적는다 -- "강산" 예시({1,2,4,6};{2,3,5,6};{1,2,3};{2,5})로 확인:
# 강=가약자+ㅇ받침, 산=사약자+ㄴ받침.
BASE_ABBREVIATION_BY_INITIAL: dict[str, BrailleCell] = {
    "ㄱ": cell(1, 2, 4, 6),  # 가
    "ㄴ": cell(1, 4),         # 나
    "ㄷ": cell(2, 4),         # 다
    "ㅁ": cell(1, 5),         # 마
    "ㅂ": cell(4, 5),         # 바
    "ㅅ": cell(1, 2, 3),      # 사
    "ㅈ": cell(4, 6),         # 자
    "ㅋ": cell(1, 2, 4),      # 카
    "ㅌ": cell(1, 2, 5),      # 타
    "ㅍ": cell(1, 4, 5),      # 파
    "ㅎ": cell(2, 4, 5),      # 하
}

# ---- 한글 점자 규정 제14항: 제13항 약자의 예외 ----
# "나,다,마,바,자,카,타,파,하"(가·사는 명시적으로 제외됨)에 모음이 붙어
# 나올 때(=다음 음절의 초성이 ㅇ일 때)에는 약자를 쓰지 않는다. "나이"
# ({1,4};{1,2,6};{1,3,5} -- 나=ㄴ+ㅏ 그대로, 약자 아님)와 "자연"
# ({4,6};{1,2,6};{1,6} -- 자=ㅈ+ㅏ 그대로, 이어지는 연=ㅇ초성이라 예외
# 적용) 두 예시로 확인. 가/사는 이 예외에 안 걸린다("가지", "성가" 예시에서
# 뒤에 오는 음절과 무관하게 항상 약자로 적힘).
EXCEPTION_APPLIES_TO_INITIALS: frozenset[str] = frozenset({"ㄴ", "ㄷ", "ㅁ", "ㅂ", "ㅈ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"})

# ---- 한글 점자 규정 제15항: 약자 15개 (억언얼연열영옥온옹운울은을인것), printed p.10 ----
# 제13항과 달리 이 음절들은 (초성,중성,종성)을 통째로 포함한 고정 점형이다
# -- "것"만 2칸, 나머지는 1칸.
SYLLABLE_ABBREVIATION_CELLS: dict[str, tuple[BrailleCell, ...]] = {
    "억": (cell(1, 4, 5, 6),),
    "언": (cell(2, 3, 4, 5, 6),),
    "얼": (cell(2, 3, 4, 5),),
    "연": (cell(1, 6),),
    "열": (cell(1, 2, 5, 6),),
    "영": (cell(1, 2, 4, 5, 6),),
    "옥": (cell(1, 3, 4, 6),),
    "온": (cell(1, 2, 3, 5, 6),),
    "옹": (cell(1, 2, 3, 4, 5, 6),),
    "운": (cell(1, 2, 4, 5),),
    "울": (cell(1, 2, 3, 4, 6),),
    "은": (cell(1, 3, 5, 6),),
    "을": (cell(2, 3, 4, 6),),
    "인": (cell(1, 2, 3, 4, 5),),
    "것": (cell(4, 5, 6), cell(2, 3, 4)),
}
YEONG_SUFFIX_CELL: BrailleCell = SYLLABLE_ABBREVIATION_CELLS["영"][0]

# ---- 한글 점자 규정 제16항: 된소리 + 약자 ----
# "까,싸,껏"만 명시적으로 주어진 예시 -- 다른 된소리+약자 조합으로
# 일반화하지 않는다(예: "따"가 다약자를 쓰는지는 근거가 없다).
TENSE_ABBREVIATION_CELLS: dict[str, tuple[BrailleCell, ...]] = {
    "까": (TENSE_MARKER_CELL, BASE_ABBREVIATION_BY_INITIAL["ㄱ"]),
    "싸": (TENSE_MARKER_CELL, BASE_ABBREVIATION_BY_INITIAL["ㅅ"]),
    "껏": (TENSE_MARKER_CELL, *SYLLABLE_ABBREVIATION_CELLS["것"]),
}

# ---- 한글 점자 규정 제17항: '성·썽·정·쩡·청' ----
# "ㅅ,ㅆ,ㅈ,ㅉ,ㅊ 뒤에 영 약자를 붙인다"는 일반 규칙 -- "성가" 예시로 성=
# {6}(ㅅ);{1,2,4,5,6}(영)을 직접 재확인, 썽/쩡은 같은 규칙을 그대로 적용한
# 것이라(개별 예시는 없음) 성/정/청보다 확신도가 약간 낮다.
YEONG_SUFFIX_SYLLABLES: dict[str, tuple[BrailleCell, ...]] = {
    "성": (INITIAL_CONSONANT_CELLS["ㅅ"], YEONG_SUFFIX_CELL),
    "정": (INITIAL_CONSONANT_CELLS["ㅈ"], YEONG_SUFFIX_CELL),
    "청": (INITIAL_CONSONANT_CELLS["ㅊ"], YEONG_SUFFIX_CELL),
    "썽": (TENSE_MARKER_CELL, INITIAL_CONSONANT_CELLS["ㅅ"], YEONG_SUFFIX_CELL),
    "쩡": (TENSE_MARKER_CELL, INITIAL_CONSONANT_CELLS["ㅈ"], YEONG_SUFFIX_CELL),
}

# ---- 한글 점자 규정 제18항: 약어 7개, printed p.12-13 ----
# 단어 전체(또는 그 단어로 시작하는 더 긴 단어의 접두부)를 2칸으로 줄인다.
WORD_ABBREVIATION_CELLS: dict[str, tuple[BrailleCell, ...]] = {
    "그래서": (cell(1), cell(2, 3, 4)),
    "그러나": (cell(1), cell(1, 4)),
    "그러면": (cell(1), cell(2, 5)),
    "그러므로": (cell(1), cell(2, 6)),
    "그런데": (cell(1), cell(1, 3, 4, 5)),
    "그리고": (cell(1), cell(1, 3, 6)),
    "그리하여": (cell(1), cell(1, 5, 6)),
}
_WORD_ABBREVIATIONS_LONGEST_FIRST = sorted(WORD_ABBREVIATION_CELLS, key=len, reverse=True)


def _starts_with_vowel_initial(ch: str) -> bool:
    if not is_hangul_syllable(ch):
        return False
    initial, _medial, _final = decompose_syllable(ch)
    return initial == "ㅇ"


def _final_cells(final: str | None) -> list[BrailleCell]:
    if final is None:
        return []
    if final in COMPOUND_FINAL_PARTS:
        first, second = COMPOUND_FINAL_PARTS[final]
        return [FINAL_CONSONANT_CELLS[first], FINAL_CONSONANT_CELLS[second]]
    return [FINAL_CONSONANT_CELLS[final]]


def _initial_cells(initial: str) -> list[BrailleCell]:
    # 제1항 다만1: 첫소리 'ㅇ'은 점자로 표기하지 않는다.
    if initial == "ㅇ":
        return []
    if initial in TENSE_INITIAL_BASE:
        return [TENSE_MARKER_CELL, INITIAL_CONSONANT_CELLS[TENSE_INITIAL_BASE[initial]]]
    return [INITIAL_CONSONANT_CELLS[initial]]


def _plain_syllable_cells(ch: str) -> list[BrailleCell]:
    initial, medial, final = decompose_syllable(ch)
    cells = _initial_cells(initial)
    cells.extend(VOWEL_CELLS[medial])
    cells.extend(_final_cells(final))
    return cells


def translate_hangul_text(text: str) -> list[BrailleCell]:
    """A run of Hangul text (and plain spaces) -> logical braille cells,
    applying 약어(제18항, word-level) then 약자(제13항/15항, syllable-level,
    with 제14항's exception and 제16항/17항's fixed combinations) before
    falling back to plain 초성+중성(+종성) decomposition."""
    cells: list[BrailleCell] = []
    i = 0
    n = len(text)
    while i < n:
        matched_word = next((w for w in _WORD_ABBREVIATIONS_LONGEST_FIRST if text.startswith(w, i)), None)
        if matched_word is not None:
            cells.extend(WORD_ABBREVIATION_CELLS[matched_word])
            i += len(matched_word)
            continue

        ch = text[i]

        if ch == " ":
            i += 1
            continue

        if ch in TENSE_ABBREVIATION_CELLS:
            cells.extend(TENSE_ABBREVIATION_CELLS[ch])
            i += 1
            continue

        if ch in YEONG_SUFFIX_SYLLABLES:
            cells.extend(YEONG_SUFFIX_SYLLABLES[ch])
            i += 1
            continue

        if is_hangul_syllable(ch):
            initial, medial, final = decompose_syllable(ch)
            if medial == "ㅏ" and initial in BASE_ABBREVIATION_BY_INITIAL:
                next_ch = text[i + 1] if i + 1 < n else None
                blocked = (
                    initial in EXCEPTION_APPLIES_TO_INITIALS
                    and next_ch is not None
                    and _starts_with_vowel_initial(next_ch)
                )
                if not blocked:
                    cells.append(BASE_ABBREVIATION_BY_INITIAL[initial])
                    cells.extend(_final_cells(final))
                    i += 1
                    continue
            if ch in SYLLABLE_ABBREVIATION_CELLS:
                cells.extend(SYLLABLE_ABBREVIATION_CELLS[ch])
                i += 1
                continue
            cells.extend(_plain_syllable_cells(ch))
            i += 1
            continue

        raise NotImplementedError(
            f"Character {ch!r} in {text!r} is not a decodable Hangul syllable "
            "and no other verified rule applies here (digits/Latin/punctuation "
            "inside Hangul text are not handled by this function)."
        )
    return cells
