from __future__ import annotations

import sys
from pathlib import Path


TOOLS_ROOT = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from evaluate_phase_a_pilot import EXTRACTIONS, PILOT_SIDES, evaluate  # noqa: E402


def _summary(tmp_path: Path, *, drop: float = 0.05):
    results = []
    comparisons = []
    for capture, side in PILOT_SIDES:
        for extraction in EXTRACTIONS:
            identifier = f"{capture}_{side}_{extraction}_none_none"
            record_path = tmp_path / f"{identifier}.json"
            record_path.write_text(
                '{"evaluation":{"normalized_content_text":'
                '"내가가진소장품도전자상거래상품이될수있다인터넷쇼핑,홈뱅킹'
                '공공기관이나정부팩스나전자우편정답해설"}}',
                encoding="utf-8",
            )
            results.append({
                "artifact_id": identifier, "status": "COMPLETE", "schema_valid": True,
                "record_path": str(record_path),
            })
            comparisons.append({
                "capture": capture, "side": side, "extraction": extraction,
                "comparison": {
                    "character_count_drop_fraction": drop if extraction == "seam_conservative" else 0.0,
                    "node_type_count_delta": {"TABLE": 0, "FORMULA": 0},
                    "node_sequence_similarity": 0.95,
                },
            })
    return {"results": results, "comparisons": comparisons}


def test_pilot_gate_allows_expansion_without_accuracy_claim(tmp_path: Path):
    result = evaluate(_summary(tmp_path))
    assert result["verdict"] == "PILOT_NO_CLEAR_REGRESSION"
    assert result["accuracy_claim_allowed"] is False
    assert result["manual_golden_status"] == "MANUAL_GOLDEN_NOT_VERIFIED"


def test_pilot_gate_rejects_over_twenty_percent_character_drop(tmp_path: Path):
    result = evaluate(_summary(tmp_path, drop=0.21))
    assert result["verdict"] == "PILOT_OCR_REGRESSION"
    assert result["criteria"]["character_drop_at_most_20_percent"] is False
