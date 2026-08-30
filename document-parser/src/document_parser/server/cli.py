"""Runnable console demo for Scenario B (serving, see docs/datapack-schema.md):
loads a datapack and lets you drive it interactively via `DatapackSession`,
the same transport-agnostic core a future HTTP/WebSocket/serial layer would
call through `handle_wire_command`. This CLI *is* a transport -- just a
manual one (stdin/stdout) -- so running it end to end is a real proof that
`SessionStore`/`DatapackSession`/`DatapackTtsEngineAdapter` actually work
together against a real datapack, not just against unit-test fakes.

Mirrors `accessibility.cli`'s shape (same command vocabulary, same braille-
frame rendering) since that's this project's established console-demo
pattern. The key difference: that CLI drives a live `SpeechController`
directly and synthesizes/plays TTS on the spot; this one drives the exact
same navigation logic through a loaded datapack, so instead of synthesizing
anything, each turn reports which pre-synthesized wav file *would* be sent
to the hardware (and can optionally actually play it locally with
`--play-audio`, for a sighted developer's own sanity-check --
`sounddevice` is only imported if that flag is passed).

Usage:
    python -m document_parser.server.cli datapacks/ my_book
    python -m document_parser.server.cli datapacks/ my_book --play-audio
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path
from typing import Any, TextIO

from document_parser.accessibility.cli import render_braille_frame
from document_parser.accessibility.domain.commands import NavigationCommand
from document_parser.server.session import DatapackSession
from document_parser.server.store import SessionStore

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
    "c": NavigationCommand("CONFIRM", "SHORT"),
    "cl": NavigationCommand("CONFIRM", "LONG"),
}


def describe_audio(audio: dict[str, Any] | None) -> str:
    """`audio` is `None` exactly when this turn was a silent braille-only
    scroll (좌우 연장 Decision 2: pure within-span/within-cell window
    movement never re-announces) -- see `DatapackSession.audio`'s docstring.
    Spelling that out here instead of just staying silent makes it obvious
    this is expected wire behavior, not the demo dropping something."""
    if audio is None:
        return "(무음 -- 점자 창만 이동, 새로 재생할 오디오 없음)"
    return f"[AUDIO] {audio['text']}  ({audio['wav']})"


def play_wav(path: str) -> None:
    import numpy as np
    import sounddevice as sd  # deferred: optional dependency, only needed with --play-audio

    with wave.open(path, "rb") as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16)
        channels = wav_file.getnchannels()
        if channels > 1:
            audio = audio.reshape(-1, channels)
        sd.play(audio, samplerate=wav_file.getframerate())
        sd.wait()


def _report_turn(result: dict[str, Any], play_audio: bool) -> None:
    state = result["state"]
    print(
        f"[state] mode={state.mode} page={state.page_index} node={state.node_index} "
        f"table=({state.table_row},{state.table_column}) span={state.math_span_index} "
        f"offset={state.braille_offset} gen={state.generation}"
    )
    print(render_braille_frame(result["braille_frame"]))
    audio = result["audio"]
    print(describe_audio(audio))
    if play_audio and audio is not None:
        play_wav(audio["wav"])


def run(session: DatapackSession, input_stream: TextIO = sys.stdin, play_audio: bool = False) -> None:
    _report_turn({"state": session.state, "braille_frame": session.braille_frame, "audio": session.audio}, play_audio)
    print(
        "명령: up/down/left/right (SHORT), ul/dl/ll/rl (LONG), pn/pp(페이지 넘김), c(확인/리플레이), "
        "cl(데이터팩 선택 화면으로 -- 이 CLI에는 그 화면이 없어 '아직 지원되지 않는 버튼'으로 처리됨), q(종료)"
    )

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
        result = session.handle_button(command)
        _report_turn(result, play_audio)


def main(argv: list[str] | None = None) -> int:
    # Same rationale as accessibility.cli.main(): force UTF-8 so the Unicode
    # braille block (U+2800+) doesn't crash a non-UTF-8 Windows console.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("datapacks_dir", type=Path, help="Directory containing {book_id}/ and _system/ (see docs/datapack-schema.md).")
    parser.add_argument("book_id")
    parser.add_argument("--session-id", default="cli-session", help="Passed to SessionStore; only matters if you run several sessions against the same store.")
    parser.add_argument("--play-audio", action="store_true", help="Actually play each turn's pre-synthesized wav locally (needs `sounddevice`).")
    args = parser.parse_args(argv)

    store = SessionStore(args.datapacks_dir)
    session = store.get_or_create_session(args.session_id, args.book_id)
    run(session, play_audio=args.play_audio)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
