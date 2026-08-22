"""Runnable entry point: wires a Page IR document through `SpeechController`
to real TTS audio (Piper, played on whatever speakers are connected to the
Raspberry Pi/PC -- see [[project-braille-phase3-design-decisions]]'s
optimistic-update note for why audio never runs on the STM board) and a
console preview of the braille frame (real Unicode braille characters,
standing in for the physical STM display, since the Phase 5 hardware
transport layer doesn't exist yet -- see accessibility/__init__.py).

Usage:
    python -m document_parser.accessibility.cli tests/fixtures/accessibility/p019.json
    python -m document_parser.accessibility.cli p019.json --piper-model D:/models/piper-korean/ko_KR-kss-medium.onnx --piper-espeak-data D:/espeak-ng-data
    python -m document_parser.accessibility.cli p019.json --no-audio   # console-only, no piper/sounddevice needed

Commands at the prompt: up/down/left/right (SHORT), ul/dl/ll/rl (LONG),
pn/pp (dedicated page-turn buttons -- next/previous page, always SHORT),
q to quit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable, TextIO

from document_parser.accessibility.adapters.tts_engine import PiperTtsEngineAdapter, TtsEngineAdapter
from document_parser.accessibility.application.speech_controller import SpeechController
from document_parser.accessibility.braille.braille_presenter import BraillePresenter
from document_parser.accessibility.domain.commands import NavigationCommand
from document_parser.accessibility.domain.navigation_state import NavigationState
from document_parser.accessibility.flattening import flatten_document

_COMMANDS: dict[str, NavigationCommand] = {
    "u": NavigationCommand("UP", "SHORT"), "up": NavigationCommand("UP", "SHORT"),
    "d": NavigationCommand("DOWN", "SHORT"), "down": NavigationCommand("DOWN", "SHORT"),
    "l": NavigationCommand("LEFT", "SHORT"), "left": NavigationCommand("LEFT", "SHORT"),
    "r": NavigationCommand("RIGHT", "SHORT"), "right": NavigationCommand("RIGHT", "SHORT"),
    "ul": NavigationCommand("UP", "LONG"),
    "dl": NavigationCommand("DOWN", "LONG"),
    "ll": NavigationCommand("LEFT", "LONG"),
    "rl": NavigationCommand("RIGHT", "LONG"),
    "pn": NavigationCommand("PAGE_NEXT", "SHORT"),
    "pp": NavigationCommand("PAGE_PREVIOUS", "SHORT"),
}


class ConsoleTtsEngineAdapter:
    """No-audio stand-in for `PiperTtsEngineAdapter`: prints what would be
    spoken instead of synthesizing it, so this CLI is runnable without a
    Piper model file or a sound device present (sandboxes, CI, a quick
    smoke check). `on_complete` fires immediately since there's no real
    playback duration to wait out -- continuous reading still advances
    correctly, just without any delay between items."""

    def __init__(self) -> None:
        self._on_complete: Callable[[int], None] | None = None

    def on_complete(self, callback: Callable[[int], None]) -> None:
        self._on_complete = callback

    def speak(self, text: str, generation: int) -> None:
        print(f"[TTS] {text}")
        if self._on_complete is not None:
            self._on_complete(generation)

    def cancel(self) -> None:
        pass


def render_braille_frame(frame: dict[str, object]) -> str:
    """Real Unicode braille characters (U+2800 block): `cell_to_int()`'s
    wire-format bit packing (bit0=dot1 ... bit5=dot6) already matches
    Unicode's own braille dot-to-bit convention exactly, so no remapping
    is needed -- `chr(0x2800 + value)` is correct as-is."""
    cells = frame.get("cells") or []
    if not cells:
        return "(점자 없음)"
    dots = "".join(chr(0x2800 + value) for value in cells)
    left = "◂" if frame.get("has_previous") else " "
    right = "▸" if frame.get("has_next") else " "
    return f"{left}{dots}{right}"


class BrailleFrameRecorder:
    """Debugging aid: writes every distinct braille frame (deduped by
    content, since e.g. a boundary press that didn't move produces the same
    frame again) to a numbered `.json` file -- source id/offset/dots/Unicode
    rendering -- so a test run leaves an inspectable record, the same way
    `PiperTtsEngineAdapter(record_dir=...)` does for audio."""

    def __init__(self, output_dir: str | Path) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0
        self._last_signature: tuple[object, ...] | None = None
        self.recorded_files: list[Path] = []

    def record(self, frame: dict[str, object]) -> Path | None:
        signature = (frame.get("source_id"), frame.get("offset"), tuple(frame.get("cells") or ()))
        if signature == self._last_signature:
            return None
        self._last_signature = signature
        self._counter += 1
        path = self._dir / f"braille_{self._counter:04d}.json"
        payload = {
            "source_id": frame.get("source_id"),
            "offset": frame.get("offset"),
            "viewport_size": frame.get("viewport_size"),
            "total_cell_count": frame.get("total_cell_count"),
            "has_previous": frame.get("has_previous"),
            "has_next": frame.get("has_next"),
            "cells": frame.get("cells"),
            "unicode": render_braille_frame(frame),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.recorded_files.append(path)
        return path


def load_document(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return flatten_document(payload)


def build_engine(args: argparse.Namespace) -> TtsEngineAdapter:
    if args.no_audio or not (args.piper_model and args.piper_espeak_data):
        print(
            "(오디오 비활성화: --piper-model/--piper-espeak-data 옵션 또는 "
            "PIPER_KOREAN_MODEL_PATH/PIPER_ESPEAK_DATA_DIR 환경변수를 지정하면 "
            "실제 Piper 음성이 재생됩니다.)"
        )
        return ConsoleTtsEngineAdapter()
    return PiperTtsEngineAdapter(
        args.piper_model, args.piper_espeak_data,
        record_dir=args.record_audio_dir, play_audio=not args.no_speaker,
    )


def run(
    document: dict[str, object],
    engine: TtsEngineAdapter,
    viewport_size: int,
    input_stream: TextIO = sys.stdin,
    braille_recorder: BrailleFrameRecorder | None = None,
) -> None:
    state = NavigationState(document_id=str(document.get("document_id", "doc")), page_index=0, node_index=0)
    controller = SpeechController(document, state, engine, braille_presenter=BraillePresenter(viewport_size=viewport_size))
    controller.speak_current()
    print(render_braille_frame(controller.braille_frame))
    if braille_recorder is not None:
        braille_recorder.record(controller.braille_frame)
    print("명령: up/down/left/right (SHORT), ul/dl/ll/rl (LONG), pn/pp(페이지 넘김), q(종료)")

    for line in input_stream:
        token = line.strip().lower()
        if not token:
            continue
        if token in ("q", "quit", "exit"):
            break
        command = _COMMANDS.get(token)
        if command is None:
            print(f"알 수 없는 명령: {token!r}")
            continue
        controller.handle_command(command)
        state = controller.state
        print(
            f"[state] mode={state.mode} page={state.page_index} node={state.node_index} "
            f"table=({state.table_row},{state.table_column}) span={state.math_span_index} "
            f"offset={state.braille_offset} gen={state.generation}"
        )
        print(render_braille_frame(controller.braille_frame))
        if braille_recorder is not None:
            braille_recorder.record(controller.braille_frame)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles often default to a non-UTF-8 codepage (e.g. cp949 on a
    # Korean-locale machine), which cannot encode the Unicode braille block
    # (U+2800+) `render_braille_frame` prints -- crashing with a
    # UnicodeEncodeError instead of just looking wrong. Force UTF-8 so this
    # runs regardless of the host console's default codepage; `errors="replace"`
    # keeps it non-fatal even on a terminal that can't render the glyphs.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("document", type=Path, help="Path to a Page IR JSON file (e.g. tests/fixtures/accessibility/p019.json)")
    parser.add_argument("--piper-model", default=os.environ.get("PIPER_KOREAN_MODEL_PATH", ""))
    parser.add_argument("--piper-espeak-data", default=os.environ.get("PIPER_ESPEAK_DATA_DIR", ""))
    parser.add_argument("--no-audio", action="store_true", help="Skip real TTS playback; print what would be spoken instead.")
    parser.add_argument("--viewport-size", type=int, default=20)
    parser.add_argument(
        "--record-audio-dir", type=Path, default=None,
        help="If set (and real Piper audio is active), also write each synthesized utterance to a numbered .wav "
             "(+ matching .txt of the source text) in this directory, for offline debugging/listening.",
    )
    parser.add_argument(
        "--record-braille-dir", type=Path, default=None,
        help="If set, also write each distinct braille frame to a numbered .json (cells + Unicode rendering) "
             "in this directory, for offline debugging.",
    )
    parser.add_argument(
        "--no-speaker", action="store_true",
        help="Synthesize (and still record, if --record-audio-dir is set) but skip live sounddevice playback.",
    )
    args = parser.parse_args(argv)

    document = load_document(args.document)
    engine = build_engine(args)
    braille_recorder = BrailleFrameRecorder(args.record_braille_dir) if args.record_braille_dir else None
    run(document, engine, args.viewport_size, braille_recorder=braille_recorder)
    # The last speak() runs in a daemon thread (PiperTtsEngineAdapter); without
    # this, the process can exit (killing that thread) before a pending
    # --record-audio-dir .wav write actually lands on disk.
    wait_until_idle = getattr(engine, "wait_until_idle", None)
    if callable(wait_until_idle):
        wait_until_idle()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
