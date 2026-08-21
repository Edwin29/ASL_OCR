"""Reads a datapack directory written by `document_parser.datapack.ingest`
back into memory for serving (Scenario B). No OCR, no TTS synthesis here --
by the time a datapack exists, both are already done; this module only does
file I/O and one index inversion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Datapack:
    """A loaded book, ready to drive a live `SpeechController`/
    `BraillePresenter` session against (see `document_parser.server.session`).

    `audio_by_text` is keyed by the exact utterance *text* (not the
    ingest-time key) -- the audio pool is merged with the book-independent
    `_system` pool because that's what a `TtsEngineAdapter.speak(text, ...)`
    call actually receives; the ingest-time key only existed to let ingest
    enumerate items without duplicating work. Two different focus items that
    happen to produce identical spoken text collapsing onto the same audio
    entry is correct, not a collision -- `SpeechController` would say the
    exact same words either way.
    """

    book_id: str
    manifest: dict[str, Any]
    document: dict[str, Any]
    audio_by_text: dict[str, dict[str, Any]]


def _load_audio_index(index_path: Path, pool_dir: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    utterances = payload.get("utterances", {})
    by_text: dict[str, dict[str, Any]] = {}
    for entry in utterances.values():
        resolved = dict(entry)
        resolved["wav"] = str((pool_dir / entry["wav"]).resolve())
        by_text[entry["text"]] = resolved
    return by_text


def load_datapack(book_dir: Path, system_dir: Path) -> Datapack:
    """Load one book's datapack, merging in the shared `_system` boundary-
    message pool. `book_dir` and `system_dir` are the same directories
    `document_parser.datapack.ingest.build_datapack`/`ensure_system_pool`
    wrote."""
    manifest = json.loads((book_dir / "manifest.json").read_text(encoding="utf-8"))
    document = json.loads((book_dir / "document.json").read_text(encoding="utf-8"))

    audio_by_text = _load_audio_index(system_dir / "audio_index.json", system_dir)
    audio_by_text.update(_load_audio_index(book_dir / "audio_index.json", book_dir))

    return Datapack(
        book_id=str(manifest["book_id"]),
        manifest=manifest,
        document=document,
        audio_by_text=audio_by_text,
    )
