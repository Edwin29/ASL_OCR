"""Datapack schema: manifest/audio-index dict builders and utterance-key
derivation. See docs/datapack-schema.md for the full design.

Kept as plain dict builders, matching the rest of the accessibility package's
convention (see `accessibility.domain.accessible_document`) -- a datapack's
`document.json` *is* an `AccessibleDocument` (the output of
`flatten_document`), unchanged, so its own schema stays a plain dict too
rather than mixing a dataclass model into a tree that's otherwise all dicts.

This module intentionally has no I/O and never calls into OCR or TTS -- it
only defines shapes and key-naming rules, so the same rules can be shared,
without duplication, by a future ingest job (writes datapacks) and a future
server (reads them).
"""

from __future__ import annotations

import hashlib
from typing import Any

SCHEMA_VERSION = 1

# The complete, book-independent set of boundary_message strings the
# navigation state machine can produce -- verified by grepping every
# `boundary_message=` call site in `application/document_navigator.py`,
# `application/table_navigator.py`, and `application/speech_controller.py`
# (2026-08-21). These never depend on document content, so they are
# synthesized once into a shared `_system` audio pool instead of being
# duplicated into every book's datapack.
SYSTEM_BOUNDARY_MESSAGES: tuple[str, ...] = (
    "문서의 끝입니다.",
    "문서의 시작입니다.",
    "문서의 마지막 페이지입니다.",
    "문서의 첫 페이지입니다.",
    "이 버튼 입력은 아직 지원되지 않습니다.",
    "현재 항목을 찾을 수 없습니다.",
    "이 항목에는 점자로 표시할 수식이 없습니다.",
    "더 이상 표시할 수식이 없습니다.",
    "이전에 표시할 수식이 없습니다.",
    "표를 찾을 수 없습니다.",
    "표 구조를 인식하지 못했습니다. 표 탐색을 사용할 수 없습니다.",
    "첫 행입니다.",
    "마지막 행입니다.",
    "첫 열입니다.",
    "마지막 열입니다.",
    "셀을 찾을 수 없습니다.",
    "셀 내용의 끝입니다.",
    "셀 내용의 시작입니다.",
)


def system_message_key(text: str) -> str:
    """Stable key for one `SYSTEM_BOUNDARY_MESSAGES` entry in the shared
    `_system` audio pool. Hash-derived (same convention as
    `document_parser.ocr.cache.OcrResultCache.cache_key`) rather than a plain
    enumerated index, so the key never changes if the tuple above is
    reordered or extended."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def utterance_key_for_item(item: dict[str, Any]) -> str:
    """Key for the whole-item announcement (what's spoken on first landing on
    this focus item) -- just the item's own id, since it's already unique
    within a document (see `accessible_document.build_focus_item`)."""
    return str(item["id"])


def utterance_key_for_span(item: dict[str, Any], span_index: int) -> str:
    """Key for one inline-math span's announcement inside a TEXT item (what's
    spoken when 좌우 연장 extends onto that span). Not used for top-level MATH
    items -- `braille_scrollable_spans(math_item)` returns `[math_item]`
    itself, so the item-level key already covers span_index 0's text."""
    return f"{item['id']}#{span_index}"


def utterance_key_for_cell(item: dict[str, Any], cell: dict[str, Any]) -> str:
    """Key for one table cell's announcement. Prefers the cell's own
    `cell_id`/`id` (already unique) when present; falls back to a
    row/column-derived key built from the owning item's id, for cells a
    future OCR/flattening change might emit without one."""
    cell_id = cell.get("id")
    if cell_id:
        return str(cell_id)
    row_index = cell.get("row_index", "?")
    column_index = cell.get("column_index", "?")
    return f"{item['id']}#r{row_index}c{column_index}"


def build_manifest(
    book_id: str,
    title: str,
    page_ids: list[str],
    created_at: str,
    engine_manifest: dict[str, object],
    tts_manifest: dict[str, object],
    validation_summary: dict[str, object],
) -> dict[str, object]:
    """Build a datapack's `manifest.json`. `page_ids` must match
    `document.json`'s page order exactly -- kept as a separate top-level list
    so a book-selection UI can read just this small file instead of parsing
    the full (potentially large) `document.json` for page count/order."""
    return {
        "schema_version": SCHEMA_VERSION,
        "book_id": book_id,
        "title": title,
        "page_ids": list(page_ids),
        "created_at": created_at,
        "engine_manifest": engine_manifest,
        "tts_manifest": tts_manifest,
        "validation_summary": validation_summary,
    }


def build_audio_index_entry(
    text: str,
    wav_path: str,
    duration_ms: int,
    sample_rate: int,
) -> dict[str, object]:
    """Build one entry of an `audio_index.json`'s `utterances` map. `text` is
    kept alongside the audio (not just the wav path) so a cache-miss fallback
    at serve time can log/synthesize using the exact same text without having
    to recompute it from the document, and so a human can inspect what was
    synthesized without opening every wav file."""
    return {
        "text": text,
        "wav": wav_path,
        "duration_ms": duration_ms,
        "sample_rate": sample_rate,
    }
