"""Secret-safe semantic feedback sinks for the E0-Core local host."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from typing import Protocol, TextIO

from asl_device.app_config import LaptopAudioConfig
from asl_device.events import FeedbackEvent
from asl_device.events import FeedbackCode
from asl_device.types import ReadingSnapshot


_JSONL_OUTPUT_LOCK = threading.Lock()


class JsonLineFeedbackSink:
    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def emit(self, event: FeedbackEvent) -> None:
        payload = {
            "type": "feedback",
            "code": event.code.value,
            "at_monotonic": event.at_monotonic,
            "details": dict(event.details),
        }
        with _JSONL_OUTPUT_LOCK:
            self.stream.write(
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n"
            )
            self.stream.flush()


class JsonLineReadingPresenter:
    """Emit changed Server-backed reading snapshots for console acceptance."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout
        self._last_snapshot: ReadingSnapshot | None = None
        self._closed = False

    def present(self, snapshot: ReadingSnapshot | None) -> None:
        if self._closed or snapshot is None or snapshot == self._last_snapshot:
            return
        payload = {
            "type": "reading_snapshot",
            "reading_session_id": snapshot.reading_session_id.value,
            "datapack_id": snapshot.datapack_id.value,
            "cursor": dict(snapshot.cursor),
            "source_text": snapshot.source_text,
            "spoken_text": snapshot.spoken_text,
            "braille_cells": list(snapshot.braille_cells),
            "audio_ref": snapshot.audio_ref,
        }
        try:
            with _JSONL_OUTPUT_LOCK:
                self.stream.write(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
                )
                self.stream.flush()
        except Exception:
            # Presentation is diagnostic and cannot roll back ACK or reading state.
            return
        self._last_snapshot = snapshot

    def close(self) -> None:
        self._closed = True


class MemoryFeedbackSink:
    def __init__(self) -> None:
        self.events: list[FeedbackEvent] = []

    def emit(self, event: FeedbackEvent) -> None:
        self.events.append(event)


class CompositeFeedbackSink:
    """Fan semantic events out while keeping each renderer independently safe."""

    def __init__(self, *sinks: object) -> None:
        self.sinks = tuple(sinks)

    def emit(self, event: FeedbackEvent) -> None:
        for sink in self.sinks:
            try:
                sink.emit(event)
            except Exception:
                continue

    def close(self) -> None:
        for sink in reversed(self.sinks):
            close = getattr(sink, "close", None)
            if close is not None:
                close()


class AudioFeedbackBackend(Protocol):
    def beep(self, pattern: tuple[tuple[int, int], ...]) -> None: ...

    def speak(self, text: str) -> None: ...


class WindowsAudioBackend:
    """Windows built-in beep and SAPI speech without a runtime package."""

    _SPEAK_SCRIPT = (
        "Add-Type -AssemblyName System.Speech; "
        "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$speaker.Speak([string]$args[0])"
    )

    def __init__(self, powershell_executable: str = "powershell.exe") -> None:
        if os.name != "nt":
            raise RuntimeError("windows_audio feedback is available only on Windows")
        import winsound

        self._winsound = winsound
        self.powershell_executable = powershell_executable

    def beep(self, pattern: tuple[tuple[int, int], ...]) -> None:
        for frequency, duration_ms in pattern:
            self._winsound.Beep(frequency, duration_ms)

    def speak(self, text: str) -> None:
        if not text.strip():
            return
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            [
                self.powershell_executable,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                self._SPEAK_SCRIPT,
                text,
            ],
            check=False,
            timeout=20,
            creationflags=creation_flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


