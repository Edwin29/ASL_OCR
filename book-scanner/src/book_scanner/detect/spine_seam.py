"""Fixed-layout spine seam detection and left/right mask ownership.

The seam is an image-coordinate prior for one controlled scanner geometry. It
is not camera calibration and it does not assume either page is a rectangle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol

import cv2
import numpy as np


@dataclass(frozen=True)
class SpineSeamConfig:
    centerline_fraction: float = 0.5
    allowed_half_width_fraction: float = 0.06
    uncertainty_band_px: int = 8
    max_step_px: int = 8
    movement_penalty: float = 0.035
    center_prior_weight: float = 0.18
    edge_penalty_weight: float = 1.25
    outside_overlap_penalty: float = 1.75
    smoothing_window_px: int = 15
    solve_scale: float = 0.25
    min_overlap_pixels: int = 64
    min_confidence: float = 0.0

    def __post_init__(self) -> None:
        if not 0 < self.centerline_fraction < 1:
            raise ValueError("centerline_fraction must be in (0, 1)")
        if not 0 < self.allowed_half_width_fraction < 0.5:
            raise ValueError("allowed_half_width_fraction must be in (0, 0.5)")
        if self.uncertainty_band_px < 0 or self.max_step_px < 0:
            raise ValueError("pixel widths must be non-negative")
        if self.smoothing_window_px < 1:
            raise ValueError("smoothing_window_px must be positive")
        if not 0 < self.solve_scale <= 1:
            raise ValueError("solve_scale must be in (0, 1]")


@dataclass(frozen=True)
class SpineSeam:
    points_full: tuple[tuple[int, int], ...]
    confidence: float
    uncertainty_band_px: int
    method: str
    fallback_used: bool
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    @property
    def x_by_row(self) -> np.ndarray:
        return np.asarray([point[0] for point in self.points_full], dtype=np.int32)


@dataclass(frozen=True)
class SeamResult:
    seam: SpineSeam | None
    reason: str | None
    cost_map: np.ndarray | None
    band_origin_x: int
    diagnostics: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OwnershipResult:
    left_mask: np.ndarray
    right_mask: np.ndarray
    ambiguous_mask: np.ndarray
    left_conservative_mask: np.ndarray
    right_conservative_mask: np.ndarray
    diagnostics: Mapping[str, object]


class SpineSeamDetector(Protocol):
    name: str

    def detect(self, frame: np.ndarray, left_mask: np.ndarray, right_mask: np.ndarray) -> SeamResult:
        ...


def seam_points_in_roi(
    seam: SpineSeam,
    origin: tuple[int, int],
    size: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
    """Translate the full-frame seam portion intersecting an ROI to local coordinates."""
    ox, oy = origin
    width, height = size
    return tuple(
        (x - ox, y - oy)
        for x, y in seam.points_full
        if oy <= y < oy + height and ox <= x < ox + width
    )


def _validate_inputs(frame: np.ndarray, left_mask: np.ndarray, right_mask: np.ndarray) -> tuple[int, int]:
    if frame is None or frame.ndim not in (2, 3):
        raise ValueError("frame must be grayscale or color")
    if left_mask.shape[:2] != frame.shape[:2] or right_mask.shape[:2] != frame.shape[:2]:
        raise ValueError("page masks must use full-frame coordinates")
    return frame.shape[:2]


def _allowed_band(width: int, config: SpineSeamConfig) -> tuple[int, int, int]:
    center = int(round(width * config.centerline_fraction))
    half = max(1, int(round(width * config.allowed_half_width_fraction)))
    return max(0, center - half), min(width, center + half + 1), center


def _input_failure(
    frame: np.ndarray,
    left_mask: np.ndarray,
    right_mask: np.ndarray,
    config: SpineSeamConfig,
    require_overlap: bool,
) -> SeamResult | None:
    _height, width = _validate_inputs(frame, left_mask, right_mask)
    x0, x1, _center = _allowed_band(width, config)
    left_count, right_count = int(np.count_nonzero(left_mask)), int(np.count_nonzero(right_mask))
    if left_count == 0 or right_count == 0:
        return SeamResult(None, "NO_PAGE", None, x0, {"left_px": left_count, "right_px": right_count})
    overlap = (left_mask[:, x0:x1] > 0) & (right_mask[:, x0:x1] > 0)
    overlap_count = int(np.count_nonzero(overlap))
    if require_overlap and overlap_count < config.min_overlap_pixels:
        return SeamResult(None, "NO_OVERLAP_SUPPORT", None, x0, {"overlap_support_px": overlap_count})
    return None


class FixedCenterlineSeamDetector:
    name = "fixed-centerline"

    def __init__(self, config: SpineSeamConfig = SpineSeamConfig()):
        self.config = config

    def detect(self, frame: np.ndarray, left_mask: np.ndarray, right_mask: np.ndarray) -> SeamResult:
        failure = _input_failure(frame, left_mask, right_mask, self.config, require_overlap=False)
        if failure is not None:
            return failure
        height, width = frame.shape[:2]
        x0, _x1, center = _allowed_band(width, self.config)
        seam = SpineSeam(
            points_full=tuple((center, y) for y in range(height)),
            confidence=1.0,
            uncertainty_band_px=self.config.uncertainty_band_px,
            method=self.name,
            fallback_used=False,
            diagnostics={"centerline_x": center, "metric_calibration": False},
        )
        return SeamResult(seam, None, None, x0, seam.diagnostics)


class _DynamicSeamDetector:
    name = "dynamic"
    mask_aware = False

    def __init__(self, config: SpineSeamConfig = SpineSeamConfig()):
        self.config = config

    def _cost(self, frame: np.ndarray, left_mask: np.ndarray, right_mask: np.ndarray, x0: int, x1: int, center: int) -> tuple[np.ndarray, dict[str, object]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        gray = cv2.GaussianBlur(gray, (9, 9), 0)
        strip = gray[:, x0:x1].astype(np.float32) / 255.0
        width = max(1, x1 - x0 - 1)
        x_positions = np.arange(x0, x1, dtype=np.float32)
        center_prior = np.abs(x_positions - center) / max(1.0, width / 2.0)
        cost = strip + self.config.center_prior_weight * center_prior[None, :]
        diagnostics: dict[str, object] = {"luminance_cost": True, "content_edge_cost": False}
        if self.mask_aware:
            edges = cv2.Canny(gray, 45, 135)
            edge_density = cv2.GaussianBlur((edges > 0).astype(np.float32), (11, 11), 0)[:, x0:x1]
            overlap = ((left_mask[:, x0:x1] > 0) & (right_mask[:, x0:x1] > 0)).astype(np.float32)
            cost = cost + self.config.edge_penalty_weight * edge_density
            cost = cost + self.config.outside_overlap_penalty * (1.0 - overlap)
            diagnostics.update({
                "content_edge_cost": True,
                "overlap_support_px": int(np.count_nonzero(overlap)),
                "edge_support_px": int(np.count_nonzero(edges[:, x0:x1])),
            })
        return cost.astype(np.float32), diagnostics

    def _solve(
        self,
        cost: np.ndarray,
        max_step_px: int | None = None,
        movement_penalty: float | None = None,
    ) -> tuple[np.ndarray | None, dict[str, object]]:
        height, width = cost.shape
        if height == 0 or width == 0 or not np.isfinite(cost).any():
            return None, {"reason": "SEAM_PATH_NOT_FOUND"}
        accumulated = cost[0].astype(np.float64)
        parents = np.zeros((height, width), dtype=np.int16)
        indexes = np.arange(width)
        max_step = self.config.max_step_px if max_step_px is None else max_step_px
        step_penalty = self.config.movement_penalty if movement_penalty is None else movement_penalty
        for y in range(1, height):
            best = np.full(width, np.inf, dtype=np.float64)
            best_parent = np.zeros(width, dtype=np.int16)
            for delta in range(-max_step, max_step + 1):
                predecessor = indexes - delta
                valid = (predecessor >= 0) & (predecessor < width)
                values = np.full(width, np.inf, dtype=np.float64)
                values[valid] = accumulated[predecessor[valid]] + step_penalty * abs(delta)
                improve = values < best
                best[improve] = values[improve]
                best_parent[improve] = predecessor[improve].astype(np.int16)
            accumulated = best + cost[y]
            parents[y] = best_parent
        finite = np.flatnonzero(np.isfinite(accumulated))
        if not len(finite):
            return None, {"reason": "SEAM_PATH_NOT_FOUND"}
        ordered = finite[np.argsort(accumulated[finite])]
        end = int(ordered[0])
        best_cost = float(accumulated[end])
        second_cost = float(accumulated[ordered[1]]) if len(ordered) > 1 else best_cost
        path = np.empty(height, dtype=np.int32)
        path[-1] = end
        for y in range(height - 1, 0, -1):
            path[y - 1] = int(parents[y, path[y]])
        window = self.config.smoothing_window_px
        if window > 1:
            window = window if window % 2 else window + 1
            radius = window // 2
            padded = np.pad(path, (radius, radius), mode="edge")
            path = np.median(np.lib.stride_tricks.sliding_window_view(padded, window), axis=1).round().astype(np.int32)
        margin = max(0.0, second_cost - best_cost)
        confidence = float(np.clip(margin / max(1.0, abs(best_cost) / height), 0.0, 1.0))
        return path, {"best_path_cost": best_cost, "second_endpoint_cost": second_cost, "cost_margin": margin, "confidence": confidence}

    def detect(self, frame: np.ndarray, left_mask: np.ndarray, right_mask: np.ndarray) -> SeamResult:
        failure = _input_failure(frame, left_mask, right_mask, self.config, require_overlap=True)
        if failure is not None:
            return failure
        height, width = frame.shape[:2]
        x0, x1, center = _allowed_band(width, self.config)
        cost, cost_diagnostics = self._cost(frame, left_mask, right_mask, x0, x1, center)
        scale = self.config.solve_scale
        solve_width = max(3, int(round(cost.shape[1] * scale)))
        solve_height = max(3, int(round(cost.shape[0] * scale)))
        solve_cost = cv2.resize(cost, (solve_width, solve_height), interpolation=cv2.INTER_AREA)
        solved_path, solve_diagnostics = self._solve(
            solve_cost,
            max_step_px=max(1, int(round(self.config.max_step_px * scale))),
            movement_penalty=self.config.movement_penalty / scale,
        )
        diagnostics = {
            **cost_diagnostics,
            **solve_diagnostics,
            "allowed_band": [x0, x1],
            "solve_scale": scale,
            "solve_size": [solve_width, solve_height],
            "metric_calibration": False,
        }
        if solved_path is None:
            return SeamResult(None, "SEAM_PATH_NOT_FOUND", cost, x0, diagnostics)
        solve_rows = np.arange(solve_height, dtype=np.float32)
        full_rows = np.linspace(0, solve_height - 1, height, dtype=np.float32)
        path_scaled = np.interp(full_rows, solve_rows, solved_path.astype(np.float32))
        local_path = path_scaled * ((cost.shape[1] - 1) / max(1, solve_width - 1))
        path = np.rint(local_path).astype(np.int32) + x0
        if np.any(path < x0) or np.any(path >= x1):
            return SeamResult(None, "SEAM_OUTSIDE_ALLOWED_BAND", cost, x0, diagnostics)
        confidence = float(solve_diagnostics["confidence"])
        if confidence < self.config.min_confidence:
            return SeamResult(None, "LOW_CONFIDENCE_SEAM", cost, x0, diagnostics)
        row_steps = np.abs(np.diff(path))
        diagnostics.update({
            "mean_row_step_px": float(row_steps.mean()) if row_steps.size else 0.0,
            "max_row_step_px": int(row_steps.max()) if row_steps.size else 0,
            "mean_center_distance_px": float(np.abs(path - center).mean()),
            "max_center_distance_px": int(np.abs(path - center).max()),
        })
        seam = SpineSeam(
            points_full=tuple((int(x), y) for y, x in enumerate(path)),
            confidence=confidence,
            uncertainty_band_px=self.config.uncertainty_band_px,
            method=self.name,
            fallback_used=False,
            diagnostics=diagnostics,
        )
        return SeamResult(seam, None, cost, x0, diagnostics)


class LuminanceValleySeamDetector(_DynamicSeamDetector):
    name = "luminance-valley"
    mask_aware = False


class MaskAwareSpineSeamDetector(_DynamicSeamDetector):
    name = "mask-aware-content-preserving"
    mask_aware = True


def apply_seam_ownership(
    left_mask: np.ndarray,
    right_mask: np.ndarray,
    seam: SpineSeam,
    policy: str = "union-preserving",
) -> OwnershipResult:
    if left_mask.shape != right_mask.shape:
        raise ValueError("left and right masks must have the same dimensions")
    height, width = left_mask.shape[:2]
    path = seam.x_by_row
    if len(path) != height:
        raise ValueError("seam must contain one point per image row")
    x_grid = np.arange(width, dtype=np.int32)[None, :]
    split = path[:, None]
    left, right = left_mask > 0, right_mask > 0
    shared = left & right
    half = seam.uncertainty_band_px
    ambiguous = shared & (np.abs(x_grid - split) <= half)
    if policy == "hard":
        left_out = left & (x_grid <= split)
        right_out = right & (x_grid > split)
    elif policy in {"union-preserving", "uncertainty-band"}:
        left_out = left & (~shared | (x_grid <= split))
        right_out = right & (~shared | (x_grid > split))
        if policy == "uncertainty-band":
            left_out &= ~ambiguous
            right_out &= ~ambiguous
    else:
        raise ValueError(f"unknown ownership policy: {policy}")
    left_conservative = left_out | ambiguous
    right_conservative = right_out | ambiguous
    original_union = left | right
    output_union = left_out | right_out
    overlap_after = left_out & right_out
    diagnostics = {
        "policy": policy,
        "prediction_overlap_px_before": int(np.count_nonzero(shared)),
        "prediction_overlap_px_after": int(np.count_nonzero(overlap_after)),
        "original_union_px": int(np.count_nonzero(original_union)),
        "output_union_px": int(np.count_nonzero(output_union)),
        "union_lost_px": int(np.count_nonzero(original_union & ~output_union)),
        "ambiguous_px": int(np.count_nonzero(ambiguous)),
    }
    return OwnershipResult(
        np.where(left_out, 255, 0).astype(np.uint8),
        np.where(right_out, 255, 0).astype(np.uint8),
        np.where(ambiguous, 255, 0).astype(np.uint8),
        np.where(left_conservative, 255, 0).astype(np.uint8),
        np.where(right_conservative, 255, 0).astype(np.uint8),
        diagnostics,
    )
