"""Small, deterministic image postprocessors for OCR A/B experiments."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Mapping, Protocol

import cv2
import numpy as np


@dataclass(frozen=True)
class PostprocessResult:
    success: bool
    image: np.ndarray | None
    processor_name: str
    processing_ms: float
    reason: str | None = None
    diagnostics: Mapping[str, object] = field(default_factory=dict)


class ImagePostprocessor(Protocol):
    def apply(self, image: np.ndarray) -> PostprocessResult:
        ...


@dataclass(frozen=True)
class LuminanceUnsharpConfig:
    sigma: float = 1.0
    amount: float = 0.5
    threshold: int = 3


class LuminanceUnsharpPostprocessor:
    name = "luminance_unsharp"

    def __init__(self, config: LuminanceUnsharpConfig | None = None):
        self.config = config or LuminanceUnsharpConfig()

    def apply(self, image: np.ndarray) -> PostprocessResult:
        if (
            not isinstance(image, np.ndarray)
            or image.ndim != 3
            or image.shape[2] != 3
            or image.size == 0
            or image.dtype != np.uint8
        ):
            return PostprocessResult(
                False,
                None,
                self.name,
                0.0,
                "invalid_input",
                {"message": "postprocess input must be a non-empty HxWx3 uint8 BGR image"},
            )
        if self.config.sigma <= 0 or self.config.amount < 0 or self.config.threshold < 0:
            return PostprocessResult(
                False,
                None,
                self.name,
                0.0,
                "invalid_config",
                {"message": "sigma must be positive; amount and threshold must be non-negative"},
            )

        started = time.perf_counter()
        try:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            luminance = lab[:, :, 0].astype(np.float32)
            blurred = cv2.GaussianBlur(luminance, (0, 0), self.config.sigma)
            detail = luminance - blurred
            selected = np.abs(detail) >= self.config.threshold
            sharpened = luminance.copy()
            sharpened[selected] += self.config.amount * detail[selected]
            lab_output = lab.copy()
            lab_output[:, :, 0] = np.clip(sharpened, 0, 255).astype(np.uint8)
            output = cv2.cvtColor(lab_output, cv2.COLOR_LAB2BGR)
            elapsed = (time.perf_counter() - started) * 1000.0
            return PostprocessResult(
                True,
                output,
                self.name,
                elapsed,
                diagnostics={
                    "sigma": self.config.sigma,
                    "amount": self.config.amount,
                    "threshold": self.config.threshold,
                    "selected_pixel_ratio": float(np.count_nonzero(selected) / selected.size),
                },
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            return PostprocessResult(
                False,
                None,
                self.name,
                elapsed,
                "processing_failed",
                {"message": f"{type(exc).__name__}: {exc}"},
            )
