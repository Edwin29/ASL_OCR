from __future__ import annotations

import struct

import pytest

from document_parser.server.e0b_bench_server import BenchSynthesizer, build_e0b_bench_server, main


def test_bench_synthesizer_is_deterministic_audible_and_distinct() -> None:
    synthesizer = BenchSynthesizer()

    low, sample_rate, channels = synthesizer("낮은 음 transport fixture")
    low_replay, _, _ = synthesizer("낮은 음 transport fixture")
    high, _, _ = synthesizer("높은 음 transport fixture")
    samples = struct.unpack(f"<{len(low) // 2}h", low)

    assert sample_rate == 16000
    assert channels == 1
    assert len(low) == sample_rate * synthesizer.duration_ms // 1000 * 2
    assert low == low_replay
    assert low != high
    assert max(abs(sample) for sample in samples) > 1000
    assert synthesizer.frequency_for("낮은 음") == 440
    assert synthesizer.frequency_for("높은 음") == 880


def test_e0b_bench_server_exposes_real_health_and_rejects_bad_auth(tmp_path) -> None:
    composition = build_e0b_bench_server(tmp_path / "bench", "secret")
    client = composition.app.test_client()

    health = client.get("/api/v1/health")
    catalog = client.get("/api/v1/devices/laptop-1/datapacks")

    assert health.status_code == 200
    assert health.get_json()["status"] == "ok"
    assert catalog.status_code == 401
    assert (tmp_path / "bench/server.sqlite3").is_file()


def test_e0b_bench_server_refuses_direct_non_loopback_bind(tmp_path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")

    with pytest.raises(SystemExit):
        main(
            [
                "--host",
                "0.0.0.0",
                "--state-root",
                str(tmp_path / "state"),
                "--api-key-file",
                str(secret),
            ]
        )
