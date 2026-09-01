"""Build a secret-safe E0-B.3.2 replay verification report from JSONL."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


E0B_SOURCE_SHA256 = "16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8"
REPORT_SCHEMA_VERSION = 2
_CANDIDATE_ROLE = "candidate_verification"
_PAGE_CHANGE_ROLE = "page_change"
_IDENTITY_CODES = {
    "identity_collection_started",
    "identity_collection_progress",
    "identity_collection_decided",
    "identity_collection_aborted",
}
_PAGE_ID_PATTERN = re.compile(r"-(?P<sequence>[0-9]{8})-(?P<side>L|R)$")
_EXPECTED_PAGE_POSITIONS = (
    ("00000001", "L"),
    ("00000001", "R"),
    ("00000002", "L"),
    ("00000002", "R"),
)


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
    page_change_checks: list[dict[str, Any]] = []
    active_page_change: dict[str, Any] | None = None
    role_issues: list[dict[str, str | None]] = []
    spread_sequences: list[int] = []
    exhausted: dict[str, int | None] | None = None
    last_catalog_kind: str | None = None
    selected_catalog_kind: str | None = None
    confirmed_datapack_id: str | None = None
    scan_datapack_id: str | None = None
    saved_datapack_id: str | None = None
    saved_revision: int | None = None
    reading_document_id: str | None = None
    reading_datapack_ids: list[str] = []
    reading_page_ids: list[str] = []

    for record in records:
        if record.get("type") == "reading_snapshot":
            datapack_id = _safe_text(record.get("datapack_id"))
            cursor_value = record.get("cursor")
            cursor = cursor_value if isinstance(cursor_value, Mapping) else {}
            page_id = _safe_text(cursor.get("page_id"))
            if datapack_id is not None and datapack_id not in reading_datapack_ids:
                reading_datapack_ids.append(datapack_id)
            if page_id is not None and page_id not in reading_page_ids:
                reading_page_ids.append(page_id)
            continue
        if record.get("type") != "feedback":
            continue
        code = record.get("code")
        details_value = record.get("details")
        details = details_value if isinstance(details_value, Mapping) else {}

        if code == "speak_catalog_title":
            last_catalog_kind = _safe_text(details.get("kind"))
            continue
        if code == "confirm_selection":
            selected_catalog_kind = last_catalog_kind
            confirmed_datapack_id = _safe_text(details.get("datapack_id"))
            continue
        if code == "scan_started":
            scan_datapack_id = _safe_text(details.get("datapack_id"))
            continue
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
        if code == "datapack_saved":
            saved_datapack_id = _safe_text(details.get("datapack_id"))
            saved_revision = _integer(details.get("revision"))
            continue
        if code == "reading_resumed":
            reading_document_id = _safe_text(details.get("document_id"))
            continue
        if code == "candidate_selected":
            role = _identity_role(details.get("identity_role"))
            if role != _CANDIDATE_ROLE:
                role_issues.append(
                    _role_issue(code, details.get("source_frame_id"), details.get("identity_role"))
                )
            spread_id = _safe_text(details.get("spread_id"))
            if spread_id is None:
                continue
            attempt = _candidate_attempt(attempts, attempt_order, spread_id)
            attempt["selected_events"] = int(attempt["selected_events"]) + 1
            source_frame_id = _safe_text(details.get("source_frame_id"))
            if source_frame_id is not None:
                attempt["candidate_source_frame_id"] = source_frame_id
            continue
        if code not in _IDENTITY_CODES:
            continue

        role = _identity_role(details.get("identity_role"))
        if role is None:
            role_issues.append(
                _role_issue(str(code), details.get("source_frame_id"), details.get("identity_role"))
            )
            continue
        if role == _CANDIDATE_ROLE:
            spread_id = _safe_text(details.get("spread_id"))
            if spread_id is None:
                role_issues.append(
                    _role_issue(str(code), details.get("source_frame_id"), "candidate_without_spread")
                )
                continue
            attempt = _candidate_attempt(attempts, attempt_order, spread_id)
            _update_identity_lifecycle(attempt, str(code), details)
            continue

        if code == "identity_collection_started":
            if active_page_change is not None:
                page_change_checks.append(active_page_change)
            active_page_change = _new_page_change_check(details)
            continue
        if active_page_change is None:
            active_page_change = _new_page_change_check(details)
        _update_identity_lifecycle(active_page_change, str(code), details)
        if code in {"identity_collection_decided", "identity_collection_aborted"}:
            page_change_checks.append(active_page_change)
            active_page_change = None

    if active_page_change is not None:
        page_change_checks.append(active_page_change)

    ordered_attempts = [attempts[spread_id] for spread_id in attempt_order]
    for index, attempt in enumerate(ordered_attempts):
        attempt["transmitted_sequence"] = (
            spread_sequences[index] if index < len(spread_sequences) else None
        )

    source_sha = source_report.get("sha256")
    source_status = source_report.get("status")
    expected_datapack = confirmed_datapack_id
    datapack_lineage = {
        "selected_catalog_kind": selected_catalog_kind,
        "confirmed": confirmed_datapack_id,
        "scan_started": scan_datapack_id,
        "saved": saved_datapack_id,
        "reading_document": reading_document_id,
        "reading_snapshots": reading_datapack_ids,
    }
    candidate_summaries = [
        {
            "spread_id": attempt["spread_id"],
            "valid": attempt["maximum_valid_observations"],
            "required": attempt["required_observations"],
            "terminal": attempt["terminal"],
        }
        for attempt in ordered_attempts
    ]
    page_positions = _page_positions(reading_page_ids)
    checks = [
        _check(
            "source_sha256",
            source_sha == E0B_SOURCE_SHA256 and source_status == "passed",
            {"expected": E0B_SOURCE_SHA256, "actual": source_sha},
        ),
        _check(
            "identity_roles",
            not role_issues,
            {"issues": role_issues},
        ),
        _check(
            "new_datapack_lineage",
            selected_catalog_kind == "new_datapack"
            and expected_datapack is not None
            and scan_datapack_id == expected_datapack,
            datapack_lineage,
        ),
        _check(
            "candidate_attempts",
            len(ordered_attempts) == 2
            and all(_successful_candidate(attempt) for attempt in ordered_attempts),
            {"count": len(ordered_attempts), "attempts": candidate_summaries},
        ),
        _check("spread_sequences", spread_sequences == [1, 2], {"actual": spread_sequences}),
        _check(
            "queued_acked",
            exhausted == {"queued_count": 2, "acked_count": 2},
            {"actual": exhausted},
        ),
        _check(
            "datapack_saved",
            expected_datapack is not None
            and saved_datapack_id == expected_datapack
            and saved_revision == 1,
            {"datapack_id": saved_datapack_id, "revision": saved_revision},
        ),
        _check(
            "reading_four_pages",
            expected_datapack is not None
            and reading_document_id == expected_datapack
            and reading_datapack_ids == [expected_datapack]
            and page_positions == list(_EXPECTED_PAGE_POSITIONS),
            {"page_ids": reading_page_ids, "positions": page_positions},
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

    runtime_passed = all(
        check["passed"]
        for check in checks
        if check["name"] != "server_receipts_fragments_duplicates"
    )
    server_check = next(
        (check for check in checks if check["name"] == "server_receipts_fragments_duplicates"),
        None,
    )
    if not runtime_passed:
        status = "failed"
    elif server_summary is None:
        status = "provisional"
    else:
        status = "passed" if server_check is not None and server_check["passed"] else "failed"
    limitations: list[str] = []
    if role_issues:
        limitations.append(
            "One or more identity events lacked an explicit supported identity_role; no role was inferred."
        )
    if server_summary is None:
        limitations.append(
            "Server spread/fragment/duplicate summary was not supplied; final status remains provisional."
        )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "kind": "e0b_replay_identity_role_boundary",
        "status": status,
        "source": {
            "sha256": source_sha,
            "expected_sha256": E0B_SOURCE_SHA256,
        },
        "datapack": datapack_lineage,
        "candidate_attempts": ordered_attempts,
        "page_change_checks": page_change_checks,
        "runtime": {
            "spread_sent_sequences": spread_sequences,
            "scan_input_exhausted": exhausted,
            "saved_revision": saved_revision,
            "reading_page_ids": reading_page_ids,
        },
        "server": normalized_server,
        "checks": checks,
        "limitations": limitations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize E0-B.3.2 identity roles and replay boundaries from a Laptop JSONL log."
    )
    parser.add_argument("log", type=Path)
    parser.add_argument("source_report", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--server-summary", type=Path)
    args = parser.parse_args(argv)

    records = parse_json_lines(args.log.read_text(encoding="utf-8").splitlines())
    source_report = _load_object(args.source_report)
    server_summary = _load_object(args.server_summary) if args.server_summary is not None else None
    report = build_report(records, source_report=source_report, server_summary=server_summary)
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


def _candidate_attempt(
    attempts: dict[str, dict[str, Any]],
    attempt_order: list[str],
    spread_id: str,
) -> dict[str, Any]:
    if spread_id not in attempts:
        attempts[spread_id] = {
            "identity_role": _CANDIDATE_ROLE,
            "spread_id": spread_id,
            "candidate_source_frame_id": None,
            "selected_events": 0,
            "required_observations": None,
            "maximum_valid_observations": 0,
            "terminal": None,
            "transmitted_sequence": None,
        }
        attempt_order.append(spread_id)
    return attempts[spread_id]


def _new_page_change_check(details: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "identity_role": _PAGE_CHANGE_ROLE,
        "spread_id": _safe_text(details.get("spread_id")),
        "started_source_frame_id": _safe_text(details.get("source_frame_id")),
        "required_observations": _integer(details.get("query_sample_count")),
        "maximum_valid_observations": 0,
        "terminal": None,
    }


def _update_identity_lifecycle(
    target: dict[str, Any],
    code: str,
    details: Mapping[str, Any],
) -> None:
    required = _integer(details.get("query_sample_count"))
    if required is not None:
        target["required_observations"] = required
    valid = _integer(details.get("valid_observations"))
    if valid is not None:
        target["maximum_valid_observations"] = max(
            int(target["maximum_valid_observations"]), valid
        )
    source_frame_id = _safe_text(details.get("source_frame_id"))
    if code == "identity_collection_decided":
        target["terminal"] = {
            "kind": "decided",
            "decision": _safe_text(details.get("decision")),
            "valid_observations": valid,
            "timed_out": details.get("timed_out") is True,
            "source_frame_id": source_frame_id,
        }
    elif code == "identity_collection_aborted":
        target["terminal"] = {
            "kind": "aborted",
            "reason": _safe_text(details.get("terminal_reason")),
            "valid_observations": valid,
            "missing_observations": _integer(details.get("missing_observations")),
            "source_frame_id": source_frame_id,
        }


def _successful_candidate(attempt: Mapping[str, Any]) -> bool:
    terminal = attempt.get("terminal")
    return bool(
        attempt.get("selected_events") == 1
        and attempt.get("candidate_source_frame_id")
        and attempt.get("required_observations") == 5
        and attempt.get("maximum_valid_observations") == 5
        and isinstance(terminal, Mapping)
        and terminal.get("kind") == "decided"
        and terminal.get("decision") == "different"
        and terminal.get("valid_observations") == 5
        and terminal.get("timed_out") is False
    )


def _identity_role(value: Any) -> str | None:
    return value if value in {_CANDIDATE_ROLE, _PAGE_CHANGE_ROLE} else None


def _role_issue(code: str, source_frame_id: Any, actual: Any) -> dict[str, str | None]:
    return {
        "code": code,
        "source_frame_id": _safe_text(source_frame_id),
        "actual": _safe_text(actual),
    }


def _page_positions(page_ids: Iterable[str]) -> list[tuple[str, str]]:
    positions: list[tuple[str, str]] = []
    for page_id in page_ids:
        match = _PAGE_ID_PATTERN.search(page_id)
        if match is None:
            return []
        positions.append((match.group("sequence"), match.group("side")))
    return positions


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


def _safe_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


if __name__ == "__main__":
    raise SystemExit(main())
