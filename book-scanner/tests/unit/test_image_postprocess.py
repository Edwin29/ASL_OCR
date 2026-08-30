from __future__ import annotations

import numpy as np

from book_scanner.correct.postprocess import LuminanceUnsharpConfig, LuminanceUnsharpPostprocessor


def test_luminance_unsharp_preserves_contract_and_source():
    image = np.full((60, 80, 3), 100, dtype=np.uint8)
    image[:, 40:] = 180
    source = image.copy()

    result = LuminanceUnsharpPostprocessor().apply(image)

    assert result.success
    assert result.image is not None
    assert result.image.shape == image.shape
    assert result.image.dtype == np.uint8
    assert np.array_equal(image, source)
    assert not np.array_equal(result.image, image)


def test_luminance_unsharp_leaves_constant_image_effectively_unchanged():
    image = np.full((40, 50, 3), (60, 100, 140), dtype=np.uint8)
    result = LuminanceUnsharpPostprocessor().apply(image)
    assert result.success
    assert result.image is not None
    assert np.max(np.abs(result.image.astype(np.int16) - image.astype(np.int16))) <= 2
    assert result.diagnostics["selected_pixel_ratio"] == 0.0


def test_luminance_unsharp_rejects_invalid_configuration():
    processor = LuminanceUnsharpPostprocessor(LuminanceUnsharpConfig(sigma=0))
    result = processor.apply(np.zeros((20, 30, 3), dtype=np.uint8))
    assert not result.success
    assert result.reason == "invalid_config"
