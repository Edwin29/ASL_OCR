"""Accessibility runtime: turns a validated Page IR document into an
AccessibleDocument and provides document/table navigation over it. See
`document_parser.accessibility.flattening.flatten_document` for the entry
point that consumes Page IR, and `document_parser.accessibility.application`
for navigation.

TTS, math/Korean braille translation, and hardware I/O are later phases and
are not implemented in this package yet.
"""

from document_parser.accessibility.adapters import (
    FakeTtsEngineAdapter,
    PageIrCompatibilityError,
    PiperTtsEngineAdapter,
    TtsEngineAdapter,
    check_compatibility_profile,
)
from document_parser.accessibility.application import SpeechController
from document_parser.accessibility.braille import BraillePresenter
from document_parser.accessibility.domain import NavigationCommand, NavigationResult, NavigationState
from document_parser.accessibility.flattening import classify_ast_status, flatten_document

__all__ = [
    "BraillePresenter",
    "FakeTtsEngineAdapter",
    "NavigationCommand",
    "NavigationResult",
    "NavigationState",
    "PageIrCompatibilityError",
    "PiperTtsEngineAdapter",
    "SpeechController",
    "TtsEngineAdapter",
    "check_compatibility_profile",
    "classify_ast_status",
    "flatten_document",
]
