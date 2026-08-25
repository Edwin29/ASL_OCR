"""Axis 3: quality judgment -- reuses document-parser's own
`ImageQualityGate` rather than inventing a parallel quality standard in
book-scanner. That gate is the actual authority on what document-parser
considers reliably processable (min_long_edge, aspect_ratio_range,
blur_score via Laplacian variance) -- see docs/quality-gate.md and
`document_parser.preprocess.quality`. Note this module has no paddle/torch
dependency (just PIL/numpy), so it runs in book-scanner's normal venv, not
the special GPU-only OCR venv document-parser's actual ingest needs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from book_scanner.judge.types import TransmitBlockReason

try:
    from document_parser.preprocess.quality import ImageQualityGate, QUALITY_LOW, QUALITY_REJECTED
except ImportError:
    _document_parser_src = Path(__file__).resolve().parents[4] / "document-parser" / "src"
    if str(_document_parser_src) not in sys.path:
        sys.path.insert(0, str(_document_parser_src))
    from document_parser.preprocess.quality import ImageQualityGate, QUALITY_LOW, QUALITY_REJECTED

_BLOCKING_STATUSES = {QUALITY_LOW, QUALITY_REJECTED}


def judge_quality(corrected_path: Path, gate: ImageQualityGate | None = None) -> TransmitBlockReason | None:
    """Runs document-parser's own quality gate against the corrected image
    file. Returns None if it passes (PASS or PASS_WITH_CORRECTION -- a
    warning-level issue doesn't block, matching document-parser's own
    convention), otherwise LOW_QUALITY."""
    gate = gate or ImageQualityGate()
    report = gate.evaluate_path(Path(corrected_path))
    if report.status in _BLOCKING_STATUSES:
        return TransmitBlockReason.LOW_QUALITY
    return None
