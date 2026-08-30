"""Model-independent dense page-unwarping contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol

import numpy as np


class UnwarpFailureReason(Enum):
    MODEL_NOT_FOUND = "model_not_found"
    MODEL_LOAD_FAILED = "model_load_failed"
    INVALID_INPUT = "invalid_input"
    INFERENCE_FAILED = "inference_failed"
    INVALID_OUTPUT = "invalid_output"


@dataclass(frozen=True)
class UnwarpResult:
    success: bool
    image: np.ndarray | None
    adapter_name: str
    device: str
    processing_ms: float
    input_size: tuple[int, int]
    output_size: tuple[int, int] | None
    reason: UnwarpFailureReason | None = None
    diagnostics: Mapping[str, object] = field(default_factory=dict)


class PageUnwarper(Protocol):
    def unwarp(self, image: np.ndarray) -> UnwarpResult:
        ...
