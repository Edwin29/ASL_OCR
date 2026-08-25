from __future__ import annotations

import numpy as np

from book_scanner.detect.background import foreground_mask, register_background


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


def test_frame_size_mismatch_raises():
    background = register_background(_textured_background(400, 300))
    mismatched = _textured_background(200, 150)

    try:
        foreground_mask(mismatched, background)
        assert False, "expected ValueError"
    except ValueError:
        pass
