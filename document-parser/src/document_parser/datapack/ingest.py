"""Ingest job (Scenario A, see [[project_system_architecture_two_scenario]]
and docs/datapack-schema.md): image(s) -> OCR -> flatten -> enumerate every
utterance the live navigator could ever produce -> Piper-synthesize each one
-> write a serving-ready datapack directory. Scenario B's (future) server
only ever reads what this writes -- no OCR or TTS synthesis on its path.

Must run under the GPU venv described in docs/gpu-inference-setup.md for the
OCR step; this module does not switch venvs itself.

Usage:
    python -m document_parser.datapack.ingest my_book p001.png p002.png ... \\
        --title "..." \\
        --piper-model D:/models/piper-korean/ko_KR-kss-medium.onnx \\
        --piper-espeak-data D:/espeak-ng-data
"""

from __future__ import annotations

import argparse
import datetime
import json
import wave
from pathlib import Path
from typing import Any, Callable

from document_parser.accessibility.braille import braille_scrollable_spans
from document_parser.accessibility.flattening import flatten_document
from document_parser.accessibility.speech import (
    focus_item_announcement,
    math_focus_item_to_speech,
    table_cell_announcement,
)
from document_parser.datapack.schema import (
    SCHEMA_VERSION,
    SYSTEM_BOUNDARY_MESSAGES,
    TITLE_UTTERANCE_KEY,
    build_audio_index_entry,
    build_manifest,
    system_message_key,
    utterance_key_for_cell,
    utterance_key_for_item,
    utterance_key_for_span,
)

# text -> (pcm int16 audio bytes, sample_rate, channel_count)
SynthesizeFn = Callable[[str], tuple[bytes, int, int]]


def log(msg: str) -> None:
    """Timestamped, unbuffered progress line -- real wall-clock time, not
    eyeballed. See [[project_gpu_setup]]/the GPU timing survey work for why
    this discipline matters: a prior session mistook `Get-Process`'s
    cumulative CPU-seconds for elapsed time and drew a false conclusion from
    it. Every long-running step in this module logs through this."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def enumerate_utterances(document: dict[str, Any]) -> dict[str, str]:
    """Every distinct spoken text the live `SpeechController` could ever
    produce for this document: one entry per focus item (first-landing
    announcement), one per inline math span inside a TEXT item (좌우 연장
    extension announcement), and one per table cell. Uses
    `focus_item_announcement` -- the same dispatch `SpeechController` calls
    live -- so a pre-synthesized datapack can never say something different
    from what a server driving this same document would say.

    Top-level MATH items get no separate span entries: `braille_scrollable_spans`
    returns `[item]` itself for those, so the item-level entry already covers
    span_index 0's only possible text.
    """
    utterances: dict[str, str] = {}
    for page in document.get("pages", []):
        for item in page.get("focus_items", []):
            utterances[utterance_key_for_item(item)] = focus_item_announcement(item)
            if item.get("kind") == "TEXT":
                for span_index, span in enumerate(braille_scrollable_spans(item)):
                    utterances[utterance_key_for_span(item, span_index)] = math_focus_item_to_speech(span)
            if item.get("kind") == "TABLE":
                for cell in item.get("cells", []):
                    utterances[utterance_key_for_cell(item, cell)] = table_cell_announcement(cell)
    return utterances


def _write_wav(path: Path, audio: bytes, sample_rate: int, channels: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels or 1)
        wav_file.setsampwidth(2)  # int16, matches PiperTtsEngineAdapter's own recording format
        wav_file.setframerate(sample_rate or 22050)
        wav_file.writeframes(audio)


def _duration_ms(audio: bytes, sample_rate: int, channels: int) -> int:
    if not sample_rate or not channels:
        return 0
    frame_count = len(audio) // (2 * channels)  # int16 = 2 bytes/sample
    return round(frame_count / sample_rate * 1000)


def _load_index(index_path: Path) -> dict[str, dict[str, Any]]:
    if not index_path.exists():
        return {}
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    utterances = payload.get("utterances", {})
    return utterances if isinstance(utterances, dict) else {}


def _write_index(index_path: Path, utterances: dict[str, dict[str, Any]]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "utterances": utterances}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def synthesize_all(
    utterances: dict[str, str],
    synthesize: SynthesizeFn,
    pool_dir: Path,
    existing_index: dict[str, dict[str, Any]] | None = None,
    log_fn: Callable[[str], None] = log,
    log_every: int = 20,
) -> dict[str, dict[str, Any]]:
    """Synthesize every utterance not already present in `existing_index`
    with matching text, writing `{pool_dir}/audio/{key}.wav`. Reusing a
    matching cached entry rather than unconditionally re-synthesizing makes
    an interrupted or re-run ingest resumable -- Piper synthesis, not the
    lookup, is the slow step here.
    """
    existing_index = existing_index or {}
    index: dict[str, dict[str, Any]] = {}
    items = sorted(utterances.items())
    total = len(items)
    for i, (key, text) in enumerate(items):
        cached = existing_index.get(key)
        if cached is not None and cached.get("text") == text:
            index[key] = cached
            continue
        audio, sample_rate, channels = synthesize(text)
        wav_relpath = f"audio/{key}.wav"
        _write_wav(pool_dir / wav_relpath, audio, sample_rate, channels)
        index[key] = build_audio_index_entry(text, wav_relpath, _duration_ms(audio, sample_rate, channels), sample_rate)
        if (i + 1) % log_every == 0 or (i + 1) == total:
            log_fn(f"synthesized {i + 1}/{total} utterances")
    return index


def ensure_system_pool(
    synthesize: SynthesizeFn,
    system_dir: Path,
    log_fn: Callable[[str], None] = log,
) -> dict[str, dict[str, Any]]:
    """Synthesize the 16 book-independent boundary messages into the shared
    `_system` pool, once ever -- idempotent, since these never depend on any
    book's content (see docs/datapack-schema.md)."""
    index_path = system_dir / "audio_index.json"
    existing = _load_index(index_path)
    utterances = {system_message_key(text): text for text in SYSTEM_BOUNDARY_MESSAGES}
    index = synthesize_all(utterances, synthesize, system_dir, existing, log_fn)
    _write_index(index_path, index)
    return index


