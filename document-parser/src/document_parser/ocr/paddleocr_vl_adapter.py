"""Adapter for PaddleOCR-VL, an end-to-end vision-language document parser.

Unlike `PaddleOcrGeneralAdapter` (flat OCR tokens only), PaddleOCR-VL returns
already-structured page blocks: text (with inline `$...$` LaTeX), standalone
display formulas, tables (as HTML), and images/charts, each with its own bbox and
reading-order index. This addresses the root cause this project spent a full
milestone working around: a plain OCR token stream has no way to know where a
mixed Korean/math line should split, because that information does not exist at
the token level. PaddleOCR-VL is trained to produce that structure directly.

Verified on real EBS pages (p004/p014/p019/p050): lines that the token-boundary
pipeline (document_parser.math.spans + formula_regions) could never split at all
were recognized correctly in one shot. Two concrete failure modes were also
independently reproduced on this project's own data and must be treated as real,
not hypothetical:
  1. Silent content omission (a value or choice dropped with no confidence signal
     -- e.g. "f(8)=" with the "8" simply missing, following a real answer choice
     omission seen in an unrelated book via the vendor's own public demo).
  2. The left-margin problem-number glyph is sometimes captured as its own block
     and sometimes silently concatenated onto the start of the problem text (e.g.
     "1" + "4 이하의..." -> "14 이하의...", verified in the raw JSON, not just the
     markdown export), inconsistently across pages.

Because of (1), this adapter's output must never be trusted at face value; see
`document_parser.serialization.vl_page_ir` for the completeness checks applied
when converting raw blocks into Page IR nodes.

`use_ocr_for_image_block` defaults to True here rather than the library's own
default (False): with it off, every UNSUPPORTED_VISUAL block's `block_content`
came back as an empty string on every page checked -- axis labels, tick marks,
and legends inside graphs were not silently duplicated, they were not captured
at all, contradicting the "ANNOUNCE_AND_PRESERVE_TEXT" handling Page IR claims
for these nodes (기획서 §15.3, "무음 누락 방지"). Verified on p004: with it on,
both graph blocks come back with real embedded text ("y=x^n", "\\sqrt[n]{a}",
"O", axis arrows, etc.) instead of nothing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class PaddleOcrVlAdapter:
    """Wraps `paddleocr.PaddleOCRVL` and returns its raw structured page result."""

    engine_id = "paddleocr-vl"

    def __init__(
        self,
        model_home: Path | None = None,
        device: str = "gpu:0",
        use_ocr_for_image_block: bool = True,
        reader: Any | None = None,
    ) -> None:
        self.model_home = model_home
        self.device = device
        self.use_ocr_for_image_block = use_ocr_for_image_block
        self._reader = reader

    @property
    def engine_version(self) -> str:
        import importlib.metadata

        try:
            return importlib.metadata.version("paddleocr")
        except importlib.metadata.PackageNotFoundError:
            return "not-installed"

    def parse_page(self, image_path: Path) -> dict[str, Any]:
        """Run PaddleOCR-VL on a page image and return its raw result dict.

        The raw dict's `parsing_res_list` (list of block dicts) and `width`/
        `height` are what `document_parser.serialization.vl_page_ir` consumes.
        """
        results = list(self.reader.predict(str(image_path)))
        if not results:
            return {"parsing_res_list": [], "width": 0, "height": 0}
        result = results[0]
        return result.json["res"] if isinstance(result.json, dict) and "res" in result.json else dict(result.json)

    @property
    def reader(self) -> Any:
        if self._reader is None:
            configure_vl_home(self.model_home)
            from paddleocr import PaddleOCRVL

            self._reader = PaddleOCRVL(device=self.device, use_ocr_for_image_block=self.use_ocr_for_image_block)
        return self._reader


def configure_vl_home(model_home: Path | None) -> None:
    if model_home is None:
        return
    model_home.mkdir(parents=True, exist_ok=True)
    cache_home = model_home / ".cache"
    paddle_home = cache_home / "paddle"
    paddle_home.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(model_home)
    os.environ["USERPROFILE"] = str(model_home)
    os.environ["XDG_CACHE_HOME"] = str(cache_home)
    os.environ["PADDLE_HOME"] = str(paddle_home)
