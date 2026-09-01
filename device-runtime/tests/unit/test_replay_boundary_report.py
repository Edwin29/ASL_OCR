from __future__ import annotations

import json

from asl_device.replay_boundary_report import E0B_SOURCE_SHA256, build_report, parse_json_lines


def _feedback(code: str, **details):
    return {"type": "feedback", "code": code, "details": details}


def test_exact_e0b_boundary_report_passes_only_with_server_evidence() -> None:
    records = [
        _feedback("candidate_selected", spread_id="spread-1", source_frame_id="frame-780"),
        _feedback("identity_collection_started", spread_id="spread-1", query_sample_count=5),
        _feedback(
            "identity_collection_decided",
            spread_id="spread-1",
            query_sample_count=5,
            valid_observations=5,
            decision="different",
            timed_out=False,
        ),
        _feedback("spread_sent", sequence=1),
        _feedback("candidate_selected", spread_id="spread-2", source_frame_id="frame-1866"),
        _feedback("identity_collection_started", spread_id="spread-2", query_sample_count=5),
        _feedback(
            "identity_collection_progress",
            spread_id="spread-2",
            query_sample_count=5,
            valid_observations=4,
        ),
        _feedback(
            "identity_collection_aborted",
            spread_id="spread-2",
            query_sample_count=5,
            valid_observations=4,
            terminal_reason="content_occluded",
        ),
        _feedback("candidate_selected", spread_id="spread-3", source_frame_id="frame-2220"),
        _feedback("identity_collection_started", spread_id="spread-3", query_sample_count=5),
        _feedback(
            "identity_collection_decided",
            spread_id="spread-3",
            query_sample_count=5,
            valid_observations=5,
            decision="different",
            timed_out=False,
        ),
        _feedback("spread_sent", sequence=2),
        _feedback("candidate_selected", spread_id="spread-4", source_frame_id="frame-2670"),
        _feedback("identity_collection_started", spread_id="spread-4", query_sample_count=5),
        _feedback(
            "identity_collection_aborted",
            spread_id="spread-4",
            query_sample_count=5,
            valid_observations=1,
            terminal_reason="source_exhausted",
        ),
        _feedback("scan_input_exhausted", queued_count=2, acked_count=2),
    ]
    source = {"sha256": E0B_SOURCE_SHA256, "status": "passed"}

    provisional = build_report(records, source_report=source)
    passed = build_report(
        records,
        source_report=source,
        server_summary={"spread_receipts": 2, "fragments": 4, "duplicates": 0},
    )

    assert provisional["status"] == "provisional"
    assert provisional["limitations"]
    assert passed["status"] == "passed"
    assert passed["runtime"]["spread_sent_sequences"] == [1, 2]
    assert [attempt["maximum_valid_observations"] for attempt in passed["attempts"]] == [5, 4, 5, 1]


def test_report_rejects_wrong_source_and_never_copies_unrecognized_fields() -> None:
    lines = [
        "not json",
        json.dumps(
            _feedback(
                "identity_collection_aborted",
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
    records = [
        _feedback("spread_sent", sequence=1),
        _feedback("spread_sent", sequence=2),
        _feedback("scan_input_exhausted", queued_count=2, acked_count=2),
        _feedback(
            "identity_collection_aborted",
            spread_id="spread-2",
            query_sample_count=5,
            valid_observations=4,
            terminal_reason="content_occluded",
        ),
        _feedback(
            "identity_collection_aborted",
            spread_id="spread-4",
            query_sample_count=5,
            valid_observations=1,
            terminal_reason="source_exhausted",
        ),
    ]

    report = build_report(
        records,
        source_report={"sha256": E0B_SOURCE_SHA256, "status": "passed"},
        server_summary={"spread_receipts": 2, "fragments": "four", "duplicates": 0},
    )

    assert report["status"] == "failed"
    server_check = next(
        check for check in report["checks"] if check["name"] == "server_receipts_fragments_duplicates"
    )
    assert server_check["passed"] is False
