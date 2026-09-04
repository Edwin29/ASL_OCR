"""Read-only serving preflight for every current READY datapack revision.

The check deliberately uses the production speech and braille rules but does
not create reading sessions, update cursors, synthesize audio, or mutate the
catalog.  It catches content defects before a user reaches the affected item.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from document_parser.accessibility.braille import BraillePresenter, braille_scrollable_spans
from document_parser.accessibility.speech import normalize_tts_pronunciation
from document_parser.datapack.ingest import enumerate_utterances
from document_parser.datapack.loader import load_datapack
from document_parser.datapack.schema import SYSTEM_BOUNDARY_MESSAGES, system_message_key

REPORT_SCHEMA_VERSION = 1


def preflight_datapack_root(
    root: str | Path,
    system_dir: str | Path,
    *,
    viewport_size: int = 10,
    expected_datapack_id: str | None = None,
    revision: int | None = None,
) -> dict[str, Any]:
    if viewport_size <= 0:
        raise ValueError("viewport_size must be positive")
    root = Path(root).resolve()
    system_dir = Path(system_dir).resolve()
    issues: list[dict[str, Any]] = []
    metrics = {
        "page_count": 0,
        "focus_item_count": 0,
        "braille_target_count": 0,
        "braille_nonempty_count": 0,
        "expected_utterance_count": 0,
        "checked_audio_file_count": 0,
    }

    try:
        datapack = load_datapack(root, system_dir)
    except Exception as exc:
        _issue(issues, "error", "DATAPACK_LOAD_FAILED", error_type=type(exc).__name__)
        return _datapack_result(expected_datapack_id or root.name, revision, metrics, issues)

    datapack_id = datapack.book_id
    if expected_datapack_id is not None and datapack_id != expected_datapack_id:
        _issue(issues, "error", "DATAPACK_IDENTITY_MISMATCH")
    if datapack.document.get("document_id") != datapack_id:
        _issue(issues, "error", "DOCUMENT_IDENTITY_MISMATCH")

    pages = datapack.document.get("pages")
    if not isinstance(pages, list) or not pages:
        _issue(issues, "error", "DOCUMENT_PAGES_INVALID")
        pages = []
    metrics["page_count"] = len(pages)
    manifest_page_ids = datapack.manifest.get("page_ids")
    document_page_ids = [page.get("page_id") for page in pages if isinstance(page, dict)]
    if manifest_page_ids != document_page_ids:
        _issue(issues, "error", "PAGE_ORDER_MISMATCH")

    presenter = BraillePresenter(viewport_size=viewport_size)
    seen_page_ids: set[str] = set()
    seen_item_ids: set[str] = set()
    for page_index, page in enumerate(pages):
        if not isinstance(page, dict):
            _issue(issues, "error", "PAGE_INVALID", page_index=page_index)
            continue
        page_id = page.get("page_id")
        if not isinstance(page_id, str) or not page_id or page_id in seen_page_ids:
            _issue(issues, "error", "PAGE_ID_INVALID", page_index=page_index)
        else:
            seen_page_ids.add(page_id)
        items = page.get("focus_items")
        if not isinstance(items, list) or not items:
            _issue(issues, "error", "PAGE_FOCUS_ITEMS_INVALID", page_index=page_index)
            continue
        for node_index, item in enumerate(items):
            metrics["focus_item_count"] += 1
            if not isinstance(item, dict):
                _issue(
                    issues,
                    "error",
                    "FOCUS_ITEM_INVALID",
                    page_index=page_index,
                    node_index=node_index,
                )
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id or item_id in seen_item_ids:
                _issue(
                    issues,
                    "error",
                    "FOCUS_ITEM_ID_INVALID",
                    page_index=page_index,
                    node_index=node_index,
                )
                item_id = f"page-{page_index}-item-{node_index}"
            else:
                seen_item_ids.add(item_id)
            if item.get("page_id") != page_id:
                _issue(issues, "error", "FOCUS_ITEM_PAGE_MISMATCH", source_id=item_id)
            try:
                spans = braille_scrollable_spans(item)
            except Exception as exc:
                _issue(
                    issues,
                    "error",
                    "BRAILLE_SPAN_DISCOVERY_FAILED",
                    source_id=item_id,
                    error_type=type(exc).__name__,
                )
                spans = []
            for span_index in range(len(spans)):
                metrics["braille_target_count"] += 1
                nonempty = _preflight_frames(
                    lambda offset, item=item, span_index=span_index: presenter.present_focus(
                        item, offset, span_index
                    ),
                    issues,
                    source_id=f"{item_id}#{span_index}",
                    viewport_size=viewport_size,
                )
                metrics["braille_nonempty_count"] += int(nonempty)
            if item.get("kind") == "TABLE":
                cells = item.get("cells")
                if not isinstance(cells, list):
                    _issue(issues, "error", "TABLE_CELLS_INVALID", source_id=item_id)
                    continue
                for cell_index, cell in enumerate(cells):
                    metrics["braille_target_count"] += 1
                    if not isinstance(cell, dict):
                        _issue(
                            issues,
                            "error",
                            "TABLE_CELL_INVALID",
                            source_id=item_id,
                            cell_index=cell_index,
                        )
                        continue
                    cell_id = str(cell.get("id") or f"{item_id}#cell-{cell_index}")
                    nonempty = _preflight_frames(
                        lambda offset, cell=cell: presenter.present_table_cell(cell, offset),
                        issues,
                        source_id=cell_id,
                        viewport_size=viewport_size,
                    )
                    metrics["braille_nonempty_count"] += int(nonempty)

    try:
        utterances = enumerate_utterances(datapack.document)
    except Exception as exc:
        _issue(issues, "error", "UTTERANCE_ENUMERATION_FAILED", error_type=type(exc).__name__)
        utterances = {}
    utterances.update(
        {
            f"system:{system_message_key(text)}": text
            for text in SYSTEM_BOUNDARY_MESSAGES
        }
    )
    metrics["expected_utterance_count"] = len(utterances)
    normalized_audio: dict[str, dict[str, Any]] = {}
    for stored_text, entry in datapack.audio_by_text.items():
        normalized_audio.setdefault(normalize_tts_pronunciation(stored_text), entry)

    checked_paths: set[Path] = set()
    for utterance_key, text in utterances.items():
        entry = datapack.audio_by_text.get(text) or normalized_audio.get(text)
        if entry is None:
            _issue(issues, "error", "AUDIO_UTTERANCE_MISSING", utterance_key=utterance_key)
            continue
        wav_value = entry.get("wav")
        if not isinstance(wav_value, str):
            _issue(issues, "error", "AUDIO_PATH_INVALID", utterance_key=utterance_key)
            continue
        path = Path(wav_value).resolve()
        if path in checked_paths:
            continue
        checked_paths.add(path)
        metrics["checked_audio_file_count"] += 1
        if not _is_within(path, root) and not _is_within(path, system_dir):
            _issue(issues, "error", "AUDIO_PATH_ESCAPES_DATAPACK", utterance_key=utterance_key)
            continue
        if not path.is_file():
            _issue(issues, "error", "AUDIO_FILE_MISSING", utterance_key=utterance_key)
            continue
        try:
            with wave.open(str(path), "rb") as handle:
                channels = handle.getnchannels()
                sample_width = handle.getsampwidth()
                sample_rate = handle.getframerate()
                frames = handle.getnframes()
            if channels <= 0 or sample_width != 2 or sample_rate <= 0 or frames <= 0:
                raise ValueError("unsupported WAV metadata")
        except (OSError, EOFError, wave.Error, ValueError) as exc:
            _issue(
                issues,
                "error",
                "AUDIO_WAV_INVALID",
                utterance_key=utterance_key,
                error_type=type(exc).__name__,
            )

    return _datapack_result(datapack_id, revision, metrics, issues)


def preflight_catalog(
    database_path: str | Path,
    datapacks_root: str | Path,
    *,
    viewport_size: int = 10,
) -> dict[str, Any]:
    database_path = Path(database_path).resolve()
    datapacks_root = Path(datapacks_root).resolve()
    rows: list[dict[str, Any]] = []
    try:
        connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT d.datapack_id, d.status AS datapack_status, d.current_revision,
                           r.revision, r.root_relative_path, r.manifest_sha256
                      FROM datapacks d
                      JOIN datapack_revisions r
                        ON r.datapack_id=d.datapack_id AND r.revision=d.current_revision
                     WHERE d.status='ready' AND r.status='ready'
                     ORDER BY d.datapack_id
                    """
                )
            ]
            catalog_count = int(connection.execute("SELECT COUNT(*) FROM datapacks").fetchone()[0])
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "status": "failed",
            "catalog_datapack_count": 0,
            "checked_revision_count": 0,
            "skipped_datapack_count": 0,
            "error_count": 1,
            "warning_count": 0,
            "datapacks": [],
            "issues": [{"severity": "error", "code": "CATALOG_OPEN_FAILED", "error_type": type(exc).__name__}],
        }

    results: list[dict[str, Any]] = []
    catalog_issues: list[dict[str, Any]] = []
    for row in rows:
        relative = Path(str(row["root_relative_path"]))
        root = (datapacks_root / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not _is_within(root, datapacks_root):
            result = _datapack_result(
                str(row["datapack_id"]),
                int(row["revision"]),
                {},
                [{"severity": "error", "code": "REVISION_PATH_INVALID"}],
            )
        elif _sha256_file_or_none(root / "manifest.json") != row["manifest_sha256"]:
            result = _datapack_result(
                str(row["datapack_id"]),
                int(row["revision"]),
                {},
                [{"severity": "error", "code": "MANIFEST_HASH_MISMATCH"}],
            )
        else:
            result = preflight_datapack_root(
                root,
                datapacks_root / "_system",
                viewport_size=viewport_size,
                expected_datapack_id=str(row["datapack_id"]),
                revision=int(row["revision"]),
            )
        results.append(result)

    error_count = sum(int(result["error_count"]) for result in results) + len(catalog_issues)
    warning_count = sum(int(result["warning_count"]) for result in results)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "status": "passed" if error_count == 0 else "failed",
        "catalog_datapack_count": catalog_count,
        "checked_revision_count": len(results),
        "skipped_datapack_count": catalog_count - len(results),
        "error_count": error_count,
        "warning_count": warning_count,
        "datapacks": results,
        "issues": catalog_issues,
    }


