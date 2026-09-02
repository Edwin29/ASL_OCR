"""Production PaddleOCR-VL/Piper E0-B Desktop end-to-end acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import threading
import time
import uuid
import wave
from array import array
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .desktop_loopback_acceptance import (
    E0B_SOURCE_SHA256,
    LoopbackAcceptanceError,
    LoopbackController,
    PreparedInputs,
    _write_json,
    parse_json_lines,
    run_desktop_loopback_acceptance,
    validate_prepared_root,
)


_DEFAULT_PIPER_MODEL = Path(r"D:\models\piper-korean\ko_KR-kss-medium.onnx")
_DEFAULT_ESPEAK_DATA = Path(r"D:\espeak-ng-data")
_REQUIRED_VL_MODEL_DIRS = (
    Path(".paddlex/official_models/PP-DocLayoutV3"),
    Path(".paddlex/official_models/PaddleOCR-VL-1.6"),
)
_BANNED_PROVENANCE = ("bench", "fixture", "deterministic-bench", "remote bench content")
_EXPECTED_POSITIONS = (
    ("00000001", "L"),
    ("00000001", "R"),
    ("00000002", "L"),
    ("00000002", "R"),
)


@dataclass(frozen=True, slots=True)
class ProductionAssets:
    prepared: PreparedInputs
    model_home: Path
    piper_model: Path
    piper_config: Path
    espeak_data: Path
    model_tree_digest: str
    model_file_count: int


@dataclass(slots=True)
class ProductionLoopbackController:
    """Pace navigation by real Device playback and retain clear-frame evidence."""

    delegate: LoopbackController = field(default_factory=LoopbackController)
    await_playback: bool = True
    reading_snapshots: list[dict[str, Any]] = field(default_factory=list)
    playback_generations: list[int] = field(default_factory=list)
    reading_positions: list[tuple[str, str]] = field(default_factory=list)
    navigation_index: int = 0
    reverse_verified: bool = False
    braille_positions: set[tuple[str, str]] = field(default_factory=set)
    _last_focus_by_position: dict[tuple[str, str], str] = field(default_factory=dict)
    _pending_commands: tuple[str, ...] = ()
    _awaiting_generation: int | None = None

    def handle(self, record: Mapping[str, Any]) -> tuple[str, ...]:
        record_type = record.get("type")
        if record_type == "reading_snapshot":
            cursor_value = record.get("cursor")
            cursor = cursor_value if isinstance(cursor_value, Mapping) else {}
            generation = cursor.get("generation")
            cells = record.get("braille_cells")
            audio_ref = record.get("audio_ref")
            if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
                raise LoopbackAcceptanceError("production reading generation is invalid")
            if not isinstance(cells, list):
                raise LoopbackAcceptanceError("production reading snapshot braille is invalid")
            if any(isinstance(cell, bool) or not isinstance(cell, int) or not 0 <= cell <= 63 for cell in cells):
                raise LoopbackAcceptanceError("production reading snapshot has invalid six-dot cells")
            if not isinstance(audio_ref, str) or not audio_ref.startswith("s0-audio:"):
                raise LoopbackAcceptanceError("production reading snapshot has no opaque audio_ref")
            if self.await_playback and self._awaiting_generation is not None:
                raise LoopbackAcceptanceError("next reading snapshot arrived before audio completion")
            if self.delegate.reading_document_id is None or self.delegate.saved_datapack_id is None:
                raise LoopbackAcceptanceError("reading snapshot arrived before save/read transition")
            if record.get("datapack_id") != self.delegate.confirmed_datapack_id:
                raise LoopbackAcceptanceError("reading snapshot datapack lineage mismatch")
            position = _reading_position(cursor.get("page_id"))
            focus_id = cursor.get("focus_item_id")
            commands = self._advance_reading(
                position,
                str(focus_id) if isinstance(focus_id, str) else "",
                bool(cells),
            )
            self.reading_snapshots.append(dict(record))
            if not self.await_playback:
                return commands
            self._pending_commands = commands
            self._awaiting_generation = generation
            return ()

        commands = self.delegate.handle(record)
        if record_type != "feedback":
            return commands
        code = record.get("code")
        details_value = record.get("details")
        details = details_value if isinstance(details_value, Mapping) else {}
        if code == "reading_audio_failed":
            raise LoopbackAcceptanceError(
                f"production reading audio failed: {details.get('error_class', 'unknown')}"
            )
        if code != "reading_audio_playback_completed":
            return commands
        generation = details.get("generation")
        if generation != self._awaiting_generation:
            raise LoopbackAcceptanceError("playback completion generation mismatch")
        self.playback_generations.append(generation)
        self._awaiting_generation = None
        pending = self._pending_commands
        self._pending_commands = ()
        return (*commands, *pending)

    @property
    def complete(self) -> bool:
        return (
            self.reverse_verified
            and (not self.await_playback or self._awaiting_generation is None)
            and (
                not self.await_playback
                or len(self.playback_generations) == len(self.reading_snapshots)
            )
        )

    @property
    def page_change_spread_ids(self) -> list[str]:
        return self.delegate.page_change_spread_ids

    def assert_complete(self) -> None:
        if self.delegate._awaiting_page_change_start is not None:
            raise LoopbackAcceptanceError("page-change start remained pending")
        if not self.delegate.selection_requested or self.delegate.scan_datapack_id is None:
            raise LoopbackAcceptanceError("new datapack scan was not started")
        if not self.delegate.seal_requested or self.delegate.saved_revision != 1:
            raise LoopbackAcceptanceError("scan was not sealed and saved at revision 1")
        if self.reading_positions != list(_EXPECTED_POSITIONS):
            raise LoopbackAcceptanceError("four ordered production pages were not observed")
        if not self.complete:
            raise LoopbackAcceptanceError("production reading/audio sequence was incomplete")

    def _advance_reading(
        self,
        position: tuple[str, str],
        focus_id: str,
        has_braille: bool,
    ) -> tuple[str, ...]:
        if self.reverse_verified:
            return ()
        expected = _EXPECTED_POSITIONS[self.navigation_index]
        if self.navigation_index < len(_EXPECTED_POSITIONS) - 1:
            if position == expected:
                if not self.reading_positions or self.reading_positions[-1] != position:
                    self.reading_positions.append(position)
                return self._seek_or_leave_page(position, focus_id, has_braille)
            next_position = _EXPECTED_POSITIONS[self.navigation_index + 1]
            if position != next_position:
                raise LoopbackAcceptanceError(
                    f"production navigation skipped page: expected {expected} or {next_position}, got {position}"
                )
            self.navigation_index += 1
            self.reading_positions.append(position)
            return self._seek_or_leave_page(position, focus_id, has_braille)
        if position == expected:
            if not self.reading_positions or self.reading_positions[-1] != position:
                self.reading_positions.append(position)
            return self._seek_or_leave_page(position, focus_id, has_braille)
        previous = _EXPECTED_POSITIONS[2]
        if position != previous:
            raise LoopbackAcceptanceError(
                f"production reverse navigation expected {expected} or {previous}, got {position}"
            )
        self.reverse_verified = True
        return ()

    def _seek_or_leave_page(
        self,
        position: tuple[str, str],
        focus_id: str,
        has_braille: bool,
    ) -> tuple[str, ...]:
        if has_braille:
            self.braille_positions.add(position)
            return ("prev",) if self.navigation_index == 3 else ("next",)
        previous_focus = self._last_focus_by_position.get(position)
        self._last_focus_by_position[position] = focus_id
        if previous_focus == focus_id:
            return ("prev",) if self.navigation_index == 3 else ("next",)
        return ("down",)


def validate_production_assets(
    prepared_root: str | Path,
    *,
    model_home: str | Path,
    piper_model: str | Path,
    espeak_data: str | Path,
) -> ProductionAssets:
    prepared = validate_prepared_root(prepared_root)
    home = Path(model_home).resolve()
    model = Path(piper_model).resolve()
    config = model.with_suffix(model.suffix + ".json")
    espeak = Path(espeak_data).resolve()
    missing = [
        str(path)
        for path in (home, model, config, espeak)
        if not (path.is_dir() if path in (home, espeak) else path.is_file())
    ]
    if missing:
        raise LoopbackAcceptanceError(f"production model assets are incomplete: {missing}")
    missing_components = [
        str(home / relative)
        for relative in _REQUIRED_VL_MODEL_DIRS
        if not (home / relative).is_dir() or not any((home / relative).rglob("*"))
    ]
    if missing_components:
        raise LoopbackAcceptanceError(
            f"PaddleOCR-VL production components are incomplete: {missing_components}"
        )
    model_digest, model_count = _tree_digest(home)
    if model_count == 0:
        raise LoopbackAcceptanceError("PaddleOCR-VL model home contains no files")
    lowered_paths = " ".join(str(path).lower() for path in (home, model, espeak))
    if any(token in lowered_paths for token in _BANNED_PROVENANCE):
        raise LoopbackAcceptanceError("production asset path contains bench/fixture provenance")
    return ProductionAssets(
        prepared,
        home,
        model,
        config,
        espeak,
        model_digest,
        model_count,
    )


def build_model_manifest(assets: ProductionAssets) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_sha256": E0B_SOURCE_SHA256,
        "paddleocr_vl": {
            "model_home": str(assets.model_home),
            "file_count": assets.model_file_count,
            "tree_sha256": assets.model_tree_digest,
        },
        "piper": {
            "engine_id": "piper",
            "voice": assets.piper_model.stem,
            "model_sha256": _sha256_file(assets.piper_model),
            "config_sha256": _sha256_file(assets.piper_config),
            "espeak_tree_sha256": _tree_digest(assets.espeak_data)[0],
        },
    }


def analyze_production_evidence(
    database: str | Path,
    datapacks_root: str | Path,
    console_log: str | Path,
    scan_session_id: str,
    *,
    require_playback: bool,
    require_p030: bool = False,
) -> dict[str, Any]:
    db = Path(database).resolve()
    root = Path(datapacks_root).resolve()
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        scan = connection.execute(
            "SELECT datapack_id, published_revision, status FROM scan_sessions WHERE scan_session_id=?",
            (scan_session_id,),
        ).fetchone()
        if scan is None:
            raise LoopbackAcceptanceError("production scan row is missing")
        revision = connection.execute(
            """
            SELECT root_relative_path, status, manifest_sha256
              FROM datapack_revisions WHERE datapack_id=? AND revision=?
            """,
            (scan["datapack_id"], scan["published_revision"]),
        ).fetchone()
        fragments = [
            dict(row)
            for row in connection.execute(
                """
                SELECT sequence, side, page_id, status, parser_engine_json,
                       validation_json, error_code
                  FROM page_fragments WHERE scan_session_id=? ORDER BY sequence, side
                """,
                (scan_session_id,),
            )
        ]
    if scan["status"] != "sealed" or scan["published_revision"] != 1 or revision is None:
        raise LoopbackAcceptanceError("production revision was not sealed at revision 1")
    if revision["status"] != "ready":
        raise LoopbackAcceptanceError("production revision is not ready")
    revision_root = (root / revision["root_relative_path"]).resolve()
    _require_confined(revision_root, root)
    manifest = _load_object(revision_root / "manifest.json")
    document = _load_object(revision_root / "document.json")
    audio_index = _load_object(revision_root / "audio_index.json")
    if _sha256_file(revision_root / "manifest.json") != revision["manifest_sha256"]:
        raise LoopbackAcceptanceError("production manifest hash differs from the database")

    _assert_no_banned_provenance({"manifest": manifest, "document": document})
    tts = manifest.get("tts_manifest")
    if not isinstance(tts, Mapping) or tts.get("engine_id") != "piper" or tts.get("bench_only") is True:
        raise LoopbackAcceptanceError("production revision does not declare Piper TTS")
    engines = []
    for fragment in fragments:
        if fragment.get("status") != "ready":
            raise LoopbackAcceptanceError("production fragment is not ready")
        engine = _json_object(fragment.get("parser_engine_json"), "fragment parser engine")
        general = engine.get("general_ocr")
        if not isinstance(general, Mapping) or general.get("engine_id") != "paddleocr-vl":
            raise LoopbackAcceptanceError("fragment did not use production paddleocr-vl")
        if not isinstance(general.get("engine_version"), str) or not general["engine_version"]:
            raise LoopbackAcceptanceError("fragment OCR engine version is missing")
        _assert_no_banned_provenance(engine)
        engines.append(dict(general))

    pages_value = document.get("pages")
    if not isinstance(pages_value, list) or len(pages_value) != 4:
        raise LoopbackAcceptanceError("production document must contain four pages")
    page_summaries = []
    for expected, page in zip(_EXPECTED_POSITIONS, pages_value, strict=True):
        if not isinstance(page, Mapping):
            raise LoopbackAcceptanceError("production page is malformed")
        page_id = page.get("page_id")
        if not isinstance(page_id, str) or not page_id.endswith(f"-{expected[0]}-{expected[1]}"):
            raise LoopbackAcceptanceError("production page order/side lineage differs")
        items = page.get("focus_items")
        if not isinstance(items, list) or not items:
            raise LoopbackAcceptanceError("production page has no accessible items")
        texts = [
            text
            for item in items
            if isinstance(item, Mapping)
            for text in [_focus_text(item)]
            if text
        ]
        if not texts:
            raise LoopbackAcceptanceError("production page has no readable text")
        combined = "\n".join(texts)
        page_summaries.append(
            {
                "page_id": page_id,
                "focus_item_count": len(items),
                "readable_item_count": len(texts),
                "text_sha256": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
                "text_preview": combined[:160],
            }
        )

    utterances = audio_index.get("utterances")
    if not isinstance(utterances, Mapping) or not utterances:
        raise LoopbackAcceptanceError("production audio index is empty")
    p030 = _summarize_p030_page(pages_value[0], utterances)
    if require_p030 and (
        not p030["identified"] or not p030["item_audio_resources_complete"]
    ):
        raise LoopbackAcceptanceError(
            "first production left page was not a complete user-confirmed p030 reading payload"
        )
    audio_summaries = []
    for key, entry in utterances.items():
        if not isinstance(key, str) or not isinstance(entry, Mapping):
            raise LoopbackAcceptanceError("production audio index entry is malformed")
        relative = entry.get("wav")
        if not isinstance(relative, str):
            raise LoopbackAcceptanceError("production audio entry has no WAV path")
        wav_path = (revision_root / relative).resolve()
        _require_confined(wav_path, revision_root)
        stats = _wav_stats(wav_path)
        expected_hashes = manifest.get("audio_sha256")
        if not isinstance(expected_hashes, Mapping) or expected_hashes.get(Path(relative).as_posix()) != stats["sha256"]:
            raise LoopbackAcceptanceError("production audio manifest hash differs")
        if stats["peak"] <= 0 or stats["rms"] <= 0:
            raise LoopbackAcceptanceError("production Piper WAV is silent")
        audio_summaries.append({"utterance_key": key, **stats})

    records = parse_json_lines(Path(console_log).read_text(encoding="utf-8").splitlines())
    snapshots = [record for record in records if record.get("type") == "reading_snapshot"]
    first_by_position: dict[tuple[str, str], Mapping[str, Any]] = {}
    braille_by_position: dict[tuple[str, str], Mapping[str, Any]] = {}
    for snapshot in snapshots:
        cursor = snapshot.get("cursor")
        if not isinstance(cursor, Mapping):
            continue
        try:
            position = _reading_position(cursor.get("page_id"))
        except LoopbackAcceptanceError:
            continue
        first_by_position.setdefault(position, snapshot)
        cells = snapshot.get("braille_cells")
        if isinstance(cells, list) and cells:
            braille_by_position.setdefault(position, snapshot)
    first_four = [
        braille_by_position.get(position, first_by_position[position])
        for position in _EXPECTED_POSITIONS
        if position in first_by_position
    ]
    if len(first_four) != 4:
        raise LoopbackAcceptanceError("four production reading snapshots were not observed")
    braille_summaries = []
    for expected, snapshot in zip(_EXPECTED_POSITIONS, first_four, strict=True):
        cursor = snapshot.get("cursor")
        cells = snapshot.get("braille_cells")
        audio_ref = snapshot.get("audio_ref")
        if not isinstance(cursor, Mapping) or not str(cursor.get("page_id", "")).endswith(
            f"-{expected[0]}-{expected[1]}"
        ):
            raise LoopbackAcceptanceError("reading snapshot page lineage differs")
        if not isinstance(cells, list) or any(
            isinstance(cell, bool) or not isinstance(cell, int) or not 0 <= cell <= 63
            for cell in cells
        ):
            raise LoopbackAcceptanceError("reading snapshot braille is invalid")
        if not isinstance(audio_ref, str) or not audio_ref.startswith("s0-audio:"):
            raise LoopbackAcceptanceError("reading snapshot audio reference is invalid")
        braille_summaries.append(
            {
                "page_id": cursor["page_id"],
                "focus_item_id": cursor.get("focus_item_id"),
                "generation": cursor.get("generation"),
                "cell_count": len(cells),
                "nonempty": bool(cells),
                "braille_cells": list(cells),
                "audio_ref_digest": hashlib.sha256(audio_ref.encode("utf-8")).hexdigest()[:12],
            }
        )
    p030["observed_braille"] = braille_summaries[0]
    if require_p030 and (
        not braille_summaries[0]["nonempty"]
        or braille_summaries[0]["focus_item_id"] != p030["target_focus_item_id"]
    ):
        raise LoopbackAcceptanceError(
            "p030 first problem did not produce non-empty braille at the expected focus item"
        )
    codes = [record.get("code") for record in records if record.get("type") == "feedback"]
    playback_completions = codes.count("reading_audio_playback_completed")
    playback_failures = codes.count("reading_audio_failed")
    if require_playback and (playback_completions < 5 or playback_failures):
        raise LoopbackAcceptanceError("production Device playback did not complete for every navigation")
    return {
        "datapack_id": scan["datapack_id"],
        "revision": scan["published_revision"],
        "revision_root": str(revision_root),
        "ocr_engines": engines,
        "tts_manifest": dict(tts),
        "pages": page_summaries,
        "braille": braille_summaries,
        "pages_with_nonempty_braille": sum(
            1 for summary in braille_summaries if summary["nonempty"]
        ),
        "audio": audio_summaries,
        "p030": p030,
        "playback": {
            "required": require_playback,
            "completions": playback_completions,
            "failures": playback_failures,
            "cache_hits": codes.count("reading_audio_cache_hit"),
            "interruptions": codes.count("reading_audio_interrupted"),
        },
    }


def exercise_production_audio_transport(
    database: str | Path,
    datapacks_root: str | Path,
    api_key_path: str | Path,
    datapack_id: str,
    *,
    playback: bool,
    first_page_target_node_index: int = 0,
    expected_first_page_focus_id: str | None = None,
) -> dict[str, Any]:
    """Exercise authenticated S0 download/cache/playback against the saved revision."""
    from document_parser.server.s0_http import create_app
    from document_parser.server.s0_services import S0ControlPlane
    from document_parser.server.s0_store import S0Store
    from document_parser.server.system_audio import SystemAudioService
    from werkzeug.serving import make_server

    from .adapters.http_s0 import S0CatalogHttpAdapter, S0HttpClient, S0ReadingHttpAdapter
    from .adapters.reading_audio import (
        S0AudioResourceHttpAdapter,
        S0SystemAudioResourceHttpAdapter,
        SoundDeviceWavPlayer,
    )
    from .desktop_audio_transport_acceptance import _QuietRequestHandler, _request_status
    from .device_audio_playback_acceptance import _AutomatedPlayer, _CountingResource, _EventSink
    from .events import FeedbackCode, FeedbackEvent
    from .reading_audio import AudioResourceCache, ReadingAudioController
    from .types import DatapackId, DeviceControl, DeviceId, InputAction

    api_key = Path(api_key_path).read_text(encoding="utf-8").strip()
    store = S0Store(Path(database), Path(datapacks_root))
    def no_runtime_synthesis(text: str):
        raise LoopbackAcceptanceError(
            f"production system audio pool is incomplete for {text!r}"
        )

    system_audio_service = SystemAudioService(
        Path(datapacks_root), no_runtime_synthesis
    )
    control_plane = S0ControlPlane(
        store, system_audio_service=system_audio_service
    )
    app = create_app(control_plane, api_key)
    server = make_server(
        "127.0.0.1", 0, app, threaded=True, request_handler=_QuietRequestHandler
    )
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    sink = _EventSink()
    player = SoundDeviceWavPlayer() if playback else _AutomatedPlayer()
    resource = _CountingResource(S0AudioResourceHttpAdapter(base_url, api_key))
    system_resource = _CountingResource(
        S0SystemAudioResourceHttpAdapter(base_url, api_key)
    )
    cache = AudioResourceCache(max_bytes=8 * 1024 * 1024, max_entries=4)
    primary_device_id, isolation_device_id = _production_replay_device_ids()
    primary_device = DeviceId(primary_device_id)
    s0_client = S0HttpClient(base_url, api_key)
    controller = ReadingAudioController(
        resource,
        player,
        cache,
        device_id=primary_device,
        system_resource_port=system_resource,
        feedback=sink,
    )
    reading = S0ReadingHttpAdapter(s0_client)
    catalog = S0CatalogHttpAdapter(s0_client)
    snapshots = []
    try:
        catalog_entry = next(
            entry
            for entry in catalog.list_datapacks(primary_device)
            if entry.datapack_id.value == datapack_id
        )
        if catalog_entry.title_audio_ref is None:
            raise LoopbackAcceptanceError(
                "production catalog title has no Piper audio reference"
            )
        controller.emit(
            FeedbackEvent(
                FeedbackCode.SCREEN_CHANGED,
                time.monotonic(),
                (("screen", "datapack_selection"), ("mode", "reading")),
            )
        )
        controller.emit(
            FeedbackEvent(
                FeedbackCode.SPEAK_CATALOG_TITLE,
                time.monotonic(),
                (
                    ("kind", "existing"),
                    ("title_audio_ref", catalog_entry.title_audio_ref),
                ),
            )
        )
        if not controller.wait_idle(180):
            raise LoopbackAcceptanceError("production system audio did not settle")
        current = reading.open(
            primary_device,
            DatapackId(datapack_id),
            20,
            f"open-{uuid.uuid4().hex}",
        )
        for target_step in range(first_page_target_node_index):
            current = reading.send_command(
                current.reading_session_id,
                f"p030-target-{target_step}-{uuid.uuid4().hex}",
                DeviceControl.DOWN,
                InputAction.SHORT,
            )
        target_cursor = dict(current.cursor)
        if expected_first_page_focus_id is not None and target_cursor.get(
            "focus_item_id"
        ) != expected_first_page_focus_id:
            raise LoopbackAcceptanceError("p030 audio target focus lineage differs")
        if not current.braille_cells:
            raise LoopbackAcceptanceError("p030 audio target returned empty braille cells")
        for page_index in range(4):
            snapshots.append(current)
            controller.present(current)
            if not controller.wait_idle(180):
                raise LoopbackAcceptanceError(
                    f"production page {page_index + 1} audio did not settle"
                )
            if page_index < 3:
                controller.interrupt()
                current = reading.send_command(
                    current.reading_session_id,
                    f"page-{page_index + 2}-{uuid.uuid4().hex}",
                    DeviceControl.PAGE_NEXT,
                    InputAction.SHORT,
                )

        first = snapshots[0]
        other = reading.open(
            DeviceId(isolation_device_id),
            DatapackId(datapack_id),
            20,
            f"other-{uuid.uuid4().hex}",
        )
        audio_id = first.audio_ref.removeprefix("s0-audio:")
        resource_url = (
            f"{base_url}/api/v1/reading-sessions/{first.reading_session_id}/audio/{audio_id}"
        )
        unauthorized = _request_status(resource_url, None)
        wrong_session = _request_status(
            f"{base_url}/api/v1/reading-sessions/{other.reading_session_id}/audio/{audio_id}",
            api_key,
        )
        system_audio_id = catalog_entry.title_audio_ref.removeprefix(
            "s0-system-audio:"
        )
        system_unauthorized = _request_status(
            f"{base_url}/api/v1/devices/{primary_device_id}/system-audio/{system_audio_id}",
            None,
        )
        system_cross_device = _request_status(
            f"{base_url}/api/v1/devices/{isolation_device_id}/system-audio/{system_audio_id}",
            api_key,
        )

        controller.interrupt()
        current = reading.send_command(
            current.reading_session_id,
            f"revisit-{uuid.uuid4().hex}",
            DeviceControl.PAGE_PREVIOUS,
            InputAction.SHORT,
        )
        controller.present(current)
        if not controller.wait_idle(180):
            raise LoopbackAcceptanceError("production cache revisit did not settle")

        controller.interrupt()
        current = reading.send_command(
            current.reading_session_id,
            f"rapid-next-{uuid.uuid4().hex}",
            DeviceControl.PAGE_NEXT,
            InputAction.SHORT,
        )
        controller.present(current)
        time.sleep(0.10 if playback else 0.01)
        controller.interrupt()
        current = reading.send_command(
            current.reading_session_id,
            f"rapid-prev-{uuid.uuid4().hex}",
            DeviceControl.PAGE_PREVIOUS,
            InputAction.SHORT,
        )
        controller.present(current)
        if not controller.wait_idle(180):
            raise LoopbackAcceptanceError("production latest-generation audio did not settle")

        codes = [event.code.value for event in sink.events]
        result = {
            "authenticated": True,
            "unauthorized_request_rejected": unauthorized == 401,
            "cross_session_request_rejected": wrong_session == 404,
            "system_audio_unauthorized_rejected": system_unauthorized == 401,
            "system_audio_cross_device_rejected": system_cross_device == 404,
            "system_audio_fetch_count": system_resource.fetches,
            "pages_presented": 4,
            "fetch_count": resource.fetches,
            "cache_hits": codes.count("reading_audio_cache_hit"),
            "playback_starts": codes.count("reading_audio_playback_started"),
            "playback_completions": codes.count("reading_audio_playback_completed"),
            "interruptions": codes.count("reading_audio_interrupted"),
            "failures": codes.count("reading_audio_failed"),
            "cache_entries": cache.entry_count,
            "cache_bytes": cache.total_bytes,
            "cache_limit_entries": cache.max_entries,
            "cache_limit_bytes": cache.max_bytes,
            "client_wav_persisted": False,
            "p030_target": {
                "page_id": target_cursor.get("page_id"),
                "focus_item_id": target_cursor.get("focus_item_id"),
                "node_index": target_cursor.get("node_index"),
                "braille_cells": list(snapshots[0].braille_cells),
                "braille_cell_count": len(snapshots[0].braille_cells),
                "audio_ref_digest": hashlib.sha256(
                    str(snapshots[0].audio_ref).encode("utf-8")
                ).hexdigest()[:12],
                "playback_requested": playback,
            },
            "events": [
                {
                    "code": event.code.value,
                    "at_monotonic": event.at_monotonic,
                    "details": dict(event.details),
                }
                for event in sink.events
            ],
        }
        if (
            not result["unauthorized_request_rejected"]
            or not result["cross_session_request_rejected"]
            or not result["system_audio_unauthorized_rejected"]
            or not result["system_audio_cross_device_rejected"]
            or result["failures"]
            or result["cache_entries"] > result["cache_limit_entries"]
            or result["cache_bytes"] > result["cache_limit_bytes"]
        ):
            raise LoopbackAcceptanceError("production audio transport invariants failed")
        return result
    finally:
        controller.close()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


def run_production_full_model_acceptance(
    prepared_root: str | Path,
    *,
    model_home: str | Path,
    piper_model: str | Path = _DEFAULT_PIPER_MODEL,
    espeak_data: str | Path = _DEFAULT_ESPEAK_DATA,
    evidence_dir: str | Path | None = None,
    work_dir: str | Path | None = None,
    server_python: str | Path,
    device_python: str | Path,
    device: str = "gpu:0",
    piper_use_cuda: bool = False,
    playback: bool = True,
    timeout_seconds: float = 3600.0,
    idle_timeout_seconds: float = 600.0,
    prompt=input,
) -> dict[str, Any]:
    assets = validate_production_assets(
        prepared_root,
        model_home=model_home,
        piper_model=piper_model,
        espeak_data=espeak_data,
    )
    repository = Path(__file__).resolve().parents[3]
    run_id = _run_id()
    evidence = (
        Path(evidence_dir).resolve()
        if evidence_dir is not None
        else repository / "tmp" / "e0b-production-runs" / run_id / "evidence"
    )
    work = (
        Path(work_dir).resolve()
        if work_dir is not None
        else repository / "tmp" / "e0b-production-runs" / run_id / "work"
    )
    model_manifest = build_model_manifest(assets)

    def server_command(port: int, server_state: Path, prepared: PreparedInputs) -> tuple[str, ...]:
        command = [
            "-m",
            "document_parser.server.combined_server",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--api-key-file",
            str(prepared.api_key_path),
            "--datapacks-dir",
            str(server_state / "datapacks"),
            "--jobs-dir",
            str(server_state / "jobs"),
            "--state-db",
            str(server_state / "server.sqlite3"),
            "--model-home",
            str(assets.model_home),
            "--device",
            device,
            "--piper-model",
            str(assets.piper_model),
            "--piper-espeak-data",
            str(assets.espeak_data),
        ]
        if piper_use_cuda:
            command.append("--piper-use-cuda")
        return tuple(command)

    controller = ProductionLoopbackController(await_playback=False)
    failure: str | None = None
    acceptance_failures: list[str] = []
    loopback: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    audio_transport: dict[str, Any] | None = None
    manual = {"status": "not_run", "checks": {}}
    try:
        loopback = run_desktop_loopback_acceptance(
            assets.prepared.root,
            evidence_dir=evidence,
            work_dir=work,
            server_python=server_python,
            device_python=device_python,
            timeout_seconds=timeout_seconds,
            idle_timeout_seconds=idle_timeout_seconds,
            server_command_builder=server_command,
            server_required_modules=("document_parser", "flask", "paddleocr", "piper"),
            controller=controller,
            reading_audio_enabled=False,
            run_kind="e0b_production_full_model_desktop_acceptance",
            environment_name="desktop_production_full_model",
            limitations=(
                "Pinned MP4 replay was used; a live camera was not exercised.",
                "STM32/bridge and Raspberry Pi hardware were not exercised.",
            ),
        )
        current_digest, current_count = _tree_digest(assets.model_home)
        if (current_digest, current_count) != (assets.model_tree_digest, assets.model_file_count):
            raise LoopbackAcceptanceError(
                "PaddleOCR-VL model home changed during acceptance; runtime download is not accepted"
            )
        analysis = analyze_production_evidence(
            work / "state" / "server" / "server.sqlite3",
            work / "state" / "server" / "datapacks",
            evidence / "e0b-replay-console.log",
            str(loopback["scan_session_id"]),
            require_playback=False,
            require_p030=True,
        )
        if analysis["pages_with_nonempty_braille"] != len(_EXPECTED_POSITIONS):
            acceptance_failures.append(
                "approved criterion requires non-empty braille on all four pages, "
                f"but observed {analysis['pages_with_nonempty_braille']}/4"
            )
        audio_transport = exercise_production_audio_transport(
            work / "state" / "server" / "server.sqlite3",
            work / "state" / "server" / "datapacks",
            assets.prepared.api_key_path,
            str(analysis["datapack_id"]),
            playback=playback,
            first_page_target_node_index=int(analysis["p030"]["target_node_index"]),
            expected_first_page_focus_id=str(analysis["p030"]["target_focus_item_id"]),
        )
        if playback:
            checks = {}
            questions = (
                ("p030_problem_heard", "30페이지 첫 문제의 Piper 한국어 음성이 들렸습니까? [yes/no]: "),
                ("content_matched", "음성이 30페이지의 지수함수 문제 내용과 일치했습니까? [yes/no]: "),
                ("not_fixture_audio", "beep/tone/SAPI가 아닌 실제 Piper 음성이었습니까? [yes/no]: "),
                ("no_stale_audio", "페이지 이동 뒤 이전 페이지 음성이 뒤늦게 재생되지 않았습니까? [yes/no]: "),
            )
            for name, question in questions:
                answer = ""
                while answer not in {"yes", "no"}:
                    answer = prompt(question).strip().lower()
                checks[name] = answer == "yes"
            manual = {"status": "passed" if all(checks.values()) else "failed", "checks": checks}
            if manual["status"] != "passed":
                raise LoopbackAcceptanceError("manual production Piper listening did not pass")
        if acceptance_failures:
            raise LoopbackAcceptanceError("; ".join(acceptance_failures))
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"

    automated_status = "passed" if failure is None and analysis is not None else "failed"
    status = (
        "passed"
        if automated_status == "passed" and manual["status"] == "passed"
        else "manual_pending"
        if automated_status == "passed" and not playback
        else "failed"
    )
    report = {
        "schema_version": 1,
        "kind": "e0b_production_full_model_desktop_acceptance",
        "status": status,
        "automated_status": automated_status,
        "manual_listening_status": manual["status"],
        "input_sha256": E0B_SOURCE_SHA256,
        "scan_session_id": loopback.get("scan_session_id") if loopback else None,
        "datapack_id": analysis.get("datapack_id") if analysis else None,
        "spread_receipts": 2 if automated_status == "passed" else None,
        "fragments": 4 if automated_status == "passed" else None,
        "duplicates": 0 if automated_status == "passed" else None,
        "page_count": len(analysis["pages"]) if analysis else None,
        "pages_with_accessible_items": len(analysis["pages"]) if analysis else None,
        "pages_with_nonempty_braille": (
            analysis["pages_with_nonempty_braille"] if analysis else None
        ),
        "ocr_engine_id": "paddleocr-vl" if analysis else None,
        "tts_engine_id": analysis["tts_manifest"].get("engine_id") if analysis else None,
        "audio_resources_verified": len(analysis["audio"]) if analysis else None,
        "audio_resources_heard": 4 if manual["status"] == "passed" else 0,
        "evidence_dir": str(evidence),
        "work_dir": str(work),
        "failure": failure,
        "acceptance_failures": acceptance_failures,
        "audio_transport": (
            {key: value for key, value in audio_transport.items() if key != "events"}
            if audio_transport
            else None
        ),
        "p030_e2e": analysis.get("p030") if analysis else None,
    }
    if evidence.is_dir():
        _write_json(evidence / "e0b-production-model-manifest.json", model_manifest)
        _write_json(evidence / "e0b-manual-listening.json", manual)
        if analysis is not None:
            _write_json(evidence / "e0b-page-content-summary.json", {"pages": analysis["pages"]})
            _write_json(evidence / "e0b-braille-summary.json", {"snapshots": analysis["braille"]})
            _write_json(evidence / "e0b-p030-e2e-summary.json", analysis["p030"])
            _write_json(
                evidence / "e0b-audio-summary.json",
                {"resources": analysis["audio"], "playback": analysis["playback"]},
            )
        if audio_transport is not None:
            _write_json(
                evidence / "e0b-production-audio-transport.json",
                {key: value for key, value in audio_transport.items() if key != "events"},
            )
            (evidence / "e0b-production-audio-events.jsonl").write_text(
                "".join(
                    json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
                    for event in audio_transport["events"]
                ),
                encoding="utf-8",
            )
        _write_json(evidence / "e0b-production-full-model-report.json", report)
    if failure is not None:
        raise LoopbackAcceptanceError(json.dumps(report, ensure_ascii=False))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared_root", type=Path)
    parser.add_argument("--model-home", type=Path)
    parser.add_argument(
        "--piper-model",
        type=Path,
        default=Path(os.environ.get("E0B_PIPER_MODEL", _DEFAULT_PIPER_MODEL)),
    )
    parser.add_argument(
        "--piper-espeak-data",
        type=Path,
        default=Path(os.environ.get("E0B_PIPER_ESPEAK_DATA", _DEFAULT_ESPEAK_DATA)),
    )
    parser.add_argument("--server-python", type=Path, required=True)
    parser.add_argument("--device-python", type=Path, required=True)
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--piper-use-cuda", action="store_true")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    parser.add_argument("--idle-timeout-seconds", type=float, default=600.0)
    parser.add_argument("--no-playback", action="store_true")
    args = parser.parse_args(argv)
    model_home = args.model_home or args.prepared_root / "models" / "paddleocr-vl"
    try:
        report = run_production_full_model_acceptance(
            args.prepared_root,
            model_home=model_home,
            piper_model=args.piper_model,
            espeak_data=args.piper_espeak_data,
            evidence_dir=args.evidence_dir,
            work_dir=args.work_dir,
            server_python=args.server_python,
            device_python=args.device_python,
            device=args.device,
            piper_use_cuda=args.piper_use_cuda,
            playback=not args.no_playback,
            timeout_seconds=args.timeout_seconds,
            idle_timeout_seconds=args.idle_timeout_seconds,
        )
    except (LoopbackAcceptanceError, OSError, ValueError, RuntimeError) as exc:
        print(f"[E0-B.5-D] FAILED: {exc}", flush=True)
        return 1
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0 if report["status"] in {"passed", "manual_pending"} else 1


def _focus_text(item: Mapping[str, Any]) -> str:
    from document_parser.accessibility.speech import focus_item_announcement

    spoken = focus_item_announcement(dict(item))
    return spoken.strip() if isinstance(spoken, str) else ""


def _production_replay_device_ids() -> tuple[str, str]:
    replay_identity = uuid.uuid4().hex
    return (
        f"desktop-production-audio-{replay_identity}",
        f"desktop-production-audio-other-{replay_identity}",
    )


def _summarize_p030_page(
    page: object,
    utterances: Mapping[str, object],
) -> dict[str, Any]:
    if not isinstance(page, Mapping):
        raise LoopbackAcceptanceError("p030 page is malformed")
    items_value = page.get("focus_items")
    if not isinstance(items_value, list):
        raise LoopbackAcceptanceError("p030 page has no focus items")
    items = [item for item in items_value if isinstance(item, Mapping)]
    texts = [_focus_text(item) for item in items]
    target_index = next(
        (index for index, text in enumerate(texts) if "지수함수" in text),
        None,
    )
    exact_footer = any(text.strip() == "30" for text in texts)
    codes = sorted(
        set(
            match
            for text in texts
            for match in re.findall(r"26008-00(?:42|43|44|45)", text)
        )
    )
    focus_ids = [str(item.get("id", "")) for item in items]
    missing_audio = [item_id for item_id in focus_ids if item_id not in utterances]
    target_id = focus_ids[target_index] if target_index is not None else None
    return {
        "source_provenance": "pinned_mp4_user_confirmed_p030_left_spread",
        "identified": exact_footer and target_index is not None,
        "page_id": page.get("page_id"),
        "printed_page_footer_exact": exact_footer,
        "problem_codes_found": codes,
        "focus_item_count": len(items),
        "item_audio_resources_present": len(focus_ids) - len(missing_audio),
        "item_audio_resources_complete": not missing_audio,
        "missing_item_audio_focus_ids": missing_audio,
        "target_node_index": target_index,
        "target_focus_item_id": target_id,
        "target_text_preview": texts[target_index][:200] if target_index is not None else None,
    }


def _reading_position(value: object) -> tuple[str, str]:
    if not isinstance(value, str):
        raise LoopbackAcceptanceError("production reading page id is missing")
    match = re.search(r"-([0-9]{8})-(L|R)$", value)
    if match is None:
        raise LoopbackAcceptanceError(f"unexpected production reading page id: {value}")
    return match.group(1), match.group(2)


def _wav_stats(path: Path) -> dict[str, Any]:
    try:
        with wave.open(str(path), "rb") as source:
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            sample_rate = source.getframerate()
            frames = source.getnframes()
            payload = source.readframes(frames)
    except (OSError, EOFError, wave.Error) as exc:
        raise LoopbackAcceptanceError(f"invalid production WAV: {path.name}") from exc
    if sample_width != 2 or channels not in {1, 2} or sample_rate <= 0 or frames <= 0:
        raise LoopbackAcceptanceError(f"unsupported production WAV format: {path.name}")
    samples = array("h")
    samples.frombytes(payload)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max((abs(value) for value in samples), default=0)
    rms = math.sqrt(sum(value * value for value in samples) / len(samples)) if samples else 0.0
    return {
        "sha256": _sha256_file(path),
        "content_length": path.stat().st_size,
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "duration_ms": round(frames * 1000 / sample_rate),
        "peak": peak,
        "rms": round(rms, 3),
    }


def _assert_no_banned_provenance(value: object) -> None:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    found = [token for token in _BANNED_PROVENANCE if token in serialized]
    if found:
        raise LoopbackAcceptanceError(f"bench/fixture provenance found: {found}")


def _json_object(value: object, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        raise LoopbackAcceptanceError(f"{label} is invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise LoopbackAcceptanceError(f"{label} is not an object")
    return parsed


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LoopbackAcceptanceError(f"cannot read production JSON: {path}") from exc
    if not isinstance(value, dict):
        raise LoopbackAcceptanceError(f"production JSON root is not an object: {path}")
    return value


def _tree_digest(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\n")
        count += 1
    return digest.hexdigest(), count


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_confined(path: Path, root: Path) -> None:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise LoopbackAcceptanceError("production evidence path escapes its root")


def _run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("e0b-production-full-model-%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


if __name__ == "__main__":
    raise SystemExit(main())
