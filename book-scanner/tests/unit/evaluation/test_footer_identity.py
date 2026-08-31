from __future__ import annotations

import cv2
import numpy as np
import pytest

from book_scanner.evaluation.footer_identity import (
    FooterIdentityDecision,
    FooterIdentityMethod,
    build_footer_visual_descriptor,
    classify_match_count,
    compare_visual_descriptors,
    match_spread_observations,
    query_match_indicators,
)


def _side(token: str | None, *, normalized: str | None = None, visual=None):
    return {
        "selected_raw": token,
        "normalized_label": normalized,
        "variant_tokens": [] if token is None else [token],
        "visual": visual or build_footer_visual_descriptor(_image(token or "")),
    }


def _observation(frame: int, left: str | None, right: str | None, *, label="p030"):
    complete = left is not None and right is not None
    return {
        "frame_index": frame,
        "spread_label": label,
        "stages": {
            "preview_1920": {
                "status": "complete" if complete else "partial",
                "semantic_key": {"left": left, "right": right} if complete else None,
                "sides": {
                    "left": _side(left, normalized=left),
                    "right": _side(right, normalized=right),
                }
            }
        },
    }


def _image(text: str) -> np.ndarray:
    image = np.full((120, 240), 240, dtype=np.uint8)
    cv2.putText(image, text, (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 1.8, 20, 3, cv2.LINE_AA)
    return image


def test_visual_descriptor_is_json_safe_and_self_matches():
    descriptor = build_footer_visual_descriptor(_image("309"))
    metrics = compare_visual_descriptors(descriptor, descriptor)
    assert len(descriptor["normalized_patch"]) == 32 * 16
    assert metrics == {"compatible": True, "hamming": 0, "projection_mae": 0.0, "ncc": pytest.approx(1.0)}


def test_missing_tokens_never_match_each_other():
    reference = _observation(1, None, None)
    query = _observation(2, None, None)
    assert not match_spread_observations(reference, query, FooterIdentityMethod.SELECTED_RAW_TOKEN)
    assert not match_spread_observations(reference, query, FooterIdentityMethod.VARIANT_TOKEN_SET)


def test_semantic_control_requires_complete_spread_key():
    reference = _observation(1, "30", "309")
    query = _observation(2, "30", None)
    assert not match_spread_observations(reference, query, FooterIdentityMethod.SEMANTIC_KEY)


def test_both_sides_must_match_for_raw_spread_match():
    reference = _observation(1, "30", "309")
    query = _observation(2, "30", "317")
    assert not match_spread_observations(reference, query, FooterIdentityMethod.SELECTED_RAW_TOKEN)


def test_query_bank_creates_one_indicator_per_query_not_n_squared():
    references = [_observation(1, "30", "309"), _observation(2, "30", "309")]
    queries = [_observation(3, "30", "309"), _observation(4, "30", "309"), _observation(5, "316", "317")]
    indicators = query_match_indicators(references, queries, FooterIdentityMethod.SELECTED_RAW_TOKEN)
    assert indicators == (True, True, False)


def test_reference_and_query_must_be_disjoint():
    observation = _observation(1, "30", "309")
    with pytest.raises(ValueError, match="frame-disjoint"):
        query_match_indicators([observation], [observation], FooterIdentityMethod.SELECTED_RAW_TOKEN)


@pytest.mark.parametrize(
    ("matches", "expected"),
    [
        (0, FooterIdentityDecision.DIFFERENT),
        (1, FooterIdentityDecision.UNKNOWN),
        (2, FooterIdentityDecision.SAME),
    ],
)
def test_three_state_thresholds(matches, expected):
    assert classify_match_count(3, matches, 0, 2) is expected


def test_invalid_thresholds_are_rejected():
    with pytest.raises(ValueError):
        classify_match_count(3, 1, 2, 2)
