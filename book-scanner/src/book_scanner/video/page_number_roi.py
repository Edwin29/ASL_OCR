"""Side-aware bottom-outer ROI extraction for corrected and preview pages."""

from __future__ import annotations

import cv2
import numpy as np

from .config import PageNumberPolicy
from .types import PageSide


def corrected_page_number_roi(
    image: np.ndarray,
    side: PageSide,
    policy: PageNumberPolicy,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    gray = _gray(image)
    height, width = gray.shape
    if side is PageSide.LEFT:
        x0, x1 = policy.left_x_min, policy.left_x_max
    else:
        x0, x1 = policy.right_x_min, policy.right_x_max
    return _fractional_crop(gray, x0, x1, policy.y_min, policy.y_max, width, height)


def preview_page_number_roi(
    gray_preview: np.ndarray,
    mask_preview: np.ndarray,
    seam_fraction: float | None,
    side: PageSide,
    policy: PageNumberPolicy,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    gray = _gray(gray_preview)
    if not isinstance(mask_preview, np.ndarray) or mask_preview.shape != gray.shape:
        raise ValueError("preview mask must match grayscale preview")
    height, width = gray.shape
    seam = 0.5 if seam_fraction is None else float(seam_fraction)
    if not 0.2 <= seam <= 0.8:
        raise ValueError("preview seam is outside fixed spread region")
    split = min(width - 1, max(1, round(width * seam)))
    x_start, x_end = (0, split) if side is PageSide.LEFT else (split, width)
    side_mask = mask_preview[:, x_start:x_end] > 0
    ys, xs = np.nonzero(side_mask)
    if len(xs) < 64:
        raise ValueError(f"{side.value} preview page mask is missing")
    bx0, bx1 = int(xs.min()) + x_start, int(xs.max()) + x_start + 1
    by0, by1 = int(ys.min()), int(ys.max()) + 1
    page = gray[by0:by1, bx0:bx1].copy()
    active = (mask_preview[by0:by1, bx0:bx1] > 0)
    fill = int(np.median(page[active]))
    page[~active] = fill
    roi, local_bbox = corrected_page_number_roi(page, side, policy)
    lx, ly, lw, lh = local_bbox
    return roi, (bx0 + lx, by0 + ly, lw, lh)


def _fractional_crop(
    gray: np.ndarray,
    x0_fraction: float,
    x1_fraction: float,
    y0_fraction: float,
    y1_fraction: float,
    width: int,
    height: int,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    x0 = min(width - 1, max(0, int(round(width * x0_fraction))))
    x1 = min(width, max(x0 + 1, int(round(width * x1_fraction))))
    y0 = min(height - 1, max(0, int(round(height * y0_fraction))))
    y1 = min(height, max(y0 + 1, int(round(height * y1_fraction))))
    return gray[y0:y1, x0:x1].copy(), (x0, y0, x1 - x0, y1 - y0)


def _gray(image: np.ndarray) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("image must be a non-empty ndarray")
    if image.ndim == 2:
        return image
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    raise ValueError("image must be grayscale or BGR")
