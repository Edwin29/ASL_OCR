"""Image-derived coarse homography anchors for offline order experiments.

The quad is only a warp surrogate.  It is never treated as the page truth or
as metric camera calibration; the curved binary mask remains the extraction
representation.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class CoarseWarpResult:
    success: bool
    image: np.ndarray
    mask: np.ndarray
    matrix: np.ndarray | None
    source_quad: np.ndarray | None
    reason: str | None
    diagnostics: dict[str, object]


def _ordered_quad(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    sums, differences = points.sum(axis=1), np.diff(points, axis=1).ravel()
    return np.array(
        [points[np.argmin(sums)], points[np.argmin(differences)], points[np.argmax(sums)], points[np.argmax(differences)]],
        dtype=np.float32,
    )


def estimate_quad_from_mask(mask: np.ndarray, min_area_ratio: float = 0.05) -> tuple[np.ndarray | None, dict[str, object]]:
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, {"reason": "WARP_ANCHOR_NOT_FOUND", "external_contour_count": 0}
    contour = max(contours, key=cv2.contourArea)
    area_ratio = float(cv2.contourArea(contour) / max(1, mask.shape[0] * mask.shape[1]))
    if area_ratio < min_area_ratio:
        return None, {"reason": "WARP_ANCHOR_NOT_FOUND", "area_ratio": area_ratio}
    perimeter = cv2.arcLength(contour, True)
    approximate = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
    if len(approximate) == 4 and cv2.isContourConvex(approximate):
        quad, method = approximate[:, 0, :].astype(np.float32), "approxPolyDP"
    else:
        quad, method = cv2.boxPoints(cv2.minAreaRect(contour)), "minAreaRect_surrogate"
    quad = _ordered_quad(quad)
    if abs(cv2.contourArea(quad)) < 16:
        return None, {"reason": "DEGENERATE_QUAD", "area_ratio": area_ratio, "anchor_method": method}
    return quad, {"area_ratio": area_ratio, "anchor_method": method, "external_contour_count": len(contours)}


def warp_from_mask(image: np.ndarray, mask: np.ndarray) -> CoarseWarpResult:
    quad, diagnostics = estimate_quad_from_mask(mask)
    if quad is None:
        return CoarseWarpResult(False, image.copy(), mask.copy(), None, None, str(diagnostics["reason"]), diagnostics)
    tl, tr, br, bl = quad
    width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    out_w, out_h = int(round(width)), int(round(height))
    if out_w < 2 or out_h < 2:
        diagnostics = {**diagnostics, "reason": "DEGENERATE_QUAD", "output_size": [out_w, out_h]}
        return CoarseWarpResult(False, image.copy(), mask.copy(), None, quad, "DEGENERATE_QUAD", diagnostics)
    destination = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], np.float32)
    matrix = cv2.getPerspectiveTransform(quad, destination)
    warped_image = cv2.warpPerspective(image, matrix, (out_w, out_h), flags=cv2.INTER_LINEAR)
    warped_mask = cv2.warpPerspective(mask, matrix, (out_w, out_h), flags=cv2.INTER_NEAREST)
    source_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    warped_gray = cv2.cvtColor(warped_image, cv2.COLOR_BGR2GRAY) if warped_image.ndim == 3 else warped_image
    source_sharpness = float(cv2.Laplacian(source_gray, cv2.CV_64F).var())
    warped_sharpness = float(cv2.Laplacian(warped_gray, cv2.CV_64F).var())
    diagnostics = {
        **diagnostics,
        "source_quad": quad.tolist(),
        "destination_quad": destination.tolist(),
        "matrix": matrix.tolist(),
        "output_size": [out_w, out_h],
        "interpolation": "INTER_LINEAR(image), INTER_NEAREST(mask)",
        "gradient_sharpness_before": source_sharpness,
        "gradient_sharpness_after": warped_sharpness,
        "gradient_sharpness_ratio": warped_sharpness / source_sharpness if source_sharpness else None,
        "metric_calibration": False,
    }
    return CoarseWarpResult(True, warped_image, warped_mask, matrix, quad, None, diagnostics)
