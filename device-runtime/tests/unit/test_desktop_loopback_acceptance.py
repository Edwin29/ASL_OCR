from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from asl_device.app_config import DeviceAppConfig
from asl_device.desktop_loopback_acceptance import (
    LoopbackAcceptanceError,
    LoopbackController,
    PreparedInputs,
    _paths_overlap,
    _scan_session_id,
    _server_evidence_complete,
    _write_json,
    extract_server_evidence,
    write_loopback_config,
)


def _feedback(code: str, **details: object) -> dict[str, object]:
    return {"type": "feedback", "code": code, "details": details}


def _snapshot(datapack_id: str, page_id: str) -> dict[str, object]:
    return {
        "type": "reading_snapshot",
        "datapack_id": datapack_id,
        "cursor": {"page_id": page_id},
    }


def test_controller_drives_complete_fresh_loopback_lifecycle() -> None:
    controller = LoopbackController()
    datapack_id = "datapack-fresh"
    scan_id = "scan-" + "a" * 32

    assert controller.handle(_feedback("speak_catalog_title", kind="new_datapack")) == (
        "confirm",
    )
    assert controller.handle(_feedback("confirm_selection", datapack_id=datapack_id)) == ()
    assert controller.handle(_feedback("scan_started", datapack_id=datapack_id)) == ()

    for sequence in (1, 2):
        assert controller.handle(_feedback("spread_sent", sequence=sequence)) == ()
        assert controller.handle(
            _feedback(
                "identity_collection_started",
                identity_role="page_change",
                spread_id=f"{scan_id}-spread-{sequence:06d}",
            )
        ) == ()

    assert controller.handle(
        _feedback("scan_input_exhausted", queued_count=2, acked_count=2)
    ) == ("confirm",)
    assert controller.handle(
        _feedback("datapack_saved", datapack_id=datapack_id, revision=1)
    ) == ()
    assert controller.handle(_feedback("reading_resumed", document_id=datapack_id)) == ()

    assert controller.handle(_snapshot(datapack_id, "pg-x-00000001-L")) == ("down",)
    assert controller.handle(_snapshot(datapack_id, "pg-x-00000001-R")) == ("down",)
    assert controller.handle(_snapshot(datapack_id, "pg-x-00000002-L")) == ("down",)
    assert controller.handle(_snapshot(datapack_id, "pg-x-00000002-R")) == ("up",)
    assert controller.handle(_snapshot(datapack_id, "pg-x-00000002-L")) == ()

    controller.assert_complete()
    assert controller.complete
    assert controller.page_change_spread_ids == [
        f"{scan_id}-spread-000001",
        f"{scan_id}-spread-000002",
    ]


def test_controller_refuses_missing_ack_callback_start() -> None:
    controller = LoopbackController()
    controller.handle(_feedback("spread_sent", sequence=1))

    with pytest.raises(LoopbackAcceptanceError, match="not followed"):
        controller.handle(_feedback("scanner_guidance", guidance_code="content_occluded"))


def test_controller_does_not_seal_unacked_or_partial_replay() -> None:
    controller = LoopbackController(
        spread_sequences=[1],
        page_change_spread_ids=["scan-" + "b" * 32 + "-spread-000001"],
    )

    with pytest.raises(LoopbackAcceptanceError, match="unexpected spread sequence"):
        controller.handle(
            _feedback("scan_input_exhausted", queued_count=1, acked_count=1)
        )

    assert not controller.seal_requested