class WindowsAudioFeedbackSink:
    """Render semantic feedback off the coordinator thread.

    Ordering remains owned by the coordinator: in particular this sink can
    only see SPREAD_SENT after a valid V4 receipt and DATAPACK_SAVED after
    READY.  Rendering failures never roll domain state back.
    """

    def __init__(
        self,
        config: LaptopAudioConfig,
        *,
        backend: AudioFeedbackBackend | None = None,
        trace: JsonLineFeedbackSink | None = None,
    ) -> None:
        self.config = config
        self.backend = backend or WindowsAudioBackend(config.powershell_executable)
        self.trace = trace if trace is not None else (JsonLineFeedbackSink() if config.jsonl_trace else None)
        self._queue: queue.Queue[FeedbackEvent | None] = queue.Queue(config.queue_capacity)
        self._closed = False
        self._thread = threading.Thread(target=self._render_loop, name="asl-laptop-feedback", daemon=True)
        self._thread.start()

    def emit(self, event: FeedbackEvent) -> None:
        if self.trace is not None:
            self.trace.emit(event)
        if self._closed:
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(None)
        self._thread.join(timeout=25)

    def _render_loop(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                return
            try:
                pattern, phrase = _feedback_rendering(event, self.config.speak_catalog_titles)
                if pattern:
                    self.backend.beep(pattern)
                if phrase:
                    self.backend.speak(phrase)
            except Exception:
                continue


def _feedback_rendering(
    event: FeedbackEvent,
    speak_catalog_titles: bool,
) -> tuple[tuple[tuple[int, int], ...], str | None]:
    details = dict(event.details)
    patterns = {
        FeedbackCode.CONFIRM_SELECTION: ((880, 80),),
        FeedbackCode.SCAN_STARTED: ((660, 80), (880, 100)),
        FeedbackCode.SPREAD_SENT: ((1040, 100),),
        FeedbackCode.SCAN_STOPPING: ((520, 100),),
        FeedbackCode.FINALIZING: ((620, 80), (620, 80)),
        FeedbackCode.DATAPACK_SAVED: ((660, 80), (880, 80), (1100, 140)),
        FeedbackCode.SERVER_CONNECTION_LOST: ((440, 180), (330, 240)),
        FeedbackCode.SERVER_RECOVERED: ((660, 80), (880, 100)),
        FeedbackCode.PARSER_REJECTED: ((330, 220), (330, 220)),
        FeedbackCode.OPERATING_MODE_CHANGED: ((740, 80),),
    }
    phrases = {
        FeedbackCode.SPREAD_SENT: "페이지 전송이 완료되었습니다. 다음 페이지로 넘겨 주세요.",
        FeedbackCode.SCANNER_GUIDANCE: "책의 위치를 조정해 주세요.",
        FeedbackCode.SCAN_STOPPING: "촬영을 마치고 전송을 확인합니다.",
        FeedbackCode.FINALIZING: "데이터팩을 생성하고 있습니다.",
        FeedbackCode.DATAPACK_SAVED: "데이터팩 저장이 완료되었습니다.",
        FeedbackCode.SERVER_CONNECTION_LOST: "서버 연결이 끊어졌습니다.",
        FeedbackCode.SERVER_RECOVERED: "서버 연결이 복구되었습니다.",
        FeedbackCode.SERVER_AUTH_FAILED: "서버 인증에 실패했습니다.",
        FeedbackCode.PARSER_REJECTED: "페이지 처리가 거부되었습니다.",
        FeedbackCode.NO_READABLE_DATAPACK: "읽을 수 있는 데이터팩이 없습니다.",
        FeedbackCode.FATAL_ERROR: "장치 실행 중 오류가 발생하여 종료합니다.",
    }
    if event.code is FeedbackCode.SCANNER_GUIDANCE:
        phrases[event.code] = {
            "page_not_found": "펼친 책의 양쪽 페이지 전체가 보이도록 맞춰 주세요.",
            "out_of_frame": "책 가장자리가 화면 안에 들어오도록 맞춰 주세요.",
            "content_occluded": "페이지를 가리는 손이나 물체를 치워 주세요.",
            "hand_or_page_turn": "페이지에서 손을 떼고 잠시 기다려 주세요.",
            "page_moving": "책과 카메라를 움직이지 말고 잠시 기다려 주세요.",
            "move_left": "책을 왼쪽으로 옮겨 주세요.",
            "move_right": "책을 오른쪽으로 옮겨 주세요.",
            "move_up": "책을 위쪽으로 옮겨 주세요.",
            "move_down": "책을 아래쪽으로 옮겨 주세요.",
            "rotate_cw": "책을 시계 방향으로 조금 돌려 주세요.",
            "rotate_ccw": "책을 반시계 방향으로 조금 돌려 주세요.",
            "underexposed": "페이지가 어둡습니다. 조명을 밝게 해 주세요.",
            "overexposed": "페이지가 너무 밝습니다. 강한 조명을 줄여 주세요.",
            "glare": "페이지의 빛 반사를 줄여 주세요.",
            "shadow_uneven": "페이지에 진 그림자가 생기지 않도록 조명을 맞춰 주세요.",
            "blur": "초점이 맞도록 카메라와 책을 고정해 주세요.",
            "insufficient_resolution": "카메라 해상도가 부족합니다. 카메라 설정을 확인해 주세요.",
        }.get(str(details.get("guidance_code")), phrases[event.code])
    if event.code is FeedbackCode.SCREEN_CHANGED:
        screen = details.get("screen")
        mode = details.get("mode")
        if screen == "datapack_selection":
            phrases[event.code] = (
                "캡처 모드 데이터팩 선택 화면입니다."
                if mode == "capture"
                else "리딩 모드 데이터팩 선택 화면입니다."
            )
        elif screen == "capture":
            phrases[event.code] = "페이지 캡처 화면입니다."
        elif screen == "reading":
            phrases[event.code] = "리딩 화면입니다."
    phrase = phrases.get(event.code)
    if event.code is FeedbackCode.SPEAK_CATALOG_TITLE and speak_catalog_titles:
        title = details.get("title")
        phrase = title if isinstance(title, str) and title.strip() else None
    return patterns.get(event.code, ()), phrase
