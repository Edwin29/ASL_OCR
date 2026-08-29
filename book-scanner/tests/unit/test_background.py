from __future__ import annotations

import cv2
import numpy as np

from book_scanner.detect.background import _BLUR_KERNEL, foreground_mask, register_background


def _textured_background(w: int = 400, h: int = 300, seed: int = 0) -> np.ndarray:
    """Simulates a textured background (wood grain / cloth) -- this is
    exactly the condition that broke v1's Canny-based detection; here it
    should have no effect at all, since diffing against itself is zero."""
    rng = np.random.default_rng(seed)
    noise = rng.integers(80, 140, size=(h, w), dtype=np.uint8)
    return np.stack([noise] * 3, axis=-1)


def test_background_alone_produces_no_foreground():
    bg_frame = _textured_background()
    background = register_background(bg_frame)

    mask = foreground_mask(bg_frame, background)

    assert mask.sum() == 0


def test_book_on_textured_background_is_isolated():
    bg_frame = _textured_background()
    background = register_background(bg_frame)

    book_frame = bg_frame.copy()
    book_frame[50:250, 100:300] = 255  # a bright "book" rectangle

    mask = foreground_mask(book_frame, background)

    # the book region should be foreground...
    assert (mask[100:200, 150:250] > 0).all()
    # ...and a region clearly outside it should not be
    assert (mask[0:20, 0:20] == 0).all()


def test_global_brightness_shift_does_not_flood_foreground():
    """Simulates the reflective-material concern raised about the current
    (pre-final) test background: placing the book shifts the *whole*
    frame's reflected brightness, not just the region it covers -- e.g. it
    bounces more ambient light back once it's there. A naive absdiff would
    see the entire frame as "changed"; illumination normalization should
    keep the mask roughly limited to the book's actual footprint instead.
    """
    bg_frame = _textured_background(seed=1)
    background = register_background(bg_frame)

    book_frame = bg_frame.copy()
    book_frame[50:250, 100:300] = 220  # the book itself: genuinely different intensity
    # uniform brightness boost across the *entire* frame, simulating a
    # global reflection/lighting shift unrelated to the book's footprint
    book_frame = np.clip(book_frame.astype(np.int16) + 35, 0, 255).astype(np.uint8)

    mask = foreground_mask(book_frame, background)
    foreground_fraction = float((mask > 0).mean())

    # the book region is still detected...
    assert (mask[100:200, 150:250] > 0).all()
    # ...but the mask isn't flooded across the whole frame
    assert foreground_fraction < 0.5

    # counterfactual: prove this isn't just a low threshold -- a raw,
    # non-illumination-normalized diff on this exact scenario really would
    # flood, which is the failure mode normalization exists to prevent
    gray = cv2.cvtColor(book_frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, _BLUR_KERNEL, 0)
    naive_diff = cv2.absdiff(blurred, background.gray_blurred)
    _, naive_mask = cv2.threshold(naive_diff, 30, 255, cv2.THRESH_BINARY)
    naive_foreground_fraction = float((naive_mask > 0).mean())
    assert naive_foreground_fraction > 0.9


def test_frame_size_mismatch_raises():
    background = register_background(_textured_background(400, 300))
    mismatched = _textured_background(200, 150)

    try:
        foreground_mask(mismatched, background)
        assert False, "expected ValueError"
    except ValueError:
        pass
