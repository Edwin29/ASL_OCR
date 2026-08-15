from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# PaddleOCR-VL is the project baseline Page IR path: it resolves text/formula/
# table/image separation and reading order directly, instead of approximating
# them from a flat OCR token stream the way the legacy token pipeline
# (tools/baseline_ocr_text_ir.py) does. See
# document_parser.serialization.vl_page_ir for the promotion rationale.
from paddleocr_vl_text_ir import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
