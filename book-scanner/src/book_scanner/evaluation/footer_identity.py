"""Pure, offline opaque-footer identity primitives for V3-A.4 experiments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

import cv2
import numpy as np


class FooterIdentityMethod(str, Enum):
    SEMANTIC_KEY = "semantic_key"
    SELECTED_RAW_TOKEN = "selected_raw_token"
    VARIANT_TOKEN_SET = "variant_token_set"
    VISUAL_FINGERPRINT = "visual_fingerprint"
    HYBRID = "hybrid"


class FooterIdentityDecision(str, Enum):
    SAME = "same"
    DIFFERENT = "different"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FooterVisualPolicy:
    hamming_max: int = 8
    hamming_relaxed_max: int = 18
    projection_mae_max: float = 0.03
    projection_relaxed_mae_max: float = 0.06
    ncc_min: float = 0.90
    ncc_relaxed_min: float = 0.78
    full_page_different_hamming_min: int = 20
    full_page_different_projection_min: float = 0.06

    def __post_init__(self) -> None:
        if not 0 <= self.hamming_max <= self.hamming_relaxed_max <= 64:
            raise ValueError("footer hamming thresholds must be ordered in [0, 64]")
        if not 0.0 <= self.projection_mae_max <= self.projection_relaxed_mae_max <= 1.0:
            raise ValueError("footer projection thresholds must be ordered in [0, 1]")
        if not -1.0 <= self.ncc_relaxed_min <= self.ncc_min <= 1.0:
            raise ValueError("footer NCC thresholds must be ordered in [-1, 1]")
        if not 0 <= self.full_page_different_hamming_min <= 64:
            raise ValueError("full-page hamming threshold must be in [0, 64]")
        if not 0.0 <= self.full_page_different_projection_min <= 1.0:
            raise ValueError("full-page projection threshold must be in [0, 1]")


def build_footer_visual_descriptor(image: np.ndarray, *, projection_bins: int = 16) -> dict[str, Any]:
    """Create a small JSON-safe descriptor without interpreting page text."""

    if not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("footer image must be a non-empty ndarray")
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 2:
        gray = image
    else:
        raise ValueError("footer image must be grayscale or BGR")
    normalized = cv2.resize(gray, (128, 64), interpolation=cv2.INTER_AREA)
    normalized = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 4)).apply(normalized)
    phash_image = cv2.resize(normalized, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low = cv2.dct(phash_image)[:8, :8]
    threshold = float(np.median(low.reshape(-1)[1:]))
    value = 0
    for bit in (low >= threshold).reshape(-1):
        value = (value << 1) | int(bool(bit))
    _threshold, ink = cv2.threshold(normalized, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    horizontal = _projection(ink, projection_bins, axis=1)
    vertical = _projection(ink, projection_bins, axis=0)
    patch = cv2.resize(normalized, (32, 16), interpolation=cv2.INTER_AREA)
    patch = cv2.normalize(patch, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return {
        "algorithm_version": "opaque-footer-visual-v1",
        "perceptual_hash": f"{value:016x}",
        "horizontal_projection": list(horizontal),
        "vertical_projection": list(vertical),
        "patch_width": 32,
        "patch_height": 16,
        "normalized_patch": patch.reshape(-1).tolist(),
    }


def compare_visual_descriptors(candidate: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, Any]:
    if candidate.get("algorithm_version") != reference.get("algorithm_version"):
        return {"compatible": False, "hamming": 64, "projection_mae": 1.0, "ncc": -1.0}
    try:
        hamming = (int(str(candidate["perceptual_hash"]), 16) ^ int(str(reference["perceptual_hash"]), 16)).bit_count()
        projection_a = tuple(int(item) for item in candidate["horizontal_projection"]) + tuple(
            int(item) for item in candidate["vertical_projection"]
        )
        projection_b = tuple(int(item) for item in reference["horizontal_projection"]) + tuple(
            int(item) for item in reference["vertical_projection"]
        )
        if not projection_a or len(projection_a) != len(projection_b):
            raise ValueError("projection lengths differ")
        projection_mae = sum(abs(a - b) for a, b in zip(projection_a, projection_b)) / (255.0 * len(projection_a))
        patch_a = np.asarray(candidate["normalized_patch"], dtype=np.float32)
        patch_b = np.asarray(reference["normalized_patch"], dtype=np.float32)
        if patch_a.size == 0 or patch_a.size != patch_b.size:
            raise ValueError("patch lengths differ")
        patch_a -= float(np.mean(patch_a))
        patch_b -= float(np.mean(patch_b))
        denominator = float(np.linalg.norm(patch_a) * np.linalg.norm(patch_b))
        ncc = float(np.dot(patch_a, patch_b) / denominator) if denominator > 1e-9 else 0.0
    except (KeyError, TypeError, ValueError):
        return {"compatible": False, "hamming": 64, "projection_mae": 1.0, "ncc": -1.0}
    return {
        "compatible": True,
        "hamming": hamming,
        "projection_mae": projection_mae,
        "ncc": max(-1.0, min(1.0, ncc)),
    }


def match_spread_observations(
    reference: Mapping[str, Any],
    query: Mapping[str, Any],
    method: FooterIdentityMethod,
    policy: FooterVisualPolicy = FooterVisualPolicy(),
    *,
    stage_name: str = "preview_1920",
) -> bool:
    """Return one frame-pair match; missing evidence never matches itself."""

    if int(reference.get("frame_index", -1)) == int(query.get("frame_index", -1)):
        raise ValueError("reference and query must not share a frame")
    stages_reference = reference.get("stages")
    stages_query = query.get("stages")
    if not isinstance(stages_reference, Mapping) or not isinstance(stages_query, Mapping):
        return False
    reference_stage = stages_reference.get(stage_name)
    query_stage = stages_query.get(stage_name)
    if method is FooterIdentityMethod.SEMANTIC_KEY:
        return _semantic_key_match(reference_stage, query_stage)
    left = _match_side(reference_stage, query_stage, method, policy)
    right = _match_side(
        _side(stages_reference.get(stage_name), "right"),
        _side(stages_query.get(stage_name), "right"),
        method,
        policy,
    )
    if method is not FooterIdentityMethod.HYBRID:
        return left and right
    if not left or not right:
        return False
    return not _full_page_contradiction(reference.get("full_visual"), query.get("full_visual"), policy)


def query_match_indicators(
    reference_bank: Sequence[Mapping[str, Any]],
    query_bank: Sequence[Mapping[str, Any]],
    method: FooterIdentityMethod,
    policy: FooterVisualPolicy = FooterVisualPolicy(),
    *,
    stage_name: str = "preview_1920",
) -> tuple[bool, ...]:
    """One trial per query observation, regardless of reference-bank size."""

    if not reference_bank or not query_bank:
        raise ValueError("reference and query banks must be non-empty")
    reference_frames = {int(item["frame_index"]) for item in reference_bank}
    query_frames = {int(item["frame_index"]) for item in query_bank}
    if reference_frames & query_frames:
        raise ValueError("reference and query banks must be frame-disjoint")
    return tuple(
        any(
            match_spread_observations(
                reference,
                query,
                method,
                policy,
                stage_name=stage_name,
            )
            for reference in reference_bank
        )
        for query in query_bank
    )


def classify_match_count(n: int, matches: int, k_different: int, k_same: int) -> FooterIdentityDecision:
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise ValueError("n must be a positive integer")
    if not 0 <= matches <= n:
        raise ValueError("matches must be in [0, n]")
    if not 0 <= k_different < k_same <= n:
        raise ValueError("thresholds must satisfy 0 <= k_different < k_same <= n")
    if matches >= k_same:
        return FooterIdentityDecision.SAME
    if matches <= k_different:
        return FooterIdentityDecision.DIFFERENT
    return FooterIdentityDecision.UNKNOWN


def _match_side(
    reference: Any,
    query: Any,
    method: FooterIdentityMethod,
    policy: FooterVisualPolicy,
) -> bool:
    reference = _side(reference, "left") if isinstance(reference, Mapping) and "sides" in reference else reference
    query = _side(query, "left") if isinstance(query, Mapping) and "sides" in query else query
    if not isinstance(reference, Mapping) or not isinstance(query, Mapping):
        return False
    if method is FooterIdentityMethod.SEMANTIC_KEY:
        return _nonempty_equal(reference.get("normalized_label"), query.get("normalized_label"))
    if method is FooterIdentityMethod.SELECTED_RAW_TOKEN:
        return _nonempty_equal(reference.get("selected_raw"), query.get("selected_raw"))
    if method is FooterIdentityMethod.VARIANT_TOKEN_SET:
        return bool(_tokens(reference.get("variant_tokens")) & _tokens(query.get("variant_tokens")))
    visual = compare_visual_descriptors(
        _mapping(reference.get("visual")),
        _mapping(query.get("visual")),
    )
    strict_visual = (
        bool(visual["compatible"])
        and int(visual["hamming"]) <= policy.hamming_max
        and float(visual["projection_mae"]) <= policy.projection_mae_max
        and float(visual["ncc"]) >= policy.ncc_min
    )
    if method is FooterIdentityMethod.VISUAL_FINGERPRINT:
        return strict_visual
    if method is FooterIdentityMethod.HYBRID:
        token_overlap = (
            _nonempty_equal(reference.get("selected_raw"), query.get("selected_raw"))
            or bool(_tokens(reference.get("variant_tokens")) & _tokens(query.get("variant_tokens")))
        )
        relaxed_visual = (
            bool(visual["compatible"])
            and int(visual["hamming"]) <= policy.hamming_relaxed_max
            and float(visual["projection_mae"]) <= policy.projection_relaxed_mae_max
            and float(visual["ncc"]) >= policy.ncc_relaxed_min
        )
        return strict_visual or (relaxed_visual and token_overlap)
    raise ValueError(f"unsupported footer identity method: {method}")


def _full_page_contradiction(reference: Any, query: Any, policy: FooterVisualPolicy) -> bool:
    if not isinstance(reference, Mapping) or not isinstance(query, Mapping):
        return False
    for side in ("left", "right"):
        left = reference.get(side)
        right = query.get(side)
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            continue
        metrics = _compare_full_visual(left, right)
        if (
            metrics["hamming"] >= policy.full_page_different_hamming_min
            and metrics["projection_mae"] >= policy.full_page_different_projection_min
        ):
            return True
    return False


def _compare_full_visual(reference: Mapping[str, Any], query: Mapping[str, Any]) -> dict[str, float | int]:
    try:
        hamming = (int(str(reference["perceptual_hash"]), 16) ^ int(str(query["perceptual_hash"]), 16)).bit_count()
        a = tuple(int(item) for item in reference["horizontal_projection"]) + tuple(int(item) for item in reference["vertical_projection"])
        b = tuple(int(item) for item in query["horizontal_projection"]) + tuple(int(item) for item in query["vertical_projection"])
        mae = sum(abs(x - y) for x, y in zip(a, b)) / (255.0 * len(a)) if a and len(a) == len(b) else 1.0
    except (KeyError, TypeError, ValueError):
        return {"hamming": 64, "projection_mae": 1.0}
    return {"hamming": hamming, "projection_mae": mae}


def _side(stage: Any, side: str) -> Any:
    return stage.get("sides", {}).get(side) if isinstance(stage, Mapping) else None


def _semantic_key_match(reference: Any, query: Any) -> bool:
    if not isinstance(reference, Mapping) or not isinstance(query, Mapping):
        return False
    if reference.get("status") != "complete" or query.get("status") != "complete":
        return False
    left = reference.get("semantic_key")
    right = query.get("semantic_key")
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    return _nonempty_equal(left.get("left"), right.get("left")) and _nonempty_equal(
        left.get("right"), right.get("right")
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nonempty_equal(left: Any, right: Any) -> bool:
    return isinstance(left, str) and bool(left.strip()) and isinstance(right, str) and left == right


def _tokens(value: Any) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {str(item).strip() for item in value if isinstance(item, str) and item.strip()}


def _projection(image: np.ndarray, bins: int, *, axis: int) -> tuple[int, ...]:
    chunks = np.array_split(np.mean(image, axis=axis), bins)
    return tuple(int(round(float(np.mean(chunk)))) for chunk in chunks)
