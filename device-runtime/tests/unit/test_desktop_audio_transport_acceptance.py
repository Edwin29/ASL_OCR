from __future__ import annotations

import io
import json
import wave
from pathlib import Path

import pytest

from asl_device.desktop_audio_transport_acceptance import (
    AudioTransportAcceptanceError,
    WindowsMemoryWavPlayer,
    analyze_wav,
    collect_manual_listening,
    collect_manual_piper_listening,
    run_desktop_audio_transport_acceptance,
)
from document_parser.server.e0b_bench_server import BenchSynthesizer


def _wav_bytes(text: str) -> bytes:
    pcm, sample_rate, channels = BenchSynthesizer()(text)
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return stream.getvalue()


def _prepared_root(tmp_path: Path) -> Path:
    prepared = tmp_path / "prepared"
    secret = prepared / "secrets" / "device-api-key.txt"
    secret.parent.mkdir(parents=True)
    secret.write_text("test-secret-value\n", encoding="utf-8")
    return prepared


class FakeFeedbackBackend:
    def __init__(self) -> None:
        self.beeps = 0

    def beep(self, _pattern: object) -> None:
        self.beeps += 1

class FakeWavPlayer:
    def __init__(self) -> None:
        self.hashes: list[str] = []

    def play(self, payload: bytes) -> None:
        self.hashes.append(analyze_wav(payload).sha256)


class FakeWinsound:
    SND_MEMORY = 4

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, int]] = []

    def PlaySound(self, payload: bytes, flags: int) -> None:
        self.calls.append((payload, flags))


def test_wav_analysis_is_audible_bounded_and_distinct() -> None:
    low = analyze_wav(_wav_bytes("낮은 음 transport fixture"))
    high = analyze_wav(_wav_bytes("높은 음 transport fixture"))

    assert low.sample_rate == high.sample_rate == 16_000
    assert low.channels == high.channels == 1
    assert low.sample_width == high.sample_width == 2
    assert low.duration_ms == high.duration_ms == 500
    assert low.peak > 0 and low.rms > 0
    assert low.sha256 != high.sha256


def test_wav_analysis_rejects_invalid_bytes() -> None:
    with pytest.raises(AudioTransportAcceptanceError, match="valid PCM WAV"):
        analyze_wav(b"not-a-wave")


def test_windows_memory_player_uses_default_sync_without_nonexistent_flag() -> None:
    winsound = FakeWinsound()
    player = WindowsMemoryWavPlayer.__new__(WindowsMemoryWavPlayer)
    player._winsound = winsound

    player.play(b"RIFF-fixture")

    assert winsound.calls == [(b"RIFF-fixture", winsound.SND_MEMORY)]


def test_manual_listening_requires_explicit_heard_and_bounds_retry() -> None:
    plays: list[int] = []
    answers = iter(
        [
            "", "yes", "yes", "yes", "yes", "retry",
            "yes", "yes", "yes", "yes", "heard",
        ]
    )

    result = collect_manual_listening(
        lambda: plays.append(1),
        lambda _message: next(answers),
        max_attempts=3,
    )

    assert result["status"] == "heard"
    assert result["attempts"] == 2
    assert result["decisions"] == ["retry", "heard"]
    assert result["attempt_details"][1]["component_checks"] == {
        "beep": True,
        "tone_low": True,
        "tone_high": True,
        "tones_distinguishable": True,
    }
    assert len(plays) == 2


def test_manual_listening_does_not_promote_not_heard() -> None:
    answers = iter(["yes", "no", "yes", "yes", "heard", "not-heard"])
    result = collect_manual_listening(lambda: None, lambda _message: next(answers))

    assert result["status"] == "not_heard"
    assert result["confirmed_at"] is None
    assert result["attempt_details"][0]["component_checks"]["tone_low"] is False


def test_piper_manual_listening_requires_every_component() -> None:
    answers = iter(
        ["yes", "yes", "yes", "yes", "no", "yes", "heard", "not-heard"]
    )

    result = collect_manual_piper_listening(
        lambda: None,
        lambda _message: next(answers),
    )

    assert result["status"] == "not_heard"
    checks = result["attempt_details"][0]["component_checks"]
    assert checks["utterance_2_intelligible"] is False
    assert result["expected_sequence"] == "beep,piper-utterance-1,piper-utterance-2"


def test_no_playback_runs_real_http_transport_and_leaves_manual_pending(tmp_path: Path) -> None:
    result = run_desktop_audio_transport_acceptance(
        _prepared_root(tmp_path),
        evidence_dir=tmp_path / "evidence",
        work_dir=tmp_path / "work",
        playback=False,
    )
    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))

    assert result["status"] == "manual_pending"
    assert report["automated"]["transport_status"] == "passed"
    assert report["automated"]["authorized_streams"] == 2
    assert report["automated"]["cross_session_resource_rejected"] is True
    assert report["automated"]["invalid_key_request_rejected"] is True
    assert report["manual_listening"]["status"] == "not_run"
    assert report["storage"]["client_wav_persisted"] is False
    assert "test-secret-value" not in Path(result["report"]).read_text(encoding="utf-8")


def test_fake_playback_records_retry_then_explicit_heard(tmp_path: Path) -> None:
    backend = FakeFeedbackBackend()
    player = FakeWavPlayer()
    answers = iter(
        [
            "yes", "no", "yes", "yes", "retry",
            "yes", "yes", "yes", "yes", "heard",
        ]
    )

    result = run_desktop_audio_transport_acceptance(
        _prepared_root(tmp_path),
        evidence_dir=tmp_path / "evidence",
        work_dir=tmp_path / "work",
        playback=True,
        prompt=lambda _message: next(answers),
        feedback_backend=backend,
        wav_player=player,
    )
    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))

    assert result["status"] == "passed"
    assert backend.beeps == 2
    assert len(player.hashes) == 4
    assert player.hashes[0] != player.hashes[1]
    assert player.hashes[:2] == player.hashes[2:]
    assert report["manual_listening"]["decisions"] == ["retry", "heard"]
    assert report["automated"]["sapi_status"] == "excluded"
