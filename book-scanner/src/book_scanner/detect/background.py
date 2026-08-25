"""Background-subtraction foreground segmentation.

The core idea replacing v1's Canny+contour approach: since the camera is
physically fixed (project constraint), a single "empty" reference frame
captured once at session start lets every subsequent frame be segmented by
*what changed*, not by edge strength. This sidesteps both v1 failure modes
directly: background texture (wood grain, cloth folds) never produces a
diff since it never changes, and printed content inside the page (photos,
highlighted boxes) never competes with the page boundary since it's part of
the same unchanged... no wait, the page itself IS the changed region, so its
interior content doesn't matter at all -- the whole page silhouette is one
solid foreground blob regardless of what's printed on it.
"""

from __future__ import annotations

import cv2
import numpy as np

from book_scanner.detect.types import BackgroundRef

# Large blur: we want a smooth reference to diff against, not edges -- fine
# texture (wood grain, cloth weave) should blur away so its natural minor
# frame-to-frame flicker (JPEG noise, tiny lighting shifts) doesn't register
# as a diff. This is deliberately different from v1's small blur, which was
# tuned to preserve edges for Canny.
_BLUR_KERNEL = (21, 21)

# Minimum pixel intensity difference (0-255) to count as "changed".
_DIFF_THRESHOLD = 30

_MORPH_KERNEL = np.ones((15, 15), np.uint8)


def register_background(frame: np.ndarray) -> BackgroundRef:
    """Store `frame` (expected to show the empty capture area, no book) as
    the reference to diff subsequent frames against."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    blurred = cv2.GaussianBlur(gray, _BLUR_KERNEL, 0)
    h, w = gray.shape[:2]
    return BackgroundRef(gray_blurred=blurred, frame_size=(w, h))


def foreground_mask(frame: np.ndarray, background: BackgroundRef) -> np.ndarray:
    """Binary mask (255=changed/foreground, 0=background) of `frame`
    relative to `background`. Raises if `frame`'s size doesn't match the
    registered background."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    h, w = gray.shape[:2]
    if (w, h) != background.frame_size:
        raise ValueError(f"frame size {(w, h)} does not match registered background {background.frame_size}")

    blurred = cv2.GaussianBlur(gray, _BLUR_KERNEL, 0)
    diff = cv2.absdiff(blurred, background.gray_blurred)
    _, mask = cv2.threshold(diff, _DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
    # Close first to fill small internal holes (e.g. a very light-colored
    # region on the page that diffs weakly against a light background),
    # then open to drop small noise specks that survived thresholding.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _MORPH_KERNEL)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _MORPH_KERNEL)
    return mask
