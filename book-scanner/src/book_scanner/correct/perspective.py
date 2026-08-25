"""Pure perspective warp: four corner points -> a flat, axis-aligned crop.

No file I/O here -- see `pipeline.py` for the orchestration (hashing, atomic
write, metadata) that turns this into roadmap Stage 6's actual "scan output"
step. Kept separate so the warp math can be unit-tested without touching
disk, matching this project's measurement/policy-separation convention.

Output size is derived directly from the quad's own measured width/height
in the source image -- never inflated beyond that. Upscaling is not real
resolution (roadmap Stage 6 constraint: "보정 결과가 임의 확대를 통해 300dpi로
위장되지 않는다").
"""

from __future__ import annotations

import cv2
import numpy as np

from book_scanner.correct.types import Corners


def warp_to_rectangle(image: np.ndarray, corners: Corners) -> np.ndarray:
    tl = np.array(corners.top_left)
    tr = np.array(corners.top_right)
    br = np.array(corners.bottom_right)
    bl = np.array(corners.bottom_left)

    width = int(round(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))))
    height = int(round(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))))
    if width <= 0 or height <= 0:
        raise ValueError(f"degenerate corners produce non-positive output size: {width}x{height}")

    src = np.float32([tl, tr, br, bl])
    dst = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, matrix, (width, height))
