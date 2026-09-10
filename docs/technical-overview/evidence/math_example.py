"""PASS 6 pure transformation probe; no OCR, audio, serial or server access."""
import json
from document_parser.math.latex_ast import parse_latex_to_ast
from document_parser.accessibility.speech import math_ast_to_speech
from document_parser.accessibility.braille.math_translator import math_focus_item_to_braille
from document_parser.accessibility.braille.viewport import build_frame

raw = r"\frac{1}{2}"
parsed = parse_latex_to_ast(raw)
assert not parsed.issues and not parsed.unconsumed_tokens
item = {"ast_status": "VALID", "presentation_ast": parsed.ast}
dots = math_focus_item_to_braille(item)
window = build_frame("documentation-example", dots, 0, 10)
record = {
    "scope": "synthetic pure function example; no physical output",
    "input_latex": raw,
    "ast": parsed.ast,
    "issues": parsed.issues,
    "unconsumed_tokens": parsed.unconsumed_tokens,
    "speech_rule_output": math_ast_to_speech(parsed.ast),
    "logical_dot_sets": [sorted(cell) for cell in dots],
    "window": window,
    "ten_cell_payload_after_zero_padding": window["cells"] + [0] * (10 - len(window["cells"])),
}
print(json.dumps(record, ensure_ascii=False, indent=2))
