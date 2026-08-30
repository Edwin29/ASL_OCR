"""Apply the predeclared Phase A pilot gate to an extraction OCR summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PILOT_SIDES = (
    ("20260826_174958", "right"),
    ("20260826_175109", "left"),
    ("20260826_175109", "right"),
)
EXTRACTIONS = ("oracle", "overlap", "seam_confirmed", "seam_conservative")


def evaluate(summary: dict[str, object]) -> dict[str, object]:
    results = {str(item.get("artifact_id")): item for item in summary.get("results", [])}
    comparisons = {
        (str(item.get("capture")), str(item.get("side")), str(item.get("extraction"))): item["comparison"]
        for item in summary.get("comparisons", [])
    }
    expected_ids = {
        f"{capture}_{side}_{extraction}_none_none"
        for capture, side in PILOT_SIDES for extraction in EXTRACTIONS
    }
    missing = sorted(expected_ids - set(results))
    complete = not missing and all(results[item].get("status") == "COMPLETE" for item in expected_ids)
    schema_valid = complete and all(bool(results[item].get("schema_valid")) for item in expected_ids)

    conservative = [comparisons.get((*key, "seam_conservative")) for key in PILOT_SIDES]
    overlap = [comparisons.get((*key, "overlap")) for key in PILOT_SIDES]
    comparison_complete = all(isinstance(item, dict) for item in (*conservative, *overlap))
    char_drops = [item.get("character_count_drop_fraction") for item in conservative if isinstance(item, dict)]
    char_gate = comparison_complete and all(value is not None and float(value) <= 0.20 for value in char_drops)

    structure_checks: list[dict[str, object]] = []
    for key, seam_item, overlap_item in zip(PILOT_SIDES, conservative, overlap):
        passed = True
        deltas: dict[str, dict[str, int]] = {}
        if not isinstance(seam_item, dict) or not isinstance(overlap_item, dict):
            passed = False
        else:
            for node_type in ("TABLE", "FORMULA"):
                seam_delta = int(dict(seam_item.get("node_type_count_delta", {})).get(node_type, 0))
                overlap_delta = int(dict(overlap_item.get("node_type_count_delta", {})).get(node_type, 0))
                deltas[node_type] = {"seam_conservative": seam_delta, "overlap": overlap_delta}
                if seam_delta < overlap_delta:
                    passed = False
        structure_checks.append({"capture": key[0], "side": key[1], "passed": passed, "deltas": deltas})
    structure_gate = comparison_complete and all(item["passed"] for item in structure_checks)

    sequence_checks = []
    markedly_lower_count = 0
    for key, seam_item, overlap_item in zip(PILOT_SIDES, conservative, overlap):
        seam_value = float(seam_item.get("node_sequence_similarity", 0.0)) if isinstance(seam_item, dict) else 0.0
        overlap_value = float(overlap_item.get("node_sequence_similarity", 0.0)) if isinstance(overlap_item, dict) else 0.0
        markedly_lower = seam_value + 0.10 < overlap_value
        markedly_lower_count += int(markedly_lower)
        sequence_checks.append({
            "capture": key[0], "side": key[1], "seam_conservative": seam_value,
            "overlap": overlap_value, "lower_by_more_than_0_10": markedly_lower,
        })
    # "Repeatedly" requires at least two of the three independent pilot sides.
    sequence_gate = comparison_complete and markedly_lower_count < 2

    key_id = "20260826_174958_right_seam_conservative_none_none"
    record_path = Path(str(results.get(key_id, {}).get("record_path", "")))
    normalized = ""
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        normalized = str(record.get("evaluation", {}).get("normalized_content_text", ""))
    required_fragments = (
        "내가가진소장품도전자상거래상품이될수있다",
        "인터넷쇼핑,홈뱅킹",
        "공공기관이나정부",
        "팩스나전자우편",
        "정답",
        "해설",
    )
    key_blocks = {fragment: fragment in normalized for fragment in required_fragments}
    key_block_gate = bool(normalized) and all(key_blocks.values())

    criteria = {
        "expected_12_complete": complete,
        "schema_valid_12_of_12": schema_valid,
        "character_drop_at_most_20_percent": char_gate,
        "no_additional_table_formula_omission_vs_overlap": structure_gate,
        "node_sequence_not_repeatedly_markedly_lower": sequence_gate,
        "174958_right_key_blocks_present": key_block_gate,
        "single_adapter_batch_contract": True,
    }
    if not complete or not schema_valid:
        verdict = "PILOT_TECHNICAL_FAILURE"
    elif all(criteria.values()):
        verdict = "PILOT_NO_CLEAR_REGRESSION"
    elif not char_gate or not structure_gate or not key_block_gate:
        verdict = "PILOT_OCR_REGRESSION"
    else:
        verdict = "PILOT_INCONCLUSIVE"
    return {
        "schema_version": 1,
        "verdict": verdict,
        "criteria": criteria,
        "missing_artifact_ids": missing,
        "character_drop_fractions": char_drops,
        "structure_checks": structure_checks,
        "sequence_checks": sequence_checks,
        "key_block_presence": key_blocks,
        "manual_golden_status": "MANUAL_GOLDEN_NOT_VERIFIED",
        "accuracy_claim_allowed": False,
        "note": (
            "Block presence does not verify exact glyph transcription. The 174958 right candidate differs "
            "from oracle OCR in some item/choice glyphs and remains manually unverified."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    decision = evaluate(json.loads(args.summary.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": decision["verdict"], "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if decision["verdict"] == "PILOT_NO_CLEAR_REGRESSION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
