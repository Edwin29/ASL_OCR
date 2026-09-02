from __future__ import annotations

import hashlib
import json
import sqlite3
import wave
from pathlib import Path

import pytest

from asl_device.desktop_loopback_acceptance import LoopbackAcceptanceError
from asl_device.production_full_model_acceptance import (
    ProductionLoopbackController,
    _production_replay_device_ids,
    _summarize_p030_page,
    analyze_production_evidence,
)


def _feedback(code: str, **details: object) -> dict[str, object]:
    return {"type": "feedback", "code": code, "details": details}


def _snapshot(datapack_id: str, page_id: str, generation: int) -> dict[str, object]:
    return {
        "type": "reading_snapshot",
        "datapack_id": datapack_id,
        "cursor": {"page_id": page_id, "generation": generation},
        "braille_cells": [1, 3, 63],
        "audio_ref": f"s0-audio:{generation:032x}",
    }


def test_production_controller_waits_for_each_audio_completion() -> None:
    controller = ProductionLoopbackController()
    datapack_id = "datapack-production"
    scan_id = "scan-" + "a" * 32

    assert controller.handle(_feedback("speak_catalog_title", kind="new_datapack")) == ("confirm",)
    controller.handle(_feedback("confirm_selection", datapack_id=datapack_id))
    controller.handle(_feedback("scan_started", datapack_id=datapack_id))
    for sequence in (1, 2):
        controller.handle(_feedback("spread_sent", sequence=sequence))
        controller.handle(
            _feedback(
                "identity_collection_started",
                identity_role="page_change",
                spread_id=f"{scan_id}-spread-{sequence:06d}",
            )
        )
    assert controller.handle(
        _feedback("scan_input_exhausted", queued_count=2, acked_count=2)
    ) == ("confirm",)
    controller.handle(_feedback("datapack_saved", datapack_id=datapack_id, revision=1))
    controller.handle(_feedback("reading_resumed", document_id=datapack_id))

    positions = ("00000001-L", "00000001-R", "00000002-L", "00000002-R", "00000002-L")
    expected_commands = ("next", "next", "next", "prev", None)
    for generation, (position, expected) in enumerate(zip(positions, expected_commands, strict=True)):
        assert controller.handle(
            _snapshot(datapack_id, f"pg-test-{position}", generation)
        ) == ()
        commands = controller.handle(
            _feedback("reading_audio_playback_completed", generation=generation)
        )
        assert commands == (() if expected is None else (expected,))

    controller.assert_complete()
    assert controller.complete


def test_production_controller_retains_plain_text_clear_frame() -> None:
    controller = ProductionLoopbackController(await_playback=False)
    controller.delegate.confirmed_datapack_id = "datapack-production"
    controller.delegate.reading_document_id = "datapack-production"
    controller.delegate.saved_datapack_id = "datapack-production"
    snapshot = _snapshot("datapack-production", "pg-test-00000001-L", 0)
    snapshot["braille_cells"] = []

    assert controller.handle(snapshot) == ("down",)
    assert controller.reading_snapshots[0]["braille_cells"] == []


def test_production_controller_seeks_braille_within_page() -> None:
    controller = ProductionLoopbackController(await_playback=False)
    controller.delegate.confirmed_datapack_id = "datapack-production"
    controller.delegate.reading_document_id = "datapack-production"
    controller.delegate.saved_datapack_id = "datapack-production"

    first = _snapshot("datapack-production", "pg-test-00000001-L", 0)
    first["cursor"]["focus_item_id"] = "text-1"
    first["braille_cells"] = []
    second = _snapshot("datapack-production", "pg-test-00000001-L", 1)
    second["cursor"]["focus_item_id"] = "text-2"
    second["braille_cells"] = []
    math = _snapshot("datapack-production", "pg-test-00000001-L", 2)
    math["cursor"]["focus_item_id"] = "math-1"

    assert controller.handle(first) == ("down",)
    assert controller.handle(second) == ("down",)
    assert controller.handle(math) == ("next",)
    assert controller.braille_positions == {("00000001", "L")}


def test_production_controller_rejects_invalid_braille() -> None:
    controller = ProductionLoopbackController(await_playback=False)
    controller.delegate.confirmed_datapack_id = "datapack-production"
    controller.delegate.reading_document_id = "datapack-production"
    controller.delegate.saved_datapack_id = "datapack-production"
    snapshot = _snapshot("datapack-production", "pg-test-00000001-L", 0)
    snapshot["braille_cells"] = [64]

    with pytest.raises(LoopbackAcceptanceError, match="invalid six-dot cells"):
        controller.handle(snapshot)


def test_analyze_production_evidence_accepts_real_provenance(tmp_path: Path) -> None:
    db, datapacks, log, scan_id = _production_fixture(tmp_path)

    result = analyze_production_evidence(
        db, datapacks, log, scan_id, require_playback=True
    )

    assert result["revision"] == 1
    assert len(result["pages"]) == 4
    assert len(result["braille"]) == 4
    assert result["pages_with_nonempty_braille"] == 4
    assert result["tts_manifest"]["engine_id"] == "piper"
    assert result["audio"][0]["peak"] > 0
    assert result["playback"]["completions"] == 5


