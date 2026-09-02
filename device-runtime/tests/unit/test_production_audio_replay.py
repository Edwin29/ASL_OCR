from __future__ import annotations

import json
from pathlib import Path

from asl_device.production_audio_replay import run_production_audio_replay


def test_production_audio_replay_records_manual_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    prepared = tmp_path / "prepared"
    (prepared / "secrets").mkdir(parents=True)
    (prepared / "secrets" / "device-api-key.txt").write_text("secret", encoding="utf-8")
    work = tmp_path / "run" / "work"
    (work / "state" / "server" / "datapacks").mkdir(parents=True)
    (work / "state" / "server" / "server.sqlite3").write_bytes(b"db")
    evidence = work.parent / "evidence"
    evidence.mkdir()
    (evidence / "e0b-p030-e2e-summary.json").write_text(
        json.dumps({"target_node_index": 2, "target_focus_item_id": "p030-problem-1"}),
        encoding="utf-8",
    )

    captured = {}
    def fake_transport(*args, **kwargs):
        captured.update(kwargs)
        return {
            "authenticated": True,
            "failures": 0,
            "events": [{"code": "reading_audio_playback_completed"}],
        }
    monkeypatch.setattr(
        "asl_device.production_audio_replay.exercise_production_audio_transport",
        fake_transport,
    )
    answers = iter(("yes", "yes", "yes", "yes"))

    report = run_production_audio_replay(
        prepared,
        work,
        "datapack-production",
        prompt=lambda _question: next(answers),
    )

    assert report["status"] == "passed"
    assert report["p030_targeted"] is True
    assert captured["first_page_target_node_index"] == 2
    assert captured["expected_first_page_focus_id"] == "p030-problem-1"
    manual = json.loads((evidence / "e0b-manual-listening.json").read_text(encoding="utf-8"))
    assert manual["status"] == "passed"
    assert (evidence / "e0b-production-audio-replay-events.jsonl").is_file()
