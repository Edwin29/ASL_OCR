"""Replay and record production audio acceptance from an existing E0-B.5-D run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .desktop_loopback_acceptance import LoopbackAcceptanceError, _write_json
from .production_full_model_acceptance import exercise_production_audio_transport


def run_production_audio_replay(
    prepared_root: str | Path,
    work_dir: str | Path,
    datapack_id: str,
    *,
    prompt=input,
) -> dict[str, object]:
    prepared = Path(prepared_root).resolve()
    work = Path(work_dir).resolve()
    evidence = work.parent / "evidence"
    database = work / "state" / "server" / "server.sqlite3"
    datapacks = work / "state" / "server" / "datapacks"
    api_key = prepared / "secrets" / "device-api-key.txt"
    if not database.is_file() or not datapacks.is_dir() or not api_key.is_file():
        raise LoopbackAcceptanceError("existing production run or prepared API key is incomplete")

    p030_summary_path = evidence / "e0b-p030-e2e-summary.json"
    p030_summary = (
        json.loads(p030_summary_path.read_text(encoding="utf-8"))
        if p030_summary_path.is_file()
        else None
    )
    p030_targeted = isinstance(p030_summary, dict) and isinstance(
        p030_summary.get("target_node_index"), int
    )

    transport = exercise_production_audio_transport(
        database,
        datapacks,
        api_key,
        datapack_id,
        playback=True,
        first_page_target_node_index=(
            int(p030_summary["target_node_index"]) if p030_targeted else 0
        ),
        expected_first_page_focus_id=(
            str(p030_summary["target_focus_item_id"]) if p030_targeted else None
        ),
    )
    checks = {}
    questions = (
        (
            "p030_problem_heard" if p030_targeted else "all_pages_heard",
            "30페이지 첫 문제의 Piper 한국어 음성이 들렸습니까? [yes/no]: "
            if p030_targeted
            else "네 페이지의 Piper 한국어 음성이 모두 들렸습니까? [yes/no]: ",
        ),
        (
            "content_matched",
            "음성이 30페이지의 지수함수 문제 내용과 일치했습니까? [yes/no]: "
            if p030_targeted
            else "각 음성이 현재 페이지 내용과 일치했습니까? [yes/no]: ",
        ),
        ("not_fixture_audio", "beep/tone/SAPI가 아닌 실제 Piper 음성이었습니까? [yes/no]: "),
        ("no_stale_audio", "빠른 이동 뒤 이전 페이지 음성이 남지 않았습니까? [yes/no]: "),
    )
    for name, question in questions:
        answer = ""
        while answer not in {"yes", "no"}:
            answer = prompt(question).strip().lower()
        checks[name] = answer == "yes"
    manual = {"status": "passed" if all(checks.values()) else "failed", "checks": checks}
    report = {
        "schema_version": 1,
        "kind": "e0b_production_audio_replay",
        "status": manual["status"],
        "datapack_id": datapack_id,
        "work_dir": str(work),
        "evidence_dir": str(evidence),
        "audio_transport": {key: value for key, value in transport.items() if key != "events"},
        "p030_targeted": p030_targeted,
        "manual_listening": manual,
    }
    evidence.mkdir(parents=True, exist_ok=True)
    _write_json(evidence / "e0b-manual-listening.json", manual)
    _write_json(evidence / "e0b-production-audio-replay-report.json", report)
    (evidence / "e0b-production-audio-replay-events.jsonl").write_text(
        "".join(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            for event in transport["events"]
        ),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared_root", type=Path)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("datapack_id")
    args = parser.parse_args(argv)
    try:
        report = run_production_audio_replay(
            args.prepared_root,
            args.work_dir,
            args.datapack_id,
        )
    except (LoopbackAcceptanceError, OSError, ValueError, RuntimeError) as exc:
        print(f"[E0-B.5-D-AUDIO] FAILED: {type(exc).__name__}: {exc}", flush=True)
        return 1
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
