"""One-time generator: builds tests/fixtures/generated/ from tests/fixtures/real/.

Run manually (`python tests/fixtures/generate_fixtures.py`) whenever the
source photos in real/ change; the output is committed, not regenerated on
every test run.

Design note (see book-scanner/README.md for the full finding): the six real
source photos were taken before the physical mounting jig existed, on a
plain wooden desk. Their background has enough edge content that a simple
Canny-contour detector often locks onto a region spanning most of the frame
rather than cleanly isolating "just the page" -- confirmed by running
measure_page against them directly. Rather than pretend that noise away,
these fixtures build each case by taking the *whole real photo* as one
"content blob" and placing/rotating/scaling that whole blob within a larger
canvas. This keeps every case grounded in genuine photographed pixels (per
the instruction to deliberately rotate/damage real images) while making the
expected outcome deterministic regardless of exactly which desk/page edges
get picked up inside the blob.
"""

from __future__ import annotations

import os

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
REAL_DIR = os.path.join(_HERE, "real")
OUT_DIR = os.path.join(_HERE, "generated")

BASE_PHOTO = "20260825_170921.jpg"  # clean, well-lit, fills its original frame
CANVAS_MARGIN = 400  # px added on each side; large enough that a 60deg-rotated
# 1200x900 blob (diagonal ~1500px) still fits without being auto-shrunk to
# the canvas, so rotation and out-of-frame stay independently testable


def _load_base() -> np.ndarray:
    path = os.path.join(REAL_DIR, BASE_PHOTO)
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"missing base fixture: {path}")
    return img


def _compose_on_canvas(content: np.ndarray, canvas_size: tuple[int, int], angle_deg: float = 0.0) -> np.ndarray:
    """Paste (optionally rotated) `content` centered on a black canvas of `canvas_size` (w, h)."""
    if angle_deg:
        h, w = content.shape[:2]
        # Expand the rotation canvas so the rotated content isn't clipped.
        diag = int(np.ceil(np.hypot(w, h)))
        rot_canvas = np.zeros((diag, diag, 3), dtype=content.dtype)
        y0, x0 = (diag - h) // 2, (diag - w) // 2
        rot_canvas[y0 : y0 + h, x0 : x0 + w] = content
        matrix = cv2.getRotationMatrix2D((diag / 2, diag / 2), angle_deg, 1.0)
        content = cv2.warpAffine(rot_canvas, matrix, (diag, diag))

    canvas_w, canvas_h = canvas_size
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    ch, cw = content.shape[:2]
    if ch > canvas_h or cw > canvas_w:
        scale = min(canvas_w / cw, canvas_h / ch)
        content = cv2.resize(content, (int(cw * scale), int(ch * scale)))
        ch, cw = content.shape[:2]
    y0, x0 = (canvas_h - ch) // 2, (canvas_w - cw) // 2
    canvas[y0 : y0 + ch, x0 : x0 + cw] = content
    return canvas


def _perspective_warp(content: np.ndarray, strength: float = 0.35) -> np.ndarray:
    """Trapezoid-warp `content` in place (simulates an extreme oblique viewing angle)."""
    h, w = content.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dx = w * strength
    dst = np.float32([[dx, 0], [w - dx, 0], [w, h], [0, h]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(content, matrix, (w, h))


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    base = _load_base()
    h, w = base.shape[:2]
    canvas_size = (w + 2 * CANVAS_MARGIN, h + 2 * CANVAS_MARGIN)

    cases = {
        "good_margin.jpg": _compose_on_canvas(base, canvas_size, angle_deg=0.0),
        "rotated_30.jpg": _compose_on_canvas(base, canvas_size, angle_deg=30.0),
        "rotated_60.jpg": _compose_on_canvas(base, canvas_size, angle_deg=60.0),
        "too_small.jpg": _compose_on_canvas(
            cv2.resize(base, (int(w * 0.25), int(h * 0.25))), canvas_size
        ),
        "perspective_warp.jpg": _compose_on_canvas(_perspective_warp(base), canvas_size, angle_deg=0.0),
    }

    for name, image in cases.items():
        out_path = os.path.join(OUT_DIR, name)
        cv2.imwrite(out_path, image)
        print(f"wrote {out_path} ({image.shape[1]}x{image.shape[0]})")

    print(
        "note: out_of_frame case uses the unmodified real photo "
        f"tests/fixtures/real/{BASE_PHOTO} directly (its content already "
        "fills its frame edge-to-edge) -- see test_judge.py"
    )


if __name__ == "__main__":
    main()