def build_datapack(
    book_id: str,
    title: str,
    page_ir: dict[str, Any],
    synthesize: SynthesizeFn,
    tts_manifest: dict[str, Any],
    output_dir: Path,
    system_dir: Path,
    log_fn: Callable[[str], None] = log,
) -> Path:
    """Core, OCR-independent half of ingest: takes an already-produced Page
    IR (see `document_parser.serialization.build_document_ir_from_vl`) and
    writes a complete serving-ready datapack directory. Kept separate from
    `main()` so it's testable against a hand-built Page IR fixture without
    real model weights -- the same pattern `tests/unit/test_vl_page_ir.py`
    already uses for the OCR integration itself.
    """
    validation = page_ir.get("validation_summary")
    if not isinstance(validation, dict) or not validation.get("schema_valid", False):
        raise ValueError(
            f"Refusing to build a datapack from an invalid Page IR (book_id={book_id!r}): "
            f"validation_summary={validation!r}. Per flatten_document's docstring, callers "
            "must not proceed on schema_valid: false."
        )

    log_fn(f"flattening page IR for {book_id!r}")
    document = flatten_document(page_ir)
    page_ids = [str(page["page_id"]) for page in document.get("pages", [])]
    log_fn(f"flattened: {len(page_ids)} pages")

    utterances = enumerate_utterances(document)
    utterances[TITLE_UTTERANCE_KEY] = title  # book-selection screen speaks this without live synthesis
    log_fn(f"enumerated {len(utterances)} distinct utterances (including title)")

    book_dir = output_dir / book_id
    audio_index_path = book_dir / "audio_index.json"
    existing_index = _load_index(audio_index_path)
    audio_index = synthesize_all(utterances, synthesize, book_dir, existing_index, log_fn)
    log_fn("book audio synthesis complete")

    ensure_system_pool(synthesize, system_dir, log_fn)
    log_fn("system boundary-message pool up to date")

    manifest = build_manifest(
        book_id=book_id,
        title=title,
        page_ids=page_ids,
        created_at=datetime.datetime.now().isoformat(),
        engine_manifest=page_ir.get("engine_manifest", {}),
        tts_manifest=tts_manifest,
        validation_summary=validation,
        title_audio=audio_index.get(TITLE_UTTERANCE_KEY, {}).get("wav"),
    )

    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (book_dir / "document.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_index(audio_index_path, audio_index)
    log_fn(f"datapack written: {book_dir}")
    return book_dir


def make_piper_synthesize_fn(voice: Any) -> SynthesizeFn:
    def synthesize(text: str) -> tuple[bytes, int, int]:
        chunks = list(voice.synthesize(text))
        if not chunks:
            return b"", 22050, 1
        sample_rate = chunks[0].sample_rate
        channels = chunks[0].sample_channels
        audio = b"".join(chunk.audio_int16_bytes for chunk in chunks)
        return audio, sample_rate, channels

    return synthesize


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book_id")
    parser.add_argument("images", nargs="+", help="Page image paths, any order (sorted before OCR).")
    parser.add_argument("--title", default=None, help="Display title; defaults to book_id.")
    parser.add_argument("--output-dir", default="datapacks")
    parser.add_argument("--system-dir", default=None, help="Defaults to <output-dir>/_system.")
    parser.add_argument("--model-home", default=None, help="PaddleOCR-VL model_home; see docs/gpu-inference-setup.md.")
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--piper-model", required=True)
    parser.add_argument("--piper-espeak-data", required=True)
    parser.add_argument("--piper-use-cuda", action="store_true")
    args = parser.parse_args()

    from document_parser.accessibility.adapters.tts_engine import load_piper_voice
    from document_parser.ocr.paddleocr_vl_adapter import PaddleOcrVlAdapter
    from document_parser.serialization import build_document_ir_from_vl

    output_dir = Path(args.output_dir)
    system_dir = Path(args.system_dir) if args.system_dir else output_dir / "_system"
    image_paths = [Path(p) for p in args.images]

    log(f"ingest start: book_id={args.book_id!r}, {len(image_paths)} images")

    log("loading Piper voice")
    voice = load_piper_voice(args.piper_model, args.piper_espeak_data, use_cuda=args.piper_use_cuda)
    synthesize = make_piper_synthesize_fn(voice)

    log(f"OCR: building document IR ({args.device})")
    adapter = PaddleOcrVlAdapter(
        model_home=Path(args.model_home) if args.model_home else None,
        device=args.device,
    )
    page_ir = build_document_ir_from_vl(sorted(image_paths), adapter, args.book_id)
    log("OCR complete")

    tts_manifest = {
        "engine_id": "piper",
        "voice": Path(args.piper_model).stem,
        "use_cuda": args.piper_use_cuda,
    }
    book_dir = build_datapack(
        book_id=args.book_id,
        title=args.title or args.book_id,
        page_ir=page_ir,
        synthesize=synthesize,
        tts_manifest=tts_manifest,
        output_dir=output_dir,
        system_dir=system_dir,
    )
    log(f"ingest done: {book_dir}")


if __name__ == "__main__":
    main()
