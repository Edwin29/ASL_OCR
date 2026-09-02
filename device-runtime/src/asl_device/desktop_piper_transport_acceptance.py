"""Real Korean Piper synthesis, S0 transport, and Desktop listening acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from document_parser.accessibility.adapters.tts_engine import load_piper_voice
from document_parser.datapack.ingest import make_piper_synthesize_fn

from .desktop_audio_transport_acceptance import (
    AudioTransportAcceptanceError,
    run_desktop_audio_transport_acceptance,
)

_DEFAULT_MODEL = Path(r"D:\models\piper-korean\ko_KR-kss-medium.onnx")
_DEFAULT_ESPEAK_DATA = Path(r"D:\espeak-ng-data")
_UTTERANCES = (
    "첫 번째 음성입니다. 데스크탑 파이퍼 검증을 시작합니다.",
    "두 번째 음성입니다. 다음 페이지로 이동했습니다.",
)


def run_desktop_piper_transport_acceptance(
    prepared_root: str | Path,
    *,
    model_path: str | Path,
    espeak_data_dir: str | Path,
    evidence_dir: str | Path | None = None,
    work_dir: str | Path | None = None,
    playback: bool = True,
) -> dict[str, object]:
    model = Path(model_path).resolve()
    config = model.with_suffix(model.suffix + ".json")
    espeak = Path(espeak_data_dir).resolve()
    if not model.is_file() or not config.is_file():
        raise AudioTransportAcceptanceError("Piper model 또는 .onnx.json 설정 파일이 없습니다")
    if not espeak.is_dir():
        raise AudioTransportAcceptanceError("Piper eSpeak data 디렉터리가 없습니다")

    voice = load_piper_voice(model, espeak, use_cuda=False)
    synthesize = make_piper_synthesize_fn(voice)
    return run_desktop_audio_transport_acceptance(
        prepared_root,
        evidence_dir=evidence_dir,
        work_dir=work_dir,
        playback=playback,
        synthesize_fn=synthesize,
        tts_manifest={
            "engine_id": "piper",
            "voice": model.stem,
            "use_cuda": False,
        },
        fixture_texts=_UTTERANCES,
        listening_profile="piper_korean",
        profile_metadata={
            "voice": model.stem,
            "model_sha256": _sha256_file(model),
            "model_bytes": model.stat().st_size,
            "config_sha256": _sha256_file(config),
            "client_wav_persisted": False,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared_root", type=Path)
    parser.add_argument(
        "--piper-model",
        type=Path,
        default=Path(os.environ.get("E0B_PIPER_MODEL", _DEFAULT_MODEL)),
    )
    parser.add_argument(
        "--piper-espeak-data",
        type=Path,
        default=Path(os.environ.get("E0B_PIPER_ESPEAK_DATA", _DEFAULT_ESPEAK_DATA)),
    )
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--no-playback", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_desktop_piper_transport_acceptance(
            args.prepared_root,
            model_path=args.piper_model,
            espeak_data_dir=args.piper_espeak_data,
            evidence_dir=args.evidence_dir,
            work_dir=args.work_dir,
            playback=not args.no_playback,
        )
    except (AudioTransportAcceptanceError, ValueError, OSError) as exc:
        print(f"[E0-B.4-D.2] FAILED: {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    if result["status"] == "manual_pending":
        print(
            "[E0-B.4-D.2] 실제 Piper 합성·전송은 통과했지만 한국어 청취는 아직 수행되지 않았습니다.",
            flush=True,
        )
    return 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