def test_analyze_production_evidence_rejects_bench_provenance(tmp_path: Path) -> None:
    db, datapacks, log, scan_id = _production_fixture(tmp_path)
    revision = next((datapacks / "revisions").iterdir())
    document = json.loads((revision / "document.json").read_text(encoding="utf-8"))
    document["pages"][0]["focus_items"][0]["spans"][0]["text"] = "remote bench content"
    (revision / "document.json").write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(LoopbackAcceptanceError, match="bench/fixture provenance"):
        analyze_production_evidence(db, datapacks, log, scan_id, require_playback=True)


def test_p030_summary_selects_problem_audio_and_not_only_page_header() -> None:
    page = {
        "page_id": "pg-test-00000001-L",
        "focus_items": [
            {"id": "header", "kind": "TEXT", "spans": [{"kind": "TEXT", "text": "기초 연습"}]},
            {
                "id": "problem-1",
                "kind": "TEXT",
                "spans": [
                    {"kind": "TEXT", "text": "1 지수함수 "},
                    {"kind": "MATH", "text": "f(x)=2^{-x}", "ast_status": "VALID"},
                ],
            },
            {"id": "footer", "kind": "TEXT", "spans": [{"kind": "TEXT", "text": "30"}]},
        ],
    }

    result = _summarize_p030_page(
        page,
        {"header": {}, "problem-1": {}, "footer": {}},
    )

    assert result["identified"] is True
    assert result["target_node_index"] == 1
    assert result["target_focus_item_id"] == "problem-1"
    assert result["item_audio_resources_complete"] is True


def test_audio_transport_uses_run_unique_device_identity() -> None:
    first = _production_replay_device_ids()
    second = _production_replay_device_ids()

    assert first[0].startswith("desktop-production-audio-")
    assert first[1].startswith("desktop-production-audio-other-")
    assert first[0] != first[1]
    assert set(first).isdisjoint(second)


def _production_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    scan_id = "scan-" + "b" * 32
    datapack_id = "datapack-production"
    datapacks = tmp_path / "datapacks"
    revision = datapacks / "revisions" / "r1"
    revision.mkdir(parents=True)
    pages = []
    positions = ("00000001-L", "00000001-R", "00000002-L", "00000002-R")
    for index, position in enumerate(positions):
        page_id = f"pg-test-{position}"
        pages.append(
            {
                "page_id": page_id,
                "focus_items": [
                    {
                        "id": f"item-{index}",
                        "kind": "TEXT",
                        "page_id": page_id,
                        "spans": [{"kind": "TEXT", "text": f"실제 내용 {index}"}],
                    }
                ],
            }
        )
    audio_path = revision / "audio" / "item.wav"
    audio_path.parent.mkdir()
    with wave.open(str(audio_path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes((b"\x10\x00\xf0\xff") * 800)
    audio_hash = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    manifest = {
        "tts_manifest": {"engine_id": "piper", "voice": "ko_KR-kss-medium"},
        "audio_sha256": {"audio/item.wav": audio_hash},
    }
    document = {"document_id": datapack_id, "pages": pages}
    audio_index = {
        "schema_version": 1,
        "utterances": {
            "item": {
                "text": "실제 내용",
                "wav": "audio/item.wav",
                "duration_ms": 100,
                "sample_rate": 16000,
            }
        },
    }
    for name, value in (
        ("manifest.json", manifest),
        ("document.json", document),
        ("audio_index.json", audio_index),
    ):
        (revision / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    manifest_hash = hashlib.sha256((revision / "manifest.json").read_bytes()).hexdigest()

    db = tmp_path / "server.sqlite3"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE scan_sessions (
            scan_session_id TEXT, datapack_id TEXT, published_revision INTEGER, status TEXT
        );
        CREATE TABLE datapack_revisions (
            datapack_id TEXT, revision INTEGER, root_relative_path TEXT,
            status TEXT, manifest_sha256 TEXT
        );
        CREATE TABLE page_fragments (
            scan_session_id TEXT, sequence INTEGER, side TEXT, page_id TEXT,
            status TEXT, parser_engine_json TEXT, validation_json TEXT, error_code TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO scan_sessions VALUES (?, ?, 1, 'sealed')", (scan_id, datapack_id)
    )
    connection.execute(
        "INSERT INTO datapack_revisions VALUES (?, 1, ?, 'ready', ?)",
        (datapack_id, "revisions/r1", manifest_hash),
    )
    engine = json.dumps(
        {
            "general_ocr": {
                "engine_id": "paddleocr-vl",
                "engine_version": "3.7.0",
            },
            "pipeline": {"mode": "incremental_paddleocr_vl"},
        }
    )
    for index, position in enumerate(positions):
        side = "left" if position.endswith("-L") else "right"
        connection.execute(
            "INSERT INTO page_fragments VALUES (?, ?, ?, ?, 'ready', ?, '{}', NULL)",
            (scan_id, index // 2 + 1, side, f"pg-test-{position}", engine),
        )
    connection.commit()
    connection.close()

    log = tmp_path / "console.log"
    records = []
    for generation, position in enumerate((*positions, "00000002-L")):
        records.append(_snapshot(datapack_id, f"pg-test-{position}", generation))
        records.append(_feedback("reading_audio_playback_completed", generation=generation))
    log.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    return db, datapacks, log, scan_id
