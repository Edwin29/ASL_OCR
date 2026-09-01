from __future__ import annotations

import json

from asl_device.replay_boundary_report import E0B_SOURCE_SHA256, build_report, parse_json_lines


def _feedback(code: str, **details):
    return {"type": "feedback", "code": code, "details": details}


def _reading(datapack_id: str, page_id: str):
    return {
        "type": "reading_snapshot",
        "datapack_id": datapack_id,
        "cursor": {"document_id": datapack_id, "page_id": page_id},
        "braille_cells": [],
        "audio_ref": "s0-audio:test",
    }


def _successful_records() -> list[dict]:
    datapack_id = "datapack-fresh"
    return [
        _feedback("speak_catalog_title", index=2, title="new", kind="new_datapack"),
        _feedback("confirm_selection", datapack_id=datapack_id),
        _feedback("scan_started", datapack_id=datapack_id),
        _feedback(
            "candidate_selected",
            identity_role="candidate_verification",
            spread_id="spread-1",
            source_frame_id="video-00000092",
        ),
        _feedback(
            "identity_collection_started",
            identity_role="candidate_verification",
            spread_id="spread-1",
            source_frame_id="video-00000092",
            query_sample_count=5,
        ),
        _feedback(
            "identity_collection_decided",
            identity_role="candidate_verification",
            spread_id="spread-1",
            source_frame_id="video-00000099",
            query_sample_count=5,
            valid_observations=5,
            decision="different",
            timed_out=False,
        ),
        _feedback("spread_sent", sequence=1),
        _feedback(
            "identity_collection_started",
            identity_role="page_change",
            spread_id="spread-1",
            source_frame_id="video-00000099",
            query_sample_count=5,
        ),
        _feedback(
            "identity_collection_progress",
            identity_role="page_change",
            source_frame_id="video-00000100",
            query_sample_count=5,
            valid_observations=1,
        ),
        _feedback(
            "identity_collection_decided",
            identity_role="page_change",
            source_frame_id="video-00000100",
            query_sample_count=5,
            valid_observations=1,
            decision="same",
            timed_out=False,
        ),
        _feedback(
            "identity_collection_progress",
            identity_role="page_change",
            source_frame_id="video-00000310",
            query_sample_count=5,
            valid_observations=1,
        ),
        _feedback(
            "identity_collection_decided",
            identity_role="page_change",
            source_frame_id="video-00000314",
            query_sample_count=5,
            valid_observations=5,
            decision="different",
            timed_out=False,
        ),
        _feedback(
            "candidate_selected",
            identity_role="candidate_verification",
            spread_id="spread-2",
            source_frame_id="video-00000365",
        ),
        _feedback(
            "identity_collection_started",
            identity_role="candidate_verification",
            spread_id="spread-2",
            source_frame_id="video-00000365",
            query_sample_count=5,
        ),
        _feedback(
            "identity_collection_decided",
            identity_role="candidate_verification",
            spread_id="spread-2",
            source_frame_id="video-00000372",
            query_sample_count=5,
            valid_observations=5,
            decision="different",
            timed_out=False,
        ),
        _feedback("spread_sent", sequence=2),
        _feedback(
            "identity_collection_started",
            identity_role="page_change",
            spread_id="spread-2",
            source_frame_id="video-00000372",
            query_sample_count=5,
        ),
        _feedback("scan_input_exhausted", queued_count=2, acked_count=2),
        _feedback("datapack_saved", datapack_id=datapack_id, revision=1),
        _feedback("reading_resumed", document_id=datapack_id),
        _reading(datapack_id, "pg-run-00000001-L"),
        _reading(datapack_id, "pg-run-00000001-R"),
        _reading(datapack_id, "pg-run-00000002-L"),
        _reading(datapack_id, "pg-run-00000002-R"),
    ]