def write_preflight_report(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _preflight_frames(
    render: Callable[[int], dict[str, object]],
    issues: list[dict[str, Any]],
    *,
    source_id: str,
    viewport_size: int,
) -> bool:
    try:
        first = render(0)
        _validate_frame(first, source_id, viewport_size)
        total = first.get("total_cell_count")
        if not isinstance(total, int) or isinstance(total, bool) or total < 0:
            raise ValueError("invalid total_cell_count")
        for offset in range(viewport_size, total, viewport_size):
            _validate_frame(render(offset), source_id, viewport_size)
        if total == 0:
            _issue(issues, "warning", "BRAILLE_TARGET_EMPTY", source_id=source_id)
        return total > 0
    except Exception as exc:
        _issue(
            issues,
            "error",
            "BRAILLE_RENDER_FAILED",
            source_id=source_id,
            error_type=type(exc).__name__,
        )
        return False


def _validate_frame(frame: dict[str, object], source_id: str, viewport_size: int) -> None:
    if not isinstance(frame, dict):
        raise TypeError("braille frame is not an object")
    cells = frame.get("cells")
    if not isinstance(cells, list) or len(cells) > viewport_size:
        raise ValueError("braille frame cell count is invalid")
    if any(isinstance(cell, bool) or not isinstance(cell, int) or not 0 <= cell <= 63 for cell in cells):
        raise ValueError("braille frame contains a non-six-dot cell")
    if not isinstance(frame.get("source_id"), str):
        raise ValueError(f"braille frame source is invalid for {source_id}")


def _datapack_result(
    datapack_id: str,
    revision: int | None,
    metrics: dict[str, Any],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    errors = sum(issue.get("severity") == "error" for issue in issues)
    warnings = sum(issue.get("severity") == "warning" for issue in issues)
    return {
        "datapack_id": datapack_id,
        "revision": revision,
        "status": "passed" if errors == 0 else "failed",
        "error_count": errors,
        "warning_count": warnings,
        "metrics": metrics,
        "issues": issues,
    }


def _issue(issues: list[dict[str, Any]], severity: str, code: str, **details: Any) -> None:
    issue = {"severity": severity, "code": code}
    issue.update({key: value for key, value in details.items() if value is not None})
    issues.append(issue)


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _sha256_file_or_none(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datapacks-dir", type=Path, required=True)
    parser.add_argument("--state-db", type=Path, required=True)
    parser.add_argument("--viewport-size", type=int, default=10)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--strict-warnings", action="store_true")
    args = parser.parse_args(argv)
    report = preflight_catalog(
        args.state_db,
        args.datapacks_dir,
        viewport_size=args.viewport_size,
    )
    if args.report is not None:
        write_preflight_report(report, args.report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    failed = report["error_count"] > 0 or (
        args.strict_warnings and report["warning_count"] > 0
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
