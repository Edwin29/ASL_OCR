"""Boundary adapters between externally-owned formats (Page IR JSON) and the
accessibility layer's own domain shapes."""

from document_parser.accessibility.adapters.page_ir_adapter import (
    PageIrCompatibilityError,
    check_compatibility_profile,
)
from document_parser.accessibility.adapters.tts_engine import (
    FakeTtsEngineAdapter,
    PiperTtsEngineAdapter,
    TtsEngineAdapter,
)

__all__ = [
    "FakeTtsEngineAdapter",
    "PageIrCompatibilityError",
    "PiperTtsEngineAdapter",
    "TtsEngineAdapter",
    "check_compatibility_profile",
]
