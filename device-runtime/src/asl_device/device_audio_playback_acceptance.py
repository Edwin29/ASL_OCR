"""Integrated Piper/S0/Device reading-audio acceptance for the Desktop host."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from document_parser.accessibility.adapters.tts_engine import load_piper_voice
from document_parser.datapack.ingest import make_piper_synthesize_fn
from document_parser.server.e0b_bench_server import build_e0b_bench_server
from werkzeug.serving import make_server

from .adapters.http_s0 import S0HttpClient, S0ReadingHttpAdapter
from .adapters.reading_audio import S0AudioResourceHttpAdapter, SoundDeviceWavPlayer
from .desktop_audio_transport_acceptance import (
    AudioTransportAcceptanceError,
    _QuietRequestHandler,
    _write_fixture_datapack,
)
from .reading_audio import AudioResourceCache, ReadingAudioController
from .types import DatapackId, DeviceControl, DeviceId, InputAction

_DEFAULT_MODEL = Path(r"D:\models\piper-korean\ko_KR-kss-medium.onnx")
_DEFAULT_ESPEAK_DATA = Path(r"D:\espeak-ng-data")
_TEXTS = (
    "첫 번째 페이지 음성입니다. 장치 재생 검증을 시작합니다.",
    "두 번째 페이지 음성입니다. 이전 음성은 중단되었습니다.",
)


class _EventSink:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


class _CountingResource:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.fetches = 0

    def fetch(self, reading_session_id, audio_ref, cancelled):
        self.fetches += 1
        return self.delegate.fetch(reading_session_id, audio_ref, cancelled)


class _AutomatedPlayer:
    def __init__(self) -> None:
        self.started = 0
        self.completed = 0
        self.interrupted = 0
        self.closed = False

    def play(self, resource, cancelled):
        self.started += 1
        deadline = time.monotonic() + 0.12
        while time.monotonic() < deadline:
            if cancelled():
                self.interrupted += 1
                return
            time.sleep(0.005)
        self.completed += 1

    def stop(self):
        return

    def close(self):
        self.closed = True


def run_device_audio_playback_acceptance(
    prepared_root: str | Path,
    *,
    model_path: str | Path,
    espeak_data_dir: str | Path,
    playback: bool,
    evidence_dir: str | Path | None = None,
    prompt=input,
) -> dict[str, object]:
    repository = Path(__file__).resolve().parents[3]
    prepared = Path(prepared_root).resolve()
    api_key = (prepared / "secrets" / "device-api-key.txt").read_text(encoding="utf-8").strip()
    model = Path(model_path).resolve()
    espeak = Path(espeak_data_dir).resolve()
    if not api_key or not model.is_file() or not model.with_suffix(model.suffix + ".json").is_file():
        raise AudioTransportAcceptanceError("API key 또는 Piper model bundle이 준비되지 않았습니다")
    if not espeak.is_dir():
        raise AudioTransportAcceptanceError("Piper eSpeak data 디렉터리가 없습니다")
    run_id = f"e0b-device-audio-playback-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    evidence = Path(evidence_dir).resolve() if evidence_dir else repository / "tmp" / "e0b-audio-runs" / run_id / "evidence"
    work = evidence.parent / "work"
    evidence.mkdir(parents=True, exist_ok=False)
    work.mkdir(parents=True, exist_ok=False)

    voice = load_piper_voice(model, espeak, use_cuda=False)
    datapack_id = "e0b-device-audio-playback-fixture"
    _write_fixture_datapack(
        work / "state" / "datapacks",
        work / "fixture",
        datapack_id,
        synthesize=make_piper_synthesize_fn(voice),
        tts_manifest={"engine_id": "piper", "voice": model.stem, "use_cuda": False},
        texts=_TEXTS,
    )
    composition = build_e0b_bench_server(work / "state", api_key)
    composition.control_plane.bootstrap_existing_datapacks()
    server = make_server(
        "127.0.0.1", 0, composition.app, threaded=True, request_handler=_QuietRequestHandler
    )
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    sink = _EventSink()
    player = SoundDeviceWavPlayer() if playback else _AutomatedPlayer()
    resource = _CountingResource(S0AudioResourceHttpAdapter(base_url, api_key))
    cache = AudioResourceCache(max_bytes=8 * 1024 * 1024, max_entries=4)
    controller = ReadingAudioController(resource, player, cache, feedback=sink)
    reading = S0ReadingHttpAdapter(S0HttpClient(base_url, api_key))
    snapshots = []
    manual = {"status": "not_run", "component_checks": {}}
    try:
        current = reading.open(
            DeviceId("desktop-reading-audio"), DatapackId(datapack_id), 20, f"open-{uuid.uuid4().hex}"
        )
        snapshots.append(current)
        controller.present(current)
        if not controller.wait_idle(15):
            raise AudioTransportAcceptanceError("generation 0 playback did not settle")

        controller.interrupt()
        current = reading.send_command(
            current.reading_session_id, f"next-{uuid.uuid4().hex}", DeviceControl.PAGE_NEXT, InputAction.SHORT
        )
        snapshots.append(current)
        controller.present(current)
        time.sleep(0.75 if playback else 0.03)
        controller.interrupt()
        current = reading.send_command(
            current.reading_session_id, f"prev-{uuid.uuid4().hex}", DeviceControl.PAGE_PREVIOUS, InputAction.SHORT
        )
        snapshots.append(current)
        controller.present(current)
        if not controller.wait_idle(15):
            raise AudioTransportAcceptanceError("cache revisit playback did not settle")

        controller.interrupt()
        current = reading.send_command(
            current.reading_session_id, f"rapid-next-{uuid.uuid4().hex}", DeviceControl.PAGE_NEXT, InputAction.SHORT
        )
        snapshots.append(current)
        controller.present(current)
        time.sleep(0.10 if playback else 0.01)
        controller.interrupt()
        current = reading.send_command(
            current.reading_session_id, f"rapid-prev-{uuid.uuid4().hex}", DeviceControl.PAGE_PREVIOUS, InputAction.SHORT
        )
        snapshots.append(current)
        controller.present(current)
        if not controller.wait_idle(15):
            raise AudioTransportAcceptanceError("latest playback did not settle")

        codes = [event.code.value for event in sink.events]
        automated = {
            "generations_presented": [snapshot.generation for snapshot in snapshots],
            "fetch_count": resource.fetches,
            "cache_hits": codes.count("reading_audio_cache_hit"),
            "playback_starts": codes.count("reading_audio_playback_started"),
            "playback_completions": codes.count("reading_audio_playback_completed"),
            "interruptions_observed": codes.count("reading_audio_interrupted"),
            "failures": codes.count("reading_audio_failed"),
            "cache_peak_bytes": cache.total_bytes,
            "cache_limit_bytes": cache.max_bytes,
            "client_wav_persisted": False,
        }
        if (
            automated["generations_presented"] != [0, 1, 2, 3, 4]
            or resource.fetches != 2
            or automated["cache_hits"] < 2
            or automated["failures"] != 0
            or cache.total_bytes > cache.max_bytes
        ):
            raise AudioTransportAcceptanceError("integrated audio invariants did not pass")
        if playback:
            checks = {}
            questions = (
                ("initial_intelligible", "첫 페이지 Piper 음성이 명료하게 들렸습니까? [yes/no]: "),
                ("previous_stopped", "페이지 이동 시 두 번째 음성이 중간에 중단됐습니까? [yes/no]: "),
                ("latest_matches_cursor", "이동 후 들린 음성이 현재 첫 페이지와 일치합니까? [yes/no]: "),
                ("cache_revisit_correct", "재방문한 첫 페이지 음성이 정상적으로 들렸습니까? [yes/no]: "),
                ("no_stale_audio", "빠른 연속 이동 뒤 이전 페이지 음성이 남지 않았습니까? [yes/no]: "),
            )
            for name, question in questions:
                answer = ""
                while answer not in {"yes", "no"}:
                    answer = prompt(question).strip().lower()
                checks[name] = answer == "yes"
            decision = ""
            choices = {"heard", "not-heard"} if all(checks.values()) else {"not-heard"}
            while decision not in choices:
                decision = prompt(f"통합 청취 결과를 입력하세요 [{'heard/not-heard' if all(checks.values()) else 'not-heard'}]: ").strip().lower()
            manual = {"status": "heard" if decision == "heard" else "not_heard", "component_checks": checks}
        status = "passed" if manual["status"] == "heard" else "manual_pending" if not playback else "failed"
        report = {
            "schema_version": 1,
            "environment": "desktop_integrated_reading_audio",
            "status": status,
            "automated": automated,
            "manual_listening": manual,
            "evidence_dir": str(evidence),
        }
        (evidence / "e0b-device-audio-events.jsonl").write_text(
            "".join(
                json.dumps(
                    {"code": event.code.value, "at_monotonic": event.at_monotonic, "details": dict(event.details)},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ) + "\n"
                for event in sink.events
            ),
            encoding="utf-8",
        )
        (evidence / "e0b-device-audio-http-summary.json").write_text(
            json.dumps({"fetch_count": resource.fetches, "authenticated": True}, indent=2) + "\n", encoding="utf-8"
        )
        (evidence / "e0b-device-audio-cache-summary.json").write_text(
            json.dumps({"entries": cache.entry_count, "bytes": cache.total_bytes, "limit_bytes": cache.max_bytes}, indent=2) + "\n",
            encoding="utf-8",
        )
        (evidence / "e0b-device-audio-playback-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return report
    finally:
        controller.close()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared_root", type=Path)
    parser.add_argument("--piper-model", type=Path, default=Path(os.environ.get("E0B_PIPER_MODEL", _DEFAULT_MODEL)))
    parser.add_argument("--piper-espeak-data", type=Path, default=Path(os.environ.get("E0B_PIPER_ESPEAK_DATA", _DEFAULT_ESPEAK_DATA)))
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--no-playback", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_device_audio_playback_acceptance(
            args.prepared_root,
            model_path=args.piper_model,
            espeak_data_dir=args.piper_espeak_data,
            playback=not args.no_playback,
            evidence_dir=args.evidence_dir,
        )
    except (AudioTransportAcceptanceError, OSError, ValueError, RuntimeError) as exc:
        print(f"[E0-B.4-D.3] FAILED: {type(exc).__name__}: {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0 if result["status"] in {"passed", "manual_pending"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