def test_exact_e0b_role_report_passes_only_with_server_evidence() -> None:
    source = {"sha256": E0B_SOURCE_SHA256, "status": "passed"}

    provisional = build_report(_successful_records(), source_report=source)
    passed = build_report(
        _successful_records(),
        source_report=source,
        server_summary={"spread_receipts": 2, "fragments": 4, "duplicates": 0},
    )

    assert provisional["schema_version"] == 2
    assert provisional["status"] == "provisional"
    assert provisional["limitations"]
    assert passed["status"] == "passed"
    assert passed["runtime"]["spread_sent_sequences"] == [1, 2]
    assert len(passed["candidate_attempts"]) == 2
    assert [attempt["maximum_valid_observations"] for attempt in passed["candidate_attempts"]] == [5, 5]
    assert [
        check["terminal"]["decision"]
        for check in passed["page_change_checks"]
        if check["terminal"] is not None
    ] == [
        "same",
        "different",
    ]
    assert all(
        attempt["identity_role"] == "candidate_verification"
        for attempt in passed["candidate_attempts"]
    )
    assert all(
        check["identity_role"] == "page_change" for check in passed["page_change_checks"]
    )
    explicit_starts = [
        check for check in passed["page_change_checks"] if check["explicit_start"]
    ]
    assert [check["spread_id"] for check in explicit_starts] == ["spread-1", "spread-2"]


def test_progress_only_page_change_log_remains_compatible() -> None:
    records = [
        record
        for record in _successful_records()
        if not (
            record.get("code") == "identity_collection_started"
            and record.get("details", {}).get("identity_role") == "page_change"
        )
    ]

    report = build_report(
        records,
        source_report={"sha256": E0B_SOURCE_SHA256, "status": "passed"},
        server_summary={"spread_receipts": 2, "fragments": 4, "duplicates": 0},
    )

    assert report["status"] == "passed"
    assert report["page_change_checks"]
    assert not any(check["explicit_start"] for check in report["page_change_checks"])


def test_report_rejects_wrong_source_and_never_copies_unrecognized_fields() -> None:
    lines = [
        "not json",
        json.dumps(
            _feedback(
                "identity_collection_aborted",
                identity_role="candidate_verification",
                spread_id="spread-1",
                source_frame_id="frame-1",
                query_sample_count=5,
                valid_observations=4,
                terminal_reason="content_occluded",
                pair_digest="must-not-appear",
                raw_token="314",
            )
        ),
    ]

    report = build_report(
        parse_json_lines(lines),
        source_report={"sha256": "0" * 64, "status": "passed"},
    )

    assert report["status"] == "failed"
    serialized = json.dumps(report)
    assert "must-not-appear" not in serialized
    assert "raw_token" not in serialized


def test_supplied_malformed_server_summary_cannot_become_provisional() -> None:
    report = build_report(
        _successful_records(),
        source_report={"sha256": E0B_SOURCE_SHA256, "status": "passed"},
        server_summary={"spread_receipts": 2, "fragments": "four", "duplicates": 0},
    )

    assert report["status"] == "failed"
    server_check = next(
        check for check in report["checks"] if check["name"] == "server_receipts_fragments_duplicates"
    )
    assert server_check["passed"] is False


def test_missing_role_is_not_inferred_from_spread_id() -> None:
    records = _successful_records()
    for record in records:
        if record.get("code") == "identity_collection_decided":
            record["details"].pop("identity_role", None)
            break

    report = build_report(
        records,
        source_report={"sha256": E0B_SOURCE_SHA256, "status": "passed"},
        server_summary={"spread_receipts": 2, "fragments": 4, "duplicates": 0},
    )

    assert report["status"] == "failed"
    role_check = next(check for check in report["checks"] if check["name"] == "identity_roles")
    assert role_check["passed"] is False
    assert report["limitations"]


def test_four_of_five_abort_is_not_a_required_success_condition() -> None:
    report = build_report(
        _successful_records(),
        source_report={"sha256": E0B_SOURCE_SHA256, "status": "passed"},
        server_summary={"spread_receipts": 2, "fragments": 4, "duplicates": 0},
    )

    check_names = {check["name"] for check in report["checks"]}
    assert "four_of_five_hard_reject" not in check_names
    assert "one_of_five_source_exhausted" not in check_names
    assert report["status"] == "passed"
