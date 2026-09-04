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

# Named device UI prompts are kept separate from navigation boundary text so
# the transport contract can address a stable cue name without duplicating
# Korean phrases in the Device Runtime.  They are synthesized by the same
# production Piper voice into the shared `_system` pool.
SYSTEM_UI_PROMPTS: dict[str, str] = {
    "screen.capture_catalog": "캡처 모드 데이터팩 선택 화면입니다.",
    "screen.reading_catalog": "리딩 모드 데이터팩 선택 화면입니다.",
    "screen.capture": "페이지 캡처 화면입니다.",
    "screen.reading": "리딩 화면입니다.",
    "catalog.new_datapack": "새 데이터팩 추가",
    "scan.started": "페이지 촬영을 시작합니다.",
    "scan.guidance": "책의 위치를 조정해 주세요.",
    "scan.guidance.page_not_found": "펼친 책의 양쪽 페이지 전체가 보이도록 맞춰 주세요.",
    "scan.guidance.out_of_frame": "책 가장자리가 화면 안에 들어오도록 맞춰 주세요.",
    "scan.guidance.content_occluded": "페이지를 가리는 손이나 물체를 치워 주세요.",
    "scan.guidance.hand_or_page_turn": "페이지에서 손을 떼고 잠시 기다려 주세요.",
    "scan.guidance.page_moving": "책과 카메라를 움직이지 말고 잠시 기다려 주세요.",
    "scan.guidance.move_left": "책을 왼쪽으로 옮겨 주세요.",
    "scan.guidance.move_right": "책을 오른쪽으로 옮겨 주세요.",
    "scan.guidance.move_up": "책을 위쪽으로 옮겨 주세요.",
    "scan.guidance.move_down": "책을 아래쪽으로 옮겨 주세요.",
    "scan.guidance.rotate_cw": "책을 시계 방향으로 조금 돌려 주세요.",
    "scan.guidance.rotate_ccw": "책을 반시계 방향으로 조금 돌려 주세요.",
    "scan.guidance.underexposed": "페이지가 어둡습니다. 조명을 밝게 해 주세요.",
    "scan.guidance.overexposed": "페이지가 너무 밝습니다. 강한 조명을 줄여 주세요.",
    "scan.guidance.glare": "페이지의 빛 반사를 줄여 주세요.",
    "scan.guidance.shadow_uneven": "페이지에 진 그림자가 생기지 않도록 조명을 맞춰 주세요.",
    "scan.guidance.blur": "초점이 맞도록 카메라와 책을 고정해 주세요.",
    "scan.guidance.insufficient_resolution": "카메라 해상도가 부족합니다. 카메라 설정을 확인해 주세요.",
    "scan.spread_sent": "페이지 전송이 완료되었습니다. 다음 페이지로 넘겨 주세요.",
    "scan.stopping": "촬영을 마치고 전송을 확인합니다.",
    "scan.finalizing": "데이터팩을 생성하고 있습니다.",
    "scan.saved": "데이터팩 저장이 완료되었습니다.",
    "server.connection_lost": "서버 연결이 끊어졌습니다.",
    "server.recovered": "서버 연결이 복구되었습니다.",
    "server.auth_failed": "서버 인증에 실패했습니다.",
    "parser.rejected": "페이지 처리가 거부되었습니다.",
    "catalog.empty": "읽을 수 있는 데이터팩이 없습니다.",
}


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
