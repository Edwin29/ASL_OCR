from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from paddleocr_text_ir import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
