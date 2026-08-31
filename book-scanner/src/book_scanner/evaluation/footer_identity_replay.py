"""Bank construction and threshold accounting for V3-A.4 offline replay."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .footer_identity import FooterIdentityDecision, classify_match_count


def cadence_frame_step(fps: float, cadence_ms: int) -> int:
    if fps <= 0.0:
        raise ValueError("fps must be positive")
    if isinstance(cadence_ms, bool) or not isinstance(cadence_ms, int) or cadence_ms <= 0:
        raise ValueError("cadence_ms must be a positive integer")
    return max(1, round(fps * cadence_ms / 1000.0))


def sample_block(
    records: Sequence[Mapping[str, Any]],
    block: Mapping[str, Any],
    *,
    fps: float,
    cadence_ms: int,
) -> tuple[Mapping[str, Any], ...]:
    """Sample a frozen block on a fixed time grid, without backfilling rejects."""

    start = int(block["start_frame_inclusive"])
    end = int(block["end_frame_inclusive"])
    if end < start:
        raise ValueError("block end must not precede start")
    indexed = {int(item["frame_index"]): item for item in records}
    step = cadence_frame_step(fps, cadence_ms)
    selected = []
    for frame_index in range(start, end + 1, step):
        record = indexed.get(frame_index)
        if record is not None and bool(record.get("eligible")):
            selected.append(record)
    return tuple(selected)


def threshold_grid(n: int) -> tuple[tuple[int, int], ...]:
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise ValueError("n must be a positive integer")
    return tuple((different, same) for different in range(n) for same in range(different + 1, n + 1))


def score_threshold(
    relations: Sequence[Mapping[str, Any]],
    *,
    n: int,
    k_different: int,
    k_same: int,
) -> dict[str, Any]:
    """Score relation-level decisions; observations, not N² pairs, are trials."""

    decisions = []
    false_duplicate = 0
    false_different = 0
    unknown = 0
    for relation in relations:
        expected = str(relation["expected"])
        matches = int(relation["match_count"])
        decision = classify_match_count(n, matches, k_different, k_same)
        indicators = [bool(item) for item in relation.get("indicators", ())]
        decisions.append(
            {
                "relation_id": relation["relation_id"],
                "expected": expected,
                "decision": decision.value,
                "first_decision_sample": _first_decision_sample(indicators, n, k_different, k_same),
            }
        )
        if decision is FooterIdentityDecision.UNKNOWN:
            unknown += 1
        elif expected == "different" and decision is FooterIdentityDecision.SAME:
            false_duplicate += 1
        elif expected == "same" and decision is FooterIdentityDecision.DIFFERENT:
            false_different += 1
    return {
        "k_different": k_different,
        "k_same": k_same,
        "false_duplicate_count": false_duplicate,
        "false_different_count": false_different,
        "unknown_count": unknown,
        "decisions": decisions,
    }


def _first_decision_sample(indicators: Sequence[bool], n: int, k_different: int, k_same: int) -> int:
    if len(indicators) != n:
        return n
    matches = 0
    for index, indicator in enumerate(indicators, start=1):
        matches += int(indicator)
        remaining = n - index
        if matches >= k_same or matches + remaining <= k_different:
            return index
    return n
