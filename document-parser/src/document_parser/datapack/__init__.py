"""Datapack schema: the on-disk shape of a pre-transcribed book, serving-ready
per [[project_system_architecture_two_scenario]] (Scenario A produces these,
Scenario B only reads them -- no OCR or TTS synthesis on the serving path).
See docs/datapack-schema.md for the full design and rationale.

Deliberately does NOT import from `ingest.py` here (unlike this module's
other exports) -- `accessibility/__init__.py` avoids importing from `cli.py`
for the same reason: a module meant to be run via `python -m
document_parser.datapack.ingest` gets loaded twice (once as
`document_parser.datapack.ingest`, once as `__main__`) if its own package's
`__init__` already imported it, which is harmless but prints a
`RuntimeWarning`. Import ingest functions directly from
`document_parser.datapack.ingest` instead.
"""

from __future__ import annotations

from document_parser.datapack.loader import Datapack, load_datapack
from document_parser.datapack.schema import (
    SYSTEM_BOUNDARY_MESSAGES,
    build_audio_index_entry,
    build_manifest,
    system_message_key,
    utterance_key_for_cell,
    utterance_key_for_item,
    utterance_key_for_span,
)

__all__ = [
    "SYSTEM_BOUNDARY_MESSAGES",
    "Datapack",
    "build_audio_index_entry",
    "build_manifest",
    "load_datapack",
    "system_message_key",
    "utterance_key_for_cell",
    "utterance_key_for_item",
    "utterance_key_for_span",
]
