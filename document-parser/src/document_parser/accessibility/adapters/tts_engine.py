"""TTS engine boundary (plan document §5.1: "재생·취소·완료 이벤트만 책임지고
엔진 내부 구현은 책임지지 않음"). `piper-tts` and `sounddevice` are optional
dependencies (`pip install document-parser[tts]`) and are imported lazily so
the rest of the accessibility package works without them installed.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class TtsEngineAdapter(Protocol):
    def speak(self, text: str, generation: int) -> None: ...
    def cancel(self) -> None: ...
    def on_complete(self, callback: Callable[[int], None]) -> None: ...


class PiperTtsEngineAdapter:
    """Piper-backed engine. Plays synthesized audio chunk by chunk in a
    background thread so `cancel()` can stop within roughly one chunk's
    duration instead of waiting for the full utterance to finish.

    `espeak_data_dir` must be an ASCII-only path. The bundled espeak-ng
    native library in the Windows `piper-tts` wheel crashes the whole
    process -- not a catchable Python exception -- when given a data
    directory path containing non-ASCII bytes (verified: a Windows username
    with Korean characters is enough to trigger it, for any voice/language,
    not just Korean text). Rejecting a non-ASCII path here, before that
    native call happens, turns an unrecoverable crash into an ordinary
    Python exception the caller can act on.
    """

    def __init__(self, model_path: str | Path, espeak_data_dir: str | Path, use_cuda: bool = False) -> None:
        espeak_data_dir = Path(espeak_data_dir)
        try:
            str(espeak_data_dir).encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError(
                f"espeak_data_dir must be an ASCII-only path, got {espeak_data_dir!r}. "
                "Copy the espeak-ng-data directory to an ASCII-only path first -- a "
                "non-ASCII path crashes the underlying native library instead of "
                "raising a catchable error."
            ) from exc

        from piper.voice import PiperVoice  # deferred: optional dependency

        self._voice = PiperVoice.load(str(model_path), espeak_data_dir=str(espeak_data_dir), use_cuda=use_cuda)
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._on_complete: Callable[[int], None] | None = None
        self._lock = threading.Lock()

    def on_complete(self, callback: Callable[[int], None]) -> None:
        self._on_complete = callback

    def speak(self, text: str, generation: int) -> None:
        self.cancel()  # stop whatever was previously playing first
        cancel_event = threading.Event()
        self._cancel_event = cancel_event
        thread = threading.Thread(target=self._run, args=(text, generation, cancel_event), daemon=True)
        with self._lock:
            self._thread = thread
        thread.start()

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _run(self, text: str, generation: int, cancel_event: threading.Event) -> None:
        import sounddevice as sd  # deferred: optional dependency

        stream: "sd.OutputStream | None" = None
        try:
            for chunk in self._voice.synthesize(text):
                if cancel_event.is_set():
                    return
                if stream is None:
                    stream = sd.OutputStream(
                        samplerate=chunk.sample_rate,
                        channels=chunk.sample_channels,
                        dtype="int16",
                    )
                    stream.start()
                audio = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                if chunk.sample_channels > 1:
                    audio = audio.reshape(-1, chunk.sample_channels)
                if cancel_event.is_set():
                    return
                stream.write(audio)
            if not cancel_event.is_set() and self._on_complete is not None:
                self._on_complete(generation)
        finally:
            if stream is not None:
                stream.stop()
                stream.close()


class FakeTtsEngineAdapter:
    """Test double: no real audio. Records every `speak`/`cancel` call so
    tests can assert on ordering, and exposes `complete(generation)` for
    tests to simulate the engine finishing an utterance."""

    def __init__(self) -> None:
        self.spoken: list[tuple[str, int]] = []
        self.cancel_count = 0
        self._on_complete: Callable[[int], None] | None = None

    def on_complete(self, callback: Callable[[int], None]) -> None:
        self._on_complete = callback

    def speak(self, text: str, generation: int) -> None:
        self.spoken.append((text, generation))

    def cancel(self) -> None:
        self.cancel_count += 1

    def complete(self, generation: int) -> None:
        if self._on_complete is not None:
            self._on_complete(generation)
