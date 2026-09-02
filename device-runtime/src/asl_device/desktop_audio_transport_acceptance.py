"""Desktop S0 audio transport acceptance with explicit human listening evidence."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from document_parser.datapack.ingest import build_datapack
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl
from document_parser.server.e0b_bench_server import BenchSynthesizer, build_e0b_bench_server
from werkzeug.serving import WSGIRequestHandler, make_server

class AudioTransportAcceptanceError(RuntimeError):
    """A transport, evidence, or explicit listening invariant failed."""


@dataclass(frozen=True, slots=True)
class WavAnalysis:
    content_length: int
    sha256: str
    duration_ms: int
    sample_rate: int
    channels: int
    sample_width: int
    peak: int
    rms: float


class WindowsMemoryWavPlayer:
    """Play a complete bounded WAV from memory; no client file is created."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows in-memory WAV playback is available only on Windows")
        import winsound

        self._winsound = winsound

    def play(self, wav_bytes: bytes) -> None:
        self._winsound.PlaySound(
            wav_bytes,
            # Synchronous playback is winsound's default (flag value 0).
            # Python exposes SND_ASYNC but does not define SND_SYNC.
            self._winsound.SND_MEMORY,
        )


class WindowsBeepBackend:
    """Minimal Windows output-device smoke; production speech is Piper WAV."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows beep is available only on Windows")
        import winsound

        self._winsound = winsound

    def beep(self, pattern: tuple[tuple[int, int], ...]) -> None:
        for frequency_hz, duration_ms in pattern:
            self._winsound.Beep(frequency_hz, duration_ms)


class _FixtureVlAdapter:
    engine_id = "e0b-audio-transport-fixture"
    engine_version = "1"

    def __init__(self, result_by_path: Mapping[str, dict[str, object]]) -> None:
        self.result_by_path = result_by_path

    def parse_page(self, image_path: Path) -> dict[str, object]:
        return self.result_by_path[str(Path(image_path).resolve())]


class _QuietRequestHandler(WSGIRequestHandler):
    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        return


def analyze_wav(payload: bytes) -> WavAnalysis:
    if len(payload) > 4 * 1024 * 1024:
        raise AudioTransportAcceptanceError("WAV exceeded the 4 MiB acceptance bound")
    try:
        with wave.open(io.BytesIO(payload), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            frames = wav_file.readframes(frame_count)
    except (EOFError, wave.Error) as exc:
        raise AudioTransportAcceptanceError("response was not a valid PCM WAV") from exc
    if channels not in {1, 2} or sample_width != 2 or not 8_000 <= sample_rate <= 48_000:
        raise AudioTransportAcceptanceError("WAV format was outside the accepted PCM bounds")
    if frame_count <= 0:
        raise AudioTransportAcceptanceError("WAV contained no audio frames")
    sample_count = len(frames) // 2
    samples = struct.unpack(f"<{sample_count}h", frames)
    peak = max(abs(sample) for sample in samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / sample_count)
    duration_ms = round(frame_count / sample_rate * 1000)
    if not 0 < duration_ms <= 120_000:
        raise AudioTransportAcceptanceError("WAV duration was outside the accepted bound")
    return WavAnalysis(
        content_length=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        duration_ms=duration_ms,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
        peak=peak,
        rms=round(rms, 3),
    )


def collect_manual_listening(
    play_once: Callable[[], None],
    prompt: Callable[[str], str] = input,
    *,
    max_attempts: int = 3,
) -> dict[str, object]:
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    decisions: list[str] = []
    attempts: list[dict[str, object]] = []
    component_prompts = (
        ("beep", "짧은 beep가 들렸습니까? [yes/no]: "),
        ("tone_low", "낮은 tone이 들렸습니까? [yes/no]: "),
        ("tone_high", "높은 tone이 들렸습니까? [yes/no]: "),
        ("tones_distinguishable", "낮은 tone과 높은 tone의 음높이가 다르게 구분됐습니까? [yes/no]: "),
    )
    for attempt in range(1, max_attempts + 1):
        play_once()
        component_checks: dict[str, bool] = {}
        for component, message in component_prompts:
            while True:
                answer = prompt(message).strip().lower()
                if answer in {"yes", "no"}:
                    break
                print("yes 또는 no를 정확히 입력해야 합니다.", flush=True)
            component_checks[component] = answer == "yes"
        all_components_heard = all(component_checks.values())
        while True:
            choices = {"heard", "not-heard", "retry"} if all_components_heard else {"not-heard", "retry"}
            choice_text = "heard/not-heard/retry" if all_components_heard else "not-heard/retry"
            decision = prompt(f"청취 결과를 입력하세요 [{choice_text}]: ").strip().lower()
            if decision in choices:
                break
            if decision == "heard" and not all_components_heard:
                print("모든 구성요소가 yes일 때만 heard로 기록할 수 있습니다.", flush=True)
            else:
                print(f"{choice_text} 중 하나를 정확히 입력해야 합니다.", flush=True)
        decisions.append(decision)
        attempts.append(
            {
                "attempt": attempt,
                "component_checks": component_checks,
                "decision": decision,
            }
        )
        if decision == "heard":
            return {
                "status": "heard",
                "attempts": attempt,
                "decisions": decisions,
                "attempt_details": attempts,
                "expected_sequence": "beep,tone-low,tone-high",
                "confirmed_at": _utc_now(),
            }
        if decision == "not-heard":
            return {
                "status": "not_heard",
                "attempts": attempt,
                "decisions": decisions,
                "attempt_details": attempts,
                "expected_sequence": "beep,tone-low,tone-high",
                "confirmed_at": None,
            }
    return {
        "status": "not_heard",
        "attempts": max_attempts,
        "decisions": decisions,
        "attempt_details": attempts,
        "expected_sequence": "beep,tone-low,tone-high",
        "confirmed_at": None,
        "reason": "retry_limit_reached",
    }


def collect_manual_piper_listening(
    play_once: Callable[[], None],
    prompt: Callable[[str], str] = input,
    *,
    max_attempts: int = 3,
) -> dict[str, object]:
    """Require component-level confirmation for two fixed Korean Piper utterances."""
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    decisions: list[str] = []
    attempts: list[dict[str, object]] = []
    component_prompts = (
        ("beep", "짧은 beep가 들렸습니까? [yes/no]: "),
        ("utterance_1_audible", "첫 번째 Piper 음성이 들렸습니까? [yes/no]: "),
        (
            "utterance_1_intelligible",
            "첫 번째 문장이 '첫 번째 음성입니다. 데스크탑 파이퍼 검증을 시작합니다.'로 이해됐습니까? [yes/no]: ",
        ),
        ("utterance_2_audible", "두 번째 Piper 음성이 들렸습니까? [yes/no]: "),
        (
            "utterance_2_intelligible",
            "두 번째 문장이 '두 번째 음성입니다. 다음 페이지로 이동했습니다.'로 이해됐습니까? [yes/no]: ",
        ),
        ("order_correct", "beep 뒤에 첫 번째, 두 번째 음성이 순서대로 재생됐습니까? [yes/no]: "),
    )
    for attempt in range(1, max_attempts + 1):
        play_once()
        component_checks: dict[str, bool] = {}
        for component, message in component_prompts:
            while True:
                answer = prompt(message).strip().lower()
                if answer in {"yes", "no"}:
                    break
                print("yes 또는 no를 정확히 입력해야 합니다.", flush=True)
            component_checks[component] = answer == "yes"
        all_components_heard = all(component_checks.values())
        while True:
            choices = {"heard", "not-heard", "retry"} if all_components_heard else {"not-heard", "retry"}
            choice_text = "heard/not-heard/retry" if all_components_heard else "not-heard/retry"
            decision = prompt(f"Piper 청취 결과를 입력하세요 [{choice_text}]: ").strip().lower()
            if decision in choices:
                break
            if decision == "heard" and not all_components_heard:
                print("모든 Piper 구성요소가 yes일 때만 heard로 기록할 수 있습니다.", flush=True)
            else:
                print(f"{choice_text} 중 하나를 정확히 입력해야 합니다.", flush=True)
        decisions.append(decision)
        attempts.append(
            {
                "attempt": attempt,
                "component_checks": component_checks,
                "decision": decision,
            }
        )
        if decision == "heard":
            return {
                "status": "heard",
                "attempts": attempt,
                "decisions": decisions,
                "attempt_details": attempts,
                "expected_sequence": "beep,piper-utterance-1,piper-utterance-2",
                "confirmed_at": _utc_now(),
            }
        if decision == "not-heard":
            return {
                "status": "not_heard",
                "attempts": attempt,
                "decisions": decisions,
                "attempt_details": attempts,
                "expected_sequence": "beep,piper-utterance-1,piper-utterance-2",
                "confirmed_at": None,
            }
    return {
        "status": "not_heard",
        "attempts": max_attempts,
        "decisions": decisions,
        "attempt_details": attempts,
        "expected_sequence": "beep,piper-utterance-1,piper-utterance-2",
        "confirmed_at": None,
        "reason": "retry_limit_reached",
    }


def run_desktop_audio_transport_acceptance(
    prepared_root: str | Path,
    *,
    evidence_dir: str | Path | None = None,
    work_dir: str | Path | None = None,
    playback: bool = True,
    prompt: Callable[[str], str] = input,
    feedback_backend: Any | None = None,
    wav_player: Any | None = None,
    synthesize_fn: Callable[[str], tuple[bytes, int, int]] | None = None,
    tts_manifest: Mapping[str, object] | None = None,
    fixture_texts: tuple[str, str] | None = None,
    listening_profile: str = "tones",
    profile_metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if listening_profile not in {"tones", "piper_korean"}:
        raise ValueError("listening_profile must be tones or piper_korean")
    repository = Path(__file__).resolve().parents[3]
    prepared = Path(prepared_root).resolve()
    api_key_path = prepared / "secrets" / "device-api-key.txt"
    try:
        api_key = api_key_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise AudioTransportAcceptanceError(
            "prepared root의 secrets/device-api-key.txt를 읽을 수 없습니다"
        ) from exc
    if not api_key or len(api_key) > 4096 or "\n" in api_key or "\r" in api_key:
        raise AudioTransportAcceptanceError("prepared root API key가 유효하지 않습니다")

    run_id = _run_id()
    evidence = Path(evidence_dir).resolve() if evidence_dir else (
        repository / "tmp" / "e0b-audio-runs" / run_id / "evidence"
    ).resolve()
    work = Path(work_dir).resolve() if work_dir else (
        repository / "tmp" / "e0b-audio-runs" / run_id / "work"
    ).resolve()
    if _paths_overlap(evidence, work):
        raise AudioTransportAcceptanceError("work와 evidence 디렉터리는 겹칠 수 없습니다")
    evidence.mkdir(parents=True, exist_ok=False)
    work.mkdir(parents=True, exist_ok=False)

    report_path = evidence / "e0b-audio-transport-report.json"
    server_log_path = evidence / "e0b-audio-server.log"
    client_log_path = evidence / "e0b-audio-client.log"
    resource_manifest_path = evidence / "e0b-audio-resource-manifest.json"
    server_log: list[dict[str, object]] = []
    client_log: list[dict[str, object]] = []
    started_at = _utc_now()
    server: Any | None = None
    server_thread: threading.Thread | None = None
    failure: str | None = None
    resources: list[dict[str, object]] = []
    expected_sequence = (
        "beep,piper-utterance-1,piper-utterance-2"
        if listening_profile == "piper_korean"
        else "beep,tone-low,tone-high"
    )
    manual: dict[str, object] = {
        "status": "not_run",
        "attempts": 0,
        "decisions": [],
        "attempt_details": [],
        "expected_sequence": expected_sequence,
        "confirmed_at": None,
    }
    automated: dict[str, object] = {
        "transport_status": "failed",
        "windows_beep_invoked": False,
        "sapi_status": "excluded",
        "authorized_streams": 0,
        "unauthorized_request_rejected": False,
        "invalid_key_request_rejected": False,
        "unknown_resource_rejected": False,
        "cross_session_resource_rejected": False,
        "wav_valid": False,
        "non_silent": False,
        "distinct_content_hashes": False,
        "content_length_matched": False,
        "etag_matched": False,
        "chunked_consumption": False,
        "path_not_disclosed": False,
        "temporary_files_remaining": 0,
    }

    try:
        state_root = work / "state" / "server"
        datapack_id = "e0b-audio-transport-fixture"
        _write_fixture_datapack(
            state_root / "datapacks",
            work / "fixture",
            datapack_id,
            synthesize=synthesize_fn or BenchSynthesizer(),
            tts_manifest=dict(
                tts_manifest
                or {"engine_id": "e0b-deterministic-bench", "bench_only": True}
            ),
            texts=fixture_texts
            or ("낮은 음 transport fixture", "높은 음 transport fixture"),
        )
        composition = build_e0b_bench_server(state_root, api_key)
        bootstrap = composition.control_plane.bootstrap_existing_datapacks()
        if not bootstrap or bootstrap[0].get("status") not in {"imported", "unchanged"}:
            raise AudioTransportAcceptanceError("fixture datapack bootstrap failed")

        server = make_server(
            "127.0.0.1",
            0,
            composition.app,
            threaded=True,
            request_handler=_QuietRequestHandler,
        )
        port = int(server.server_port)
        base_url = f"http://127.0.0.1:{port}"
        server_thread = threading.Thread(
            target=server.serve_forever,
            name="e0b-audio-transport-server",
            daemon=True,
        )
        server_thread.start()
        server_log.append({"event": "started", "at": _utc_now(), "host": "127.0.0.1"})

        first = _request_json(
            "POST",
            f"{base_url}/api/v1/reading-sessions",
            api_key,
            {"device_id": "desktop-audio-primary", "datapack_id": datapack_id, "viewport_size": 20},
            idempotency_key=f"open-{uuid.uuid4().hex}",
        )
        reading_session_id = _required_string(first, "reading_session_id")
        first_ref = _audio_ref(first)
        second = _request_json(
            "POST",
            f"{base_url}/api/v1/reading-sessions/{reading_session_id}/commands",
            api_key,
            {"command_id": f"next-{uuid.uuid4().hex}", "button": "PAGE_NEXT", "action": "SHORT"},
        )
        second_ref = _audio_ref(second)
        if first_ref == second_ref:
            raise AudioTransportAcceptanceError("two reading positions returned the same audio_ref")

        other = _request_json(
            "POST",
            f"{base_url}/api/v1/reading-sessions",
            api_key,
            {"device_id": "desktop-audio-other", "datapack_id": datapack_id, "viewport_size": 20},
            idempotency_key=f"open-{uuid.uuid4().hex}",
        )
        other_session_id = _required_string(other, "reading_session_id")

        wav_payloads: list[bytes] = []
        for sequence, audio_ref in enumerate((first_ref, second_ref), start=1):
            audio_id = audio_ref.removeprefix("s0-audio:")
            url = f"{base_url}/api/v1/reading-sessions/{reading_session_id}/audio/{audio_id}"
            payload, headers, chunk_count = _fetch_audio(url, api_key)
            analysis = analyze_wav(payload)
            expected_length = int(headers.get("Content-Length", "-1"))
            etag = headers.get("ETag", "").strip('"')
            if expected_length != analysis.content_length:
                raise AudioTransportAcceptanceError("Content-Length did not match streamed bytes")
            if etag != analysis.sha256:
                raise AudioTransportAcceptanceError("ETag did not match content SHA-256")
            if headers.get_content_type() != "audio/wav":
                raise AudioTransportAcceptanceError("audio resource Content-Type was not audio/wav")
            if analysis.peak <= 0 or analysis.rms <= 0:
                raise AudioTransportAcceptanceError("bench WAV was silent")
            resources.append(
                {
                    "sequence": sequence,
                    "audio_id": audio_id,
                    "analysis": asdict(analysis),
                    "chunks_read": chunk_count,
                    "cache_control": headers.get("Cache-Control"),
                    "nosniff": headers.get("X-Content-Type-Options") == "nosniff",
                }
            )
            wav_payloads.append(payload)
            client_log.append(
                {"event": "audio_fetched", "at": _utc_now(), "sequence": sequence, "status": 200}
            )

        unauthorized_status = _request_status(
            f"{base_url}/api/v1/reading-sessions/{reading_session_id}/audio/{first_ref.removeprefix('s0-audio:')}",
            None,
        )
        invalid_key_status = _request_status(
            f"{base_url}/api/v1/reading-sessions/{reading_session_id}/audio/{first_ref.removeprefix('s0-audio:')}",
            "invalid-acceptance-key",
        )
        unknown_status = _request_status(
            f"{base_url}/api/v1/reading-sessions/{reading_session_id}/audio/{'f' * 32}",
            api_key,
        )
        cross_session_status = _request_status(
            f"{base_url}/api/v1/reading-sessions/{other_session_id}/audio/{first_ref.removeprefix('s0-audio:')}",
            api_key,
        )
        hashes = [item["analysis"]["sha256"] for item in resources]
        serialized_public = json.dumps({"first": first, "second": second}, ensure_ascii=False)
        path_tokens = (str(repository), str(work), str(state_root))
        automated.update(
            {
                "authorized_streams": len(resources),
                "unauthorized_request_rejected": unauthorized_status == 401,
                "invalid_key_request_rejected": invalid_key_status == 401,
                "unknown_resource_rejected": unknown_status == 404,
                "cross_session_resource_rejected": cross_session_status == 404,
                "wav_valid": len(resources) == 2,
                "non_silent": all(item["analysis"]["peak"] > 0 for item in resources),
                "distinct_content_hashes": len(set(hashes)) == 2,
                "content_length_matched": True,
                "etag_matched": True,
                "chunked_consumption": all(item["chunks_read"] > 1 for item in resources),
                "path_not_disclosed": not any(token in serialized_public for token in path_tokens),
            }
        )
        required_checks = (
            automated["authorized_streams"] == 2,
            automated["unauthorized_request_rejected"],
            automated["invalid_key_request_rejected"],
            automated["unknown_resource_rejected"],
            automated["cross_session_resource_rejected"],
            automated["wav_valid"],
            automated["non_silent"],
            automated["distinct_content_hashes"],
            automated["content_length_matched"],
            automated["etag_matched"],
            automated["chunked_consumption"],
            automated["path_not_disclosed"],
        )
        if not all(required_checks):
            raise AudioTransportAcceptanceError("one or more automated transport checks failed")
        automated["transport_status"] = "passed"
        server_log.append(
            {
                "event": "request_contract_validated",
                "at": _utc_now(),
                "authorized": [200, 200],
                "missing_key": unauthorized_status,
                "invalid_key": invalid_key_status,
                "unknown_resource": unknown_status,
                "cross_session": cross_session_status,
            }
        )
        client_log.append(
            {
                "event": "negative_boundaries_validated",
                "at": _utc_now(),
                "missing_key": unauthorized_status,
                "invalid_key": invalid_key_status,
                "unknown_resource": unknown_status,
                "cross_session": cross_session_status,
            }
        )

        if playback:
            backend = feedback_backend or WindowsBeepBackend()
            player = wav_player or WindowsMemoryWavPlayer()
            print(
                (
                    "[E0-B.4-D.2] 곧 짧은 beep와 두 개의 한국어 Piper 음성을 재생합니다."
                    if listening_profile == "piper_korean"
                    else "[E0-B.4-D.1] 곧 짧은 beep, 낮은 tone, 높은 tone을 재생합니다."
                ),
                flush=True,
            )

            def play_once() -> None:
                backend.beep(((660, 140),))
                automated["windows_beep_invoked"] = True
                player.play(wav_payloads[0])
                time.sleep(0.4)
                player.play(wav_payloads[1])

            if listening_profile == "piper_korean":
                manual = collect_manual_piper_listening(play_once, prompt)
            else:
                manual = collect_manual_listening(play_once, prompt)
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if server_thread is not None:
            server_thread.join(timeout=5.0)
        server_log.append({"event": "stopped", "at": _utc_now()})

    if failure is None:
        if not playback:
            status = "manual_pending"
        elif manual["status"] == "heard":
            status = "passed"
        else:
            status = "failed"
            failure = "ManualListeningError: 사용자가 실제 청취 성공을 확인하지 않았습니다"
    else:
        status = "failed"

    resource_manifest = {
        "schema_version": 1,
        "resources": resources,
        "raw_audio_included": False,
        "filesystem_paths_included": False,
    }
    report = {
        "schema_version": 2,
        "environment": (
            "desktop_piper_audio_transport"
            if listening_profile == "piper_korean"
            else "desktop_audio_transport"
        ),
        "status": status,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "repository_revision": _git_revision(repository),
        "repository_dirty": _git_dirty(repository),
        "prepared_root_validated": True,
        "audio_profile": {
            "name": listening_profile,
            "sapi_status": "excluded",
            "metadata": dict(profile_metadata or {}),
        },
        "automated": automated,
        "manual_listening": manual,
        "storage": {
            "client_wav_persisted": False,
            "playback_mode": "memory" if playback else "not_run",
        },
        "limitations": (
            [
                "This validates real Piper synthesis, authenticated transport, and desktop memory playback.",
                "Device navigation cancellation and Raspberry Pi playback are follow-up packets.",
            ]
            if listening_profile == "piper_korean"
            else [
                "Bench tones validate transport and audible output, not production Korean TTS quality.",
                "Device navigation cancellation and Raspberry Pi playback are follow-up packets.",
            ]
        ),
        "failure": failure,
    }
    _write_json(resource_manifest_path, resource_manifest)
    _write_json_lines(server_log_path, server_log)
    _write_json_lines(client_log_path, client_log)
    _write_json(report_path, report)
    result = {
        "status": status,
        "evidence_dir": str(evidence),
        "report": str(report_path),
        "automated_transport_status": automated["transport_status"],
        "manual_listening_status": manual["status"],
        "failure": failure,
    }
    if status == "failed":
        raise AudioTransportAcceptanceError(json.dumps(result, ensure_ascii=False))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared_root", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--no-playback", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_desktop_audio_transport_acceptance(
            args.prepared_root,
            evidence_dir=args.evidence_dir,
            work_dir=args.work_dir,
            playback=not args.no_playback,
        )
    except AudioTransportAcceptanceError as exc:
        print(f"[E0-B.4-D.1] FAILED: {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    if result["status"] == "manual_pending":
        print(
            "[E0-B.4-D.1] 자동 transport는 통과했지만 실제 청취는 아직 수행되지 않았습니다.",
            flush=True,
        )
    return 0


def _write_fixture_datapack(
    datapacks_root: Path,
    fixture_root: Path,
    book_id: str,
    *,
    synthesize: Callable[[str], tuple[bytes, int, int]],
    tts_manifest: dict[str, object],
    texts: tuple[str, str],
) -> None:
    fixture_root.mkdir(parents=True, exist_ok=True)
    paths = [fixture_root / "audio-p001-source.bin", fixture_root / "audio-p002-source.bin"]
    result_by_path: dict[str, dict[str, object]] = {}
    for index, (path, text) in enumerate(zip(paths, texts), start=1):
        path.write_bytes(b"fixture")
        result_by_path[str(path.resolve())] = {
            "width": 1000,
            "height": 1400,
            "parsing_res_list": [
                {
                    "block_label": "text",
                    "block_content": text,
                    "block_bbox": [100, 100, 900, 200],
                    "block_id": index,
                    "block_order": 1,
                }
            ],
        }
    page_ir = build_document_ir_from_vl(paths, _FixtureVlAdapter(result_by_path), book_id)
    build_datapack(
        book_id=book_id,
        title="E0-B Audio Transport Fixture",
        page_ir=page_ir,
        synthesize=synthesize,
        tts_manifest=tts_manifest,
        output_dir=datapacks_root,
        system_dir=datapacks_root / "_system",
        log_fn=lambda _message: None,
    )


def _request_json(
    method: str,
    url: str,
    api_key: str,
    body: Mapping[str, object],
    *,
    idempotency_key: str | None = None,
) -> dict[str, object]:
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AudioTransportAcceptanceError("loopback JSON request failed") from exc
    if not isinstance(payload, dict):
        raise AudioTransportAcceptanceError("loopback JSON response was not an object")
    return payload


def _fetch_audio(url: str, api_key: str) -> tuple[bytes, Any, int]:
    request = urllib.request.Request(
        url,
        headers={"X-API-Key": api_key, "Accept": "audio/wav"},
        method="GET",
    )
    chunks: list[bytes] = []
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:
            headers = response.headers
            while True:
                chunk = response.read(1024)
                if not chunk:
                    break
                chunks.append(chunk)
                if sum(map(len, chunks)) > 4 * 1024 * 1024:
                    raise AudioTransportAcceptanceError("stream exceeded the client byte bound")
    except urllib.error.HTTPError as exc:
        raise AudioTransportAcceptanceError(f"audio request returned HTTP {exc.code}") from exc
    return b"".join(chunks), headers, len(chunks)


def _request_status(url: str, api_key: str | None) -> int:
    headers = {"Accept": "audio/wav"}
    if api_key is not None:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def _audio_ref(response: Mapping[str, object]) -> str:
    audio = response.get("audio")
    if not isinstance(audio, Mapping):
        raise AudioTransportAcceptanceError("reading response had no audio object")
    audio_ref = audio.get("audio_ref")
    if not isinstance(audio_ref, str) or not audio_ref.startswith("s0-audio:"):
        raise AudioTransportAcceptanceError("reading response had no opaque audio_ref")
    return audio_ref


def _required_string(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise AudioTransportAcceptanceError(f"response field {key} was missing")
    return value


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _run_id() -> str:
    return f"e0b-audio-transport-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_revision(repository: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _git_dirty(repository: Path) -> bool | None:
    try:
        return bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_json_lines(path: Path, values: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n" for value in values),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
