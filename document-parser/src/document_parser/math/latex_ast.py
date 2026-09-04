"""LaTeX -> Presentation AST parser and validator.

Converts a `raw_formula` LaTeX string (from `PaddleOcrVlAdapter`'s display_formula
blocks or `PaddleFormulaOcrAdapter`) into the tree shape defined by
`schemas/math-ast.schema.json`. Nothing upstream of this module produces that
tree today: MATH nodes only carry a flat LaTeX string, which is not something a
braille translator can walk (it cannot find "the denominator" in a string).

Scope (기획서 §12.4: "실제 골든 데이터에 등장하는 문법부터 지원"): this covers the
LaTeX actually observed in this project's recognized formulas so far --
fractions, powers/subscripts, radicals (with index), relations, named functions,
parentheses, unary minus, and basic decorations (\overline, \boldsymbol, etc, kept
as a `decoration` tag on the wrapped node rather than dropped). It is not a
general LaTeX grammar. Anything not covered becomes an `Unknown` node with the
raw text preserved (기획서 §12.4's `UnknownCommand` policy) rather than being
silently dropped or aborting the whole parse -- a garbled fragment in one part of
a formula must not erase the parts that did parse correctly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

FUNCTION_NAMES = {"sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "lim", "exp"}

GREEK_AND_CONSTANTS = {
    "pi": "π", "theta": "θ", "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "Delta": "Δ", "lambda": "λ", "mu": "μ", "phi": "φ", "varphi": "φ", "omega": "ω",
    "infty": "∞", "sigma": "σ", "Sigma": "Σ",
}

# Commands that only decorate their argument (segment/vector/bold notation etc).
# There is no dedicated AST node type for these in math-ast.schema.json, so the
# inner argument is parsed normally and tagged with a `decoration` field (schema
# allows additional properties) instead of dropping the notation.
DECORATION_COMMANDS = {"overline", "underline", "widehat", "hat", "vec", "boldsymbol", "mathbf", "mathrm"}

RELATION_TOKENS = {"=", "<", ">", "\\geq", "\\leq", "\\neq", "\\approx", "\\equiv", "≥", "≤", "≠", "≈"}
RELATION_DISPLAY = {
    "\\geq": "≥", "\\leq": "≤", "\\neq": "≠", "\\approx": "≈", "\\equiv": "≡",
}
MULT_TOKENS = {"\\times", "\\cdot", "\\div", "*", "×", "÷", "·"}
MULT_DISPLAY = {"\\times": "×", "\\cdot": "·", "\\div": "÷"}

SKIP_COMMANDS = {"quad", "qquad", "!", ",", ";", ":", "left", "right", "displaystyle", "textstyle"}

TOKEN_PATTERN = re.compile(
    r"\\\\"              # LaTeX row break (two literal backslashes) -- must
                          # be checked before the \command alternative below,
                          # otherwise a row break immediately followed by a
                          # letter (e.g. "...\\\\b(x-1)", common in \cases
                          # bodies) greedily matches as a bogus one-letter
                          # command "\b" instead of two separate row-break
                          # backslash tokens.
    r"|\\[a-zA-Z]+"       # LaTeX command
    r"|\d+\.\d+|\d+"     # number
    r"|[a-zA-Z]"         # single-letter identifier
    r"|\s+"              # whitespace (skipped)
    r"|."                # any other single character
)


@dataclass(frozen=True)
class Token:
    kind: str  # "command" | "number" | "letter" | "char"
    text: str


@dataclass
class AstParseResult:
    ast: dict[str, object]
    unconsumed_tokens: list[str] = field(default_factory=list)
    issues: list[dict[str, object]] = field(default_factory=list)


def parse_latex_to_ast(raw_latex: str) -> AstParseResult:
    tokens = tokenize(raw_latex)
    if len(tokens) == 1 and tokens[0].kind == "char" and tokens[0].text in {"+", "-"}:
        # A lone "+"/"-" with no operand (e.g. a 부호표 sign-table cell) isn't
        # a valid expression under the normal binary-operator grammar --
        # every other rule in this file only recognizes +/- as the connective
        # between two already-parsed operands (see parse_additive), so a
        # single bare sign would otherwise fall through parse_primary's
        # "unrecognized token" branch and become Unknown/PARTIAL. It's still
        # one real, already braille- and speech-verified symbol (사칙연산
        # 제2항), so treat "the whole formula is one bare sign" as its own
        # case rather than routing it through the binary-expression grammar
        # at all. Gated tightly (exactly one token) so this can never fire
        # for any input that already parses successfully today.
        return AstParseResult(ast={"type": "Operator", "value": tokens[0].text}, unconsumed_tokens=[], issues=[])
    parser = _Parser(tokens)
    ast = parser.parse_row()
    unconsumed = [tok.text for tok in tokens[parser.pos:]]
    result = AstParseResult(ast=ast, unconsumed_tokens=unconsumed, issues=list(parser.issues))
    if unconsumed:
        result.issues.append({
            "code": "AST_UNCONSUMED_TOKENS",
            "severity": "warning",
            "message": f"{len(unconsumed)} token(s) left over after parsing: {''.join(unconsumed)!r}",
        })
    result.issues.extend(validate_ast(ast))
    return result


def tokenize(raw_latex: str) -> list[Token]:
    tokens: list[Token] = []
    for match in TOKEN_PATTERN.finditer(raw_latex):
        text = match.group(0)
        if text.strip() == "":
            continue
        if text == "\\\\":
            # Row break: split into the two single-backslash `char` tokens the
            # rest of the parser (`_at_row_break`) expects, rather than one
            # 2-char token -- keeps every downstream consumer unchanged.
            tokens.append(Token("char", "\\"))
            tokens.append(Token("char", "\\"))
        elif text.startswith("\\") and len(text) > 1:
            # A real \command always has >=1 letter after the backslash (the
            # TOKEN_PATTERN command alternative requires it). A bare "\\" with
            # nothing after it only reaches here via the catch-all "." fallback
            # (e.g. the escaped-delimiter "\{" in "\left\{" tokenizes as this
            # lone backslash followed by its own "{" char token) and must be
            # classified as a "char" token, not a zero-length command.
            tokens.append(Token("command", text[1:]))
        elif re.fullmatch(r"\d+\.\d+|\d+", text):
            tokens.append(Token("number", text))
        elif re.fullmatch(r"[a-zA-Z]", text):
            tokens.append(Token("letter", text))
        else:
            tokens.append(Token("char", text))
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.issues: list[dict[str, object]] = []
        # `\begin{name}` pushes, `\end` pops -- lets `parse_row()` tag
        # `AlignedRows` with which environment (cases/array/aligned/matrix/...)
        # produced it, since braille/TTS need to know that to pick the right
        # presentation rule (there is no single universal "multiple rows" rule).
        self._environment_stack: list[str | None] = []

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def advance(self) -> Token | None:
        tok = self.peek()
        if tok is not None:
            self.pos += 1
        return tok

    def at_text(self, *texts: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.text in texts

    # ---- grammar, lowest to highest precedence ----

    def parse_row(self) -> dict[str, object]:
        """Top level: a two-dimensional row/cell layout when separators occur.

        `\\\\` starts a new logical row while `&` starts a new cell in the
        current row.  Keeping those two axes distinct is important for cases,
        systems, aligned equations, and matrices: speech and braille must number
        actual equations/rows, not each alignment cell as if it were a row.

        A LaTeX row break is two literal backslash characters in a row. Neither
        one matches the `\\command` token pattern on its own (it requires a
        following letter), so each tokenizes as its own single-backslash `char`
        token; a row break is exactly two of those in a row.

        The canonical shape is `AlignedRows.rows[] -> AlignedRow.cells[]`.
        Consumers still accept the older flat `AlignedRows.children[]` shape so
        already-published datapacks remain readable, but all new parses preserve
        the real two-dimensional association.
        """
        rows: list[list[dict[str, object]]] = [[self.parse_comma_list()]]
        while self._at_row_break() or self.at_text("&"):
            if self._at_row_break():
                self.advance()
                self.advance()
                rows.append([self.parse_comma_list()])
            else:
                self.advance()
                rows[-1].append(self.parse_comma_list())
        environment = self._environment_stack[-1] if self._environment_stack else None
        self._consume_matching_environment_end()
        if len(rows) == 1 and len(rows[0]) == 1:
            return rows[0][0]
        node: dict[str, object] = {
            "type": "AlignedRows",
            "rows": [
                {"type": "AlignedRow", "cells": cells}
                for cells in rows
            ],
        }
        if environment is not None:
            node["environment"] = environment
        return node

    def parse_comma_list(self) -> dict[str, object]:
        """A bare "," between complete relation-level expressions (set
        notation "2,4,6,...", an interval "0,1", or a list of independent
        relations like "sinθ=y/r,cosθ=x/r,...") is a list separator --
        distinct from `Row` (implicit multiplication, no separator between
        children) and from `AlignedRows` (real `\\\\`/`&` row/cell layout,
        which gets the numbered-row braille/TTS treatment). Binds looser than
        a single relation but tighter than a row/cell split -- called once
        per "row" inside `parse_row()`'s loop, so a comma never crosses a
        `\\\\`/`&` boundary. A bare "," previously matched no grammar rule at
        all and always fell through as `Unknown`/unconsumed, so this is
        additive with no regression risk for formulas that don't use one.
        """
        items = [self.parse_relation_sequence()]
        while self.peek() is not None and self.peek().kind == "char" and self.peek().text == ",":
            self.advance()
            items.append(self.parse_relation_sequence())
        if len(items) == 1:
            return items[0]
        return {"type": "List", "children": items}

    def _consume_matching_environment_end(self) -> None:
        """The row-break loop above stops as soon as no more `\\\\`/`&` follow
        -- for `\\begin{cases}a\\\\b\\end{cases}` that's right before `\\end`,
        which nothing else ever advances past (the `\\begin`/`\\end` handling
        in `parse_command` only runs when `\\end` is reached *through* a
        `parse_primary` call, which this loop's natural exit bypasses). Without
        this, `\\end{...}` always leaks into `unconsumed_tokens`, which would
        make every environment-wrapped formula look PARTIAL to
        `classify_ast_status` even though it parsed cleanly."""
        if not self._environment_stack:
            return
        if self.peek() is not None and self.peek().kind == "command" and self.peek().text == "end":
            self.advance()
            self._read_environment_name()
            self._environment_stack.pop()

    def _at_row_break(self) -> bool:
        tok = self.peek()
        if tok is None or tok.kind != "char" or tok.text != "\\":
            return False
        nxt = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
        return nxt is not None and nxt.kind == "char" and nxt.text == "\\"

    def _match_relation_operator(self) -> str | None:
        """Match a relation operator, including one wrapped alone in braces.

        Formula OCR output has repeatedly wrapped a bare relation operator in
        its own brace group (e.g. "x{=}y" instead of "x=y", seen both from
        PP-FormulaNet and PaddleOCR-VL output) -- almost certainly a spacing
        artifact from the source model, not meaningful grouping. Treating
        "{=}" as equivalent to "=" recovers the relation instead of losing the
        entire right-hand side to "unconsumed".
        """
        tok = self.peek()
        if tok is None:
            return None
        candidate = "\\" + tok.text if tok.kind == "command" else tok.text
        if candidate in RELATION_TOKENS:
            self.advance()
            return RELATION_DISPLAY.get(candidate, candidate)
        if tok.kind == "char" and tok.text == "{":
            inner = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            closer = self.tokens[self.pos + 2] if self.pos + 2 < len(self.tokens) else None
            if inner is not None and closer is not None and closer.kind == "char" and closer.text == "}":
                inner_candidate = "\\" + inner.text if inner.kind == "command" else inner.text
                if inner_candidate in RELATION_TOKENS:
                    self.advance()
                    self.advance()
                    self.advance()
                    return RELATION_DISPLAY.get(inner_candidate, inner_candidate)
        return None

    def _consume_closing_delimiter(self, expected: str) -> bool:
        """Match a closing delimiter, tolerating a preceding `\\right` marker
        (from `\\left(...\\right)`) and LaTeX's "invisible delimiter" `.` (from
        `\\right.`, used when a `\\left\\{` case block has no visible close).
        The `.` fallback only applies right after an actual `\\right`, so it
        cannot mask a genuinely missing `}` in an unrelated group.
        """
        had_right = False
        if self.peek() is not None and self.peek().kind == "command" and self.peek().text == "right":
            self.advance()
            had_right = True
        if self.at_text(expected):
            self.advance()
            return True
        if had_right and self.at_text("."):
            self.advance()
            return True
        return False

    def _consume_escaped_closing_brace(self) -> bool:
        """Match "\\}" (an escaped closing curly brace, two tokens: a lone
        backslash `char` then a `}` `char`), tolerating a preceding `\\right`
        the same way `_consume_closing_delimiter` does for `)`/`|`/`]`."""
        had_right = False
        if self.peek() is not None and self.peek().kind == "command" and self.peek().text == "right":
            self.advance()
            had_right = True
        nxt = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
        if (self.peek() is not None and self.peek().kind == "char" and self.peek().text == "\\"
                and nxt is not None and nxt.kind == "char" and nxt.text == "}"):
            self.advance()
            self.advance()
            return True
        if had_right and self.at_text("."):
            self.advance()
            return True
        return False

    def parse_relation_sequence(self) -> dict[str, object]:
        # Aligned equations commonly begin a continuation row with `=&...`.
        # Here the leading relation sign is real content in the first alignment
        # cell, not a malformed binary relation with a missing left operand.
        leading_operator = self._match_relation_operator()
        if leading_operator is not None:
            if self.at_text("&") or self._at_row_break():
                return {"type": "Operator", "value": leading_operator}
            left: dict[str, object] = {"type": "Operator", "value": leading_operator}
        else:
            left = self.parse_additive()
        while True:
            operator = self._match_relation_operator()
            if operator is None:
                break
            if self.at_text("&") or self._at_row_break():
                # `lhs=&rhs`: preserve the trailing relation sign in the left
                # alignment cell and leave `&` for parse_row() to split.
                if left.get("type") == "Row" and isinstance(left.get("children"), list):
                    left = {**left, "children": [*left["children"], {"type": "Operator", "value": operator}]}
                else:
                    left = {
                        "type": "Row",
                        "children": [left, {"type": "Operator", "value": operator}],
                    }
                break
            right = self.parse_additive()
            left = {"type": "Relation", "operator": operator, "left": left, "right": right}
        return left

    def parse_additive(self) -> dict[str, object]:
        # Bug fix: this used to build a binary tree of
        # {"type": "Operator", "operator": op, "left": ..., "right": ...} for
        # chained +/-, which was never the shape math_translator.py/
        # math_rules.py's "Operator" handler expects (a leaf node with a
        # "value" field, used inside a Row's children -- see e.g.
        # parse_multiplicative's Row of factors). That meant every chained
        # addition/subtraction with 2+ terms (very common: "a+b-c",
        # "m+n", "-a^2+6a-4") produced a node braille raised
        # NotImplementedError on (via the empty `node.get("value", "")`
        # lookup) and that TTS silently dropped (`OPERATOR_SPEECH.get("",
        # "")` -> "" -> contributes nothing), a real silent-content-loss bug.
        # Found via real OCR fixtures p008/p030, 2026-08-18.
        children = [self.parse_multiplicative()]
        while self.peek() is not None and self.peek().kind == "char" and self.peek().text in {"+", "-"}:
            operator = self.advance().text
            children.append({"type": "Operator", "value": operator})
            children.append(self.parse_multiplicative())
        if len(children) == 1:
            return children[0]
        return {"type": "Row", "children": children}

    def parse_multiplicative(self) -> dict[str, object]:
        factors = [self.parse_slash_fraction()]
        while True:
            tok = self.peek()
            if tok is None:
                break
            candidate = "\\" + tok.text if tok.kind == "command" else tok.text
            if candidate in MULT_TOKENS:
                self.advance()
                factors.append(self.parse_slash_fraction())
                continue
            if self._starts_implicit_factor(tok):
                factors.append(self.parse_slash_fraction())
                continue
            break
        if len(factors) == 1:
            return factors[0]
        return {"type": "Row", "children": factors}

    def parse_slash_fraction(self) -> dict[str, object]:
        """A bare "/" directly between two atoms (e.g. "2/3", "a/b") is a
        slash-notation fraction, distinct from `\\frac{}{}`'s stacked form --
        수학 점자 규정 제7항 2. gives it its own braille indicator, different
        from the stacked form's bar, so the AST records which notation was
        used (`notation: "slash"`; omitted entirely for the default stacked
        `\\frac` form, so existing consumers that don't check it are
        unaffected). Binds at the same tight precedence as a single
        multiplicative factor, same as implicit multiplication -- not as
        loosely as `\\div`/`*`. A bare "/" previously matched no grammar rule
        at all and always fell through as an `Unknown` token, so this is a
        pure addition with no regression risk for existing formulas.
        """
        numerator = self.parse_unary()
        if self.peek() is not None and self.peek().kind == "char" and self.peek().text == "/":
            self.advance()
            denominator = self.parse_unary()
            return {"type": "Fraction", "numerator": numerator, "denominator": denominator, "notation": "slash"}
        return numerator

    def _starts_implicit_factor(self, tok: Token) -> bool:
        # Juxtaposition (e.g. "2x", "ab") means implicit multiplication. Stop at
        # anything that closes the current group or starts a new relation/term.
        if tok.kind in {"number", "letter"}:
            return True
        if tok.kind == "command" and (tok.text in FUNCTION_NAMES or tok.text == "frac" or tok.text == "sqrt" or tok.text in GREEK_AND_CONSTANTS or tok.text in DECORATION_COMMANDS):
            return True
        if tok.kind == "char" and tok.text in {"(", "|", "["}:
            return True
        return False

    def parse_unary(self) -> dict[str, object]:
        if self.peek() is not None and self.peek().kind == "char" and self.peek().text == "-":
            self.advance()
            return {"type": "UnaryMinus", "body": self.parse_unary()}
        return self.parse_postfix()

    def parse_postfix(self) -> dict[str, object]:
        node = self.parse_primary()
        while True:
            tok = self.peek()
            if tok is None:
                break
            if tok.kind == "char" and tok.text == "^":
                self.advance()
                exponent = self.parse_group_or_atom()
                node = {"type": "Power", "base": node, "exponent": exponent}
                continue
            if tok.kind == "char" and tok.text == "_":
                self.advance()
                subscript = self.parse_group_or_atom()
                if self.peek() is not None and self.peek().kind == "char" and self.peek().text == "^":
                    self.advance()
                    exponent = self.parse_group_or_atom()
                    node = {"type": "Subsuperscript", "base": node, "subscript": subscript, "exponent": exponent}
                else:
                    node = {"type": "Subscript", "base": node, "subscript": subscript}
                continue
            if tok.kind == "char" and tok.text == "(" and node.get("type") in {"Identifier"} and is_function_like(node):
                argument = self.parse_group_or_atom(force_paren=True)
                node = {"type": "FunctionApplication", "name": node.get("value"), "argument": argument}
                continue
            break
        return node

    def parse_primary(self) -> dict[str, object]:
        tok = self.peek()
        if tok is None:
            self.issues.append({
                "code": "AST_UNEXPECTED_END",
                "severity": "error",
                "message": "Expected an expression but reached the end of input.",
            })
            return unknown_node("")

        if tok.kind == "number":
            self.advance()
            return {"type": "Number", "value": tok.text}

        if tok.kind == "letter":
            self.advance()
            return {"type": "Identifier", "value": tok.text}

        if tok.kind == "command":
            return self.parse_command()

        if tok.kind == "char" and tok.text == "(":
            self.advance()
            body = self.parse_comma_list()
            if not self._consume_closing_delimiter(")"):
                self.issues.append({
                    "code": "AST_UNMATCHED_PAREN",
                    "severity": "error",
                    "message": "Missing closing ')' for a parenthesized group.",
                })
            return {"type": "Parenthesized", "body": body, "delimiter": "("}

        if tok.kind == "char" and tok.text == "|":
            self.advance()
            body = self.parse_comma_list()
            if not self._consume_closing_delimiter("|"):
                self.issues.append({
                    "code": "AST_UNMATCHED_PAREN",
                    "severity": "error",
                    "message": "Missing closing '|' for an absolute-value group.",
                })
            return {"type": "Parenthesized", "body": body, "delimiter": "|"}

        if tok.kind == "char" and tok.text == "[":
            # A bare "[" here is a real 대괄호 (e.g. an interval "[0,1]"), not
            # \sqrt's index bracket -- that one is consumed separately, right
            # after \sqrt, before control ever reaches this general dispatch.
            self.advance()
            body = self.parse_comma_list()
            if not self._consume_closing_delimiter("]"):
                self.issues.append({
                    "code": "AST_UNMATCHED_BRACKET",
                    "severity": "error",
                    "message": "Missing closing ']' for a bracketed group.",
                })
            return {"type": "Parenthesized", "body": body, "delimiter": "["}

        if tok.kind == "char" and tok.text == "{":
            return self.parse_brace_group()

        if tok.kind == "char" and tok.text == "\\":
            # A lone backslash not forming a \command is an escaped-delimiter
            # artifact. "\{"/"\}" specifically (e.g. set notation
            # "\{2,4,6,...\}", or a \cases block opened as \left\{...\right.)
            # are real 중괄호 content delimiters -- everything else here (a
            # "\}"/"\." not opened by a matching "\{", stray \right markers)
            # is a spacing/closing artifact with nothing to attach to, so it
            # is skipped past rather than treated as an empty group.
            nxt = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            if nxt is not None and nxt.kind == "char" and nxt.text == "{":
                self.advance()  # consume the backslash
                self.advance()  # consume '{'
                # \begin{cases}...\end{cases} is the single most common thing
                # to find directly inside \left\{...\right. (연립식/피스와이즈),
                # and that needs row/cell splitting -- parse_row() (not
                # parse_relation_sequence()) is what already does that.
                body = self.parse_row()
                if not self._consume_escaped_closing_brace():
                    self.issues.append({
                        "code": "AST_UNMATCHED_BRACE",
                        "severity": "error",
                        "message": "Missing closing '\\}' for an escaped brace group.",
                    })
                return {"type": "Parenthesized", "body": body, "delimiter": "{"}
            self.advance()
            if self.peek() is None:
                return unknown_node("")
            return self.parse_primary()

        if tok.kind == "char" and tok.text == "&":
            # Alignment tab inside \begin{aligned}/\begin{array} -- a layout hint,
            # not content. Skip it and continue parsing the row.
            self.advance()
            if self.peek() is None:
                return unknown_node("")
            return self.parse_primary()

        # Unrecognized token: preserve it as Unknown and advance so the parser
        # keeps making progress on the rest of the formula.
        self.advance()
        self.issues.append({
            "code": "AST_UNKNOWN_TOKEN",
            "severity": "warning",
            "message": f"Unrecognized token {tok.text!r} preserved as an Unknown node.",
        })
        return unknown_node(tok.text)

    def parse_command(self) -> dict[str, object]:
        tok = self.advance()
        name = tok.text

        if name in SKIP_COMMANDS:
            if self.peek() is not None:
                return self.parse_primary()
            return unknown_node("")

        if name in {"begin", "end"}:
            # \begin{aligned}, \end{array}, etc: the first brace group is an
            # environment name, not content, and tabular environments like
            # \begin{array}{ll} follow it with a column-spec brace group that
            # is also not content. Read the name (see `_read_environment_name`)
            # and push/pop it on `self._environment_stack` so `parse_row()`
            # can tag the resulting `AlignedRows` with it.
            environment_name = self._read_environment_name()
            if self.at_text("{"):
                self.parse_brace_group()
            if name == "begin":
                self._environment_stack.append(environment_name)
            elif self._environment_stack:
                self._environment_stack.pop()
            if self.peek() is not None:
                return self.parse_primary()
            return unknown_node("")

        if name == "frac":
            numerator = self.parse_group_or_atom()
            denominator = self.parse_group_or_atom()
            return {"type": "Fraction", "numerator": numerator, "denominator": denominator}

        if name == "sqrt":
            index = None
            if self.at_text("["):
                self.advance()
                index = self.parse_relation_sequence()
                if not self._consume_closing_delimiter("]"):
                    self.issues.append({
                        "code": "AST_UNMATCHED_BRACKET",
                        "severity": "error",
                        "message": "Missing closing ']' for a \\sqrt index.",
                    })
            radicand = self.parse_group_or_atom()
            node: dict[str, object] = {"type": "Radical", "radicand": radicand}
            if index is not None:
                node["index"] = index
            return node

        if name in FUNCTION_NAMES:
            # "\sin^{2}x" means (sin x)^2: the exponent binds to the function
            # symbol itself and is applied *after* the real argument is parsed,
            # not consumed as if it were the argument.
            power_exponent = None
            if self.at_text("^"):
                self.advance()
                power_exponent = self.parse_group_or_atom()
            if self.at_text("("):
                argument = self.parse_group_or_atom(force_paren=True)
            else:
                argument = self.parse_unary()
            application: dict[str, object] = {"type": "FunctionApplication", "name": name, "argument": argument}
            if power_exponent is not None:
                return {"type": "Power", "base": application, "exponent": power_exponent}
            return application

        if name in DECORATION_COMMANDS:
            body = self.parse_group_or_atom()
            return {**body, "decoration": name}

        if name in GREEK_AND_CONSTANTS:
            return {"type": "Identifier", "value": GREEK_AND_CONSTANTS[name]}

        if name == "textcircled":
            # OCR-noise marker wrapper, e.g. "\textcircled{1}" -- not real math.
            inner = self.parse_group_or_atom()
            return {"type": "Unknown", "value": f"\\textcircled{{{node_display(inner)}}}"}

        # Unrecognized command: preserve as Unknown, do not consume a following
        # brace group as its argument (we do not know its arity).
        self.issues.append({
            "code": "AST_UNKNOWN_COMMAND",
            "severity": "warning",
            "message": f"Unrecognized command \\{name} preserved as an Unknown node.",
        })
        return unknown_node("\\" + name)

    def parse_group_or_atom(self, force_paren: bool = False) -> dict[str, object]:
        if self.at_text("{"):
            return self.parse_brace_group()
        if force_paren and self.at_text("("):
            return self.parse_primary()
        return self.parse_postfix() if not force_paren else self.parse_primary()

    def _read_environment_name(self) -> str | None:
        """`\\begin{name}`/`\\end{name}`'s brace group is always a bare word
        like "cases"/"array"/"aligned"/"matrix", never a real expression --
        read the raw token text directly rather than running the expression
        grammar on it (which would turn e.g. "cases" into a `Row` of five
        implicitly-multiplied `Identifier` letters)."""
        if not self.at_text("{"):
            return None
        self.advance()  # consume '{'
        chars: list[str] = []
        while self.peek() is not None and not self.at_text("}"):
            chars.append(self.advance().text)
        if self.at_text("}"):
            self.advance()
        return "".join(chars) or None

    def parse_brace_group(self) -> dict[str, object]:
        self.advance()  # consume '{'
        if self.at_text("}"):
            self.advance()
            return {"type": "Row", "children": []}
        body = self.parse_row()
        if self._consume_closing_delimiter("}"):
            pass
        else:
            self.issues.append({
                "code": "AST_UNMATCHED_BRACE",
                "severity": "error",
                "message": "Missing closing '}' for a group.",
            })
        return body


def is_function_like(node: dict[str, object]) -> bool:
    value = node.get("value")
    return isinstance(value, str) and value in {"f", "g", "h"}


def unknown_node(raw: str) -> dict[str, object]:
    return {"type": "Unknown", "value": raw}


def node_display(node: dict[str, object]) -> str:
    return str(node.get("value", node.get("type", "")))


def aligned_row_cells(node: object) -> list[list[dict[str, object]]]:
    """Return canonical logical rows while accepting pre-2D datapacks.

    New ASTs store `rows -> cells`.  Published revisions created before the
    two-dimensional AST used one flat `children` list where every child was
    presented as a row.  That legacy interpretation is intentionally retained
    as a read-only fallback; it cannot recover column grouping that was never
    stored, but it prevents an upgrade from making old books unreadable.
    """
    if not isinstance(node, dict) or node.get("type") != "AlignedRows":
        return []
    rows = node.get("rows")
    if isinstance(rows, list):
        result: list[list[dict[str, object]]] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("type") != "AlignedRow":
                continue
            cells = row.get("cells")
            if isinstance(cells, list):
                valid_cells = [cell for cell in cells if isinstance(cell, dict)]
                if valid_cells:
                    result.append(valid_cells)
        if result:
            return result
    children = node.get("children")
    if isinstance(children, list):
        return [[child] for child in children if isinstance(child, dict)]
    return []


# ---- AST validation (기획서 §12.5) ----

REQUIRED_CHILDREN_BY_TYPE = {
    "Fraction": ("numerator", "denominator"),
    "Power": ("base", "exponent"),
    "Subscript": ("base", "subscript"),
    "Subsuperscript": ("base", "subscript", "exponent"),
    "Radical": ("radicand",),
    "Parenthesized": ("body",),
    "UnaryMinus": ("body",),
    "Relation": ("left", "right"),
    "FunctionApplication": ("argument",),
}


def validate_ast(node: object, path: str = "$") -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    if not isinstance(node, dict):
        return issues
    node_type = node.get("type")
    if node_type == "Unknown":
        issues.append({
            "code": "AST_UNKNOWN_NODE",
            "severity": "info",
            "message": f"Unparsed fragment at {path}: {node.get('value', '')!r}.",
        })
    if node_type == "AlignedRows" and not aligned_row_cells(node):
        issues.append({
            "code": "AST_MISSING_ALIGNED_ROWS",
            "severity": "error",
            "message": f"AlignedRows node at {path} has no valid rows.",
        })
    if node_type == "AlignedRow" and not (
        isinstance(node.get("cells"), list)
        and any(isinstance(cell, dict) for cell in node["cells"])
    ):
        issues.append({
            "code": "AST_MISSING_ALIGNED_CELLS",
            "severity": "error",
            "message": f"AlignedRow node at {path} has no valid cells.",
        })
    required = REQUIRED_CHILDREN_BY_TYPE.get(str(node_type), ())
    for field_name in required:
        child = node.get(field_name)
        if not isinstance(child, dict):
            issues.append({
                "code": "AST_MISSING_REQUIRED_CHILD",
                "severity": "error",
                "message": f"{node_type} node at {path} is missing required field '{field_name}'.",
            })
    for key, value in node.items():
        if key in {"children", "rows", "cells"} and isinstance(value, list):
            for i, child in enumerate(value):
                issues.extend(validate_ast(child, f"{path}.{key}[{i}]"))
        elif isinstance(value, dict):
            issues.extend(validate_ast(value, f"{path}.{key}"))
    return issues
