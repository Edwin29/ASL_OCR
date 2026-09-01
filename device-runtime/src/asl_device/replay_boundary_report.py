"""Build a secret-safe E0-B replay boundary verification report from JSONL."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


E0B_SOURCE_SHA256 = "16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8"


def parse_json_lines(lines: Iterable[str]) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return tuple(records)


def build_report(
    records: Iterable[Mapping[str, Any]],
    *,
    source_report: Mapping[str, Any],
    server_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    attempts: dict[str, dict[str, Any]] = {}
    attempt_order: list[str] = []
    spread_sequences: list[int] = []
    exhausted: dict[str, Any] | None = None

    for record in records:
        if record.get("type") != "feedback":
            continue
        code = record.get("code")
        details_value = record.get("details")
        details = details_value if isinstance(details_value, Mapping) else {}
        if code == "spread_sent":
            sequence = _integer(details.get("sequence"))
            if sequence is not None:
                spread_sequences.append(sequence)
            continue
        if code == "scan_input_exhausted":
            exhausted = {
                "queued_count": _integer(details.get("queued_count")),
                "acked_count": _integer(details.get("acked_count")),
            }
            continue
        if code not in {
            "candidate_selected",
            "identity_collection_started",
            "identity_collection_progress",
            "identity_collection_decided",
            "identity_collection_aborted",
        }:
            continue
        spread_id = details.get("spread_id")
        if not isinstance(spread_id, str) or not spread_id:
            continue
        if spread_id not in attempts:
            attempts[spread_id] = {
                "spread_id": spread_id,
                "candidate_source_frame_id": None,
                "required_observations": None,
                "maximum_valid_observations": 0,
                "terminal": None,
            }
            attempt_order.append(spread_id)
        attempt = attempts[spread_id]
        source_frame_id = details.get("source_frame_id")
        if code == "candidate_selected" and isinstance(source_frame_id, str):
            attempt["candidate_source_frame_id"] = source_frame_id
        required = _integer(details.get("query_sample_count"))
        if required is not None:
            attempt["required_observations"] = required
        valid = _integer(details.get("valid_observations"))
        if valid is not None:
            attempt["maximum_valid_observations"] = max(
                int(attempt["maximum_valid_observations"]),
                valid,
            )
        if code == "identity_collection_decided":
            attempt["terminal"] = {
                "kind": "decided",
                "decision": _safe_reason(details.get("decision")),
                "valid_observations": valid,
                "timed_out": details.get("timed_out") is True,
                "source_frame_id": source_frame_id if isinstance(source_frame_id, str) else None,
            }
        elif code == "identity_collection_aborted":
            attempt["terminal"] = {
                "kind": "aborted",
                "reason": _safe_reason(details.get("terminal_reason")),
                "valid_observations": valid,
                "missing_observations": _integer(details.get("missing_observations")),
                "source_frame_id": source_frame_id if isinstance(source_frame_id, str) else None,
            }

    ordered_attempts = [attempts[spread_id] for spread_id in attempt_order]
    source_sha = source_report.get("sha256")
    source_status = source_report.get("status")
    checks = [
        _check(
            "source_sha256",
            source_sha == E0B_SOURCE_SHA256 and source_status == "passed",
            {"expected": E0B_SOURCE_SHA256, "actual": source_sha},
        ),
        _check("spread_sequences", spread_sequences == [1, 2], {"actual": spread_sequences}),
        _check(
            "queued_acked",
            exhausted == {"queued_count": 2, "acked_count": 2},
            {"actual": exhausted},
        ),
        _check(
            "four_of_five_hard_reject",
            _has_abort(ordered_attempts, "content_occluded", 4, 5),
            {"reason": "content_occluded", "valid": 4, "required": 5},
        ),
        _check(
            "one_of_five_source_exhausted",
            _has_abort(ordered_attempts, "source_exhausted", 1, 5),
            {"reason": "source_exhausted", "valid": 1, "required": 5},
        ),
    ]

    normalized_server = _server_evidence(server_summary)
    if server_summary is not None:
        checks.append(
            _check(
                "server_receipts_fragments_duplicates",
                normalized_server
                == {"spread_receipts": 2, "fragments": 4, "duplicates": 0},
                {"actual": normalized_server},
            )
        )

    runtime_passed = all(check["passed"] for check in checks if check["name"] != "server_receipts_fragments_duplicates")
    server_check = next(
        (check for check in checks if check["name"] == "server_receipts_fragments_duplicates"),
        None,
    )
    server_passed = server_check is not None and server_check["passed"]
    if not runtime_passed:
        status = "failed"
    elif server_summary is None:
        status = "provisional"
    else:
        status = "passed" if server_passed else "failed"
    return {
        "schema_version": 1,
        "kind": "e0b_replay_candidate_identity_boundary",
        "status": status,
        "source": {
            "sha256": source_sha,
            "expected_sha256": E0B_SOURCE_SHA256,
        },
        "attempts": ordered_attempts,
        "runtime": {
            "spread_sent_sequences": spread_sequences,
            "scan_input_exhausted": exhausted,
        },
        "server": normalized_server,
        "checks": checks,
        "limitations": (
            []
            if normalized_server is not None
            else ["Server spread/fragment/duplicate summary was not supplied; final status remains provisional."]
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize E0-B.3 candidate/identity boundaries from a Laptop JSONL log."
    )
    parser.add_argument("log", type=Path)
    parser.add_argument("source_report", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--server-summary", type=Path)
    args = parser.parse_args(argv)

    records = parse_json_lines(args.log.read_text(encoding="utf-8").splitlines())
    source_report = _load_object(args.source_report)
    server_summary = _load_object(args.server_summary) if args.server_summary is not None else None
    report = build_report(
        records,
        source_report=source_report,
        server_summary=server_summary,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report["status"] in {"passed", "provisional"} else 1


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def _has_abort(
    attempts: Iterable[Mapping[str, Any]],
    reason: str,
    valid: int,
    required: int,
) -> bool:
    for attempt in attempts:
        terminal = attempt.get("terminal")
        if not isinstance(terminal, Mapping):
            continue
        if (
            terminal.get("kind") == "aborted"
            and terminal.get("reason") == reason
            and terminal.get("valid_observations") == valid
            and attempt.get("required_observations") == required
        ):
            return True
    return False


def _server_evidence(value: Mapping[str, Any] | None) -> dict[str, int] | None:
    if value is None:
        return None
    normalized = {
        "spread_receipts": _integer(value.get("spread_receipts")),
        "fragments": _integer(value.get("fragments")),
        "duplicates": _integer(value.get("duplicates")),
    }
    if any(item is None for item in normalized.values()):
        return None
    return {key: int(item) for key, item in normalized.items()}


def _check(name: str, passed: bool, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": dict(evidence)}


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _safe_reason(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


if __name__ == "__main__":
    raise SystemExit(main())