def test_loopback_config_is_isolated_and_keeps_secret_out_of_evidence(tmp_path: Path) -> None:
    prepared_root = tmp_path / "prepared"
    models = prepared_root / "models"
    video = prepared_root / "inputs" / "scanner-replay.mp4"
    source_report = prepared_root / "reports" / "e0b-replay-input.json"
    secret = prepared_root / "secrets" / "device-api-key.txt"
    for path in (video, source_report, secret):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    prepared = PreparedInputs(
        prepared_root,
        video,
        source_report,
        {"status": "passed"},
        models,
        secret,
    )
    work = tmp_path / "work"
    config_path = write_loopback_config(
        work,
        prepared,
        port=18421,
        device_id="desktop-loopback-test",
    )

    config = DeviceAppConfig.from_toml(config_path)

    assert config.connectivity.server_base_url == "http://127.0.0.1:18421"
    assert config.connectivity.allow_insecure_http is True
    assert config.delivery.outbox_db_path == (work / "state/device/delivery.sqlite3").resolve()
    assert config.scanner.replay_path == video.resolve()
    assert config.scanner.sample_interval_ms == 100
    assert config.connectivity.api_key_file == (work / "secrets/device-api-key.txt").resolve()
    assert "fixture" not in config_path.read_text(encoding="utf-8")


def test_extract_server_evidence_reports_exact_two_four_zero(tmp_path: Path) -> None:
    database = tmp_path / "server.sqlite3"
    scan_id = "scan-" + "c" * 32
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE scan_spreads (
            scan_session_id TEXT, sequence INTEGER, spread_id TEXT,
            source_frame_id TEXT, receipt_id TEXT, status TEXT
        );
        CREATE TABLE page_fragments (
            scan_session_id TEXT, sequence INTEGER, side TEXT,
            page_id TEXT, status TEXT
        );
        CREATE TABLE spread_upload_attempts (
            scan_session_id TEXT, sequence INTEGER, status TEXT,
            attempt_count INTEGER, s1_receipt_id TEXT, created_at TEXT
        );
        """
    )
    for sequence in (1, 2):
        connection.execute(
            "INSERT INTO scan_spreads VALUES (?, ?, ?, ?, ?, ?)",
            (
                scan_id,
                sequence,
                f"{scan_id}-spread-{sequence:06d}",
                f"video-{sequence:08d}",
                f"receipt-{sequence}",
                "ready",
            ),
        )
        for side in ("left", "right"):
            connection.execute(
                "INSERT INTO page_fragments VALUES (?, ?, ?, ?, ?)",
                (scan_id, sequence, side, f"page-{sequence}-{side}", "ready"),
            )
        connection.execute(
            "INSERT INTO spread_upload_attempts VALUES (?, ?, ?, ?, ?, ?)",
            (scan_id, sequence, "accepted", 1, f"receipt-{sequence}", f"t{sequence}"),
        )
    connection.commit()
    connection.close()

    evidence = extract_server_evidence(database, scan_id)

    assert evidence["summary"] == {
        "spread_receipts": 2,
        "fragments": 4,
        "duplicates": 0,
    }
    assert len(evidence["spreads"]) == 2
    assert len(evidence["fragments"]) == 4
    assert len(evidence["upload_attempts"]) == 2
    assert _server_evidence_complete(evidence)
    assert json.dumps(evidence)


def test_scan_session_id_requires_one_valid_lineage() -> None:
    scan_id = "scan-" + "d" * 32

    assert _scan_session_id(
        [f"{scan_id}-spread-000001", f"{scan_id}-spread-000002"]
    ) == scan_id

    with pytest.raises(LoopbackAcceptanceError, match="crossed scan sessions"):
        _scan_session_id(
            [
                f"{scan_id}-spread-000001",
                f"scan-{'e' * 32}-spread-000002",
            ]
        )


def test_work_and_evidence_paths_must_be_disjoint(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"

    assert _paths_overlap(evidence, evidence / "work")
    assert _paths_overlap(evidence / "nested", evidence)
    assert not _paths_overlap(evidence, tmp_path / "work")


def test_json_evidence_is_utf8_without_bom(tmp_path: Path) -> None:
    output = tmp_path / "evidence.json"

    _write_json(output, {"message": "한글"})

    raw = output.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert json.loads(raw.decode("utf-8")) == {"message": "한글"}
