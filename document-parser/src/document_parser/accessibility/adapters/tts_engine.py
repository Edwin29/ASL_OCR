"""TTS engine boundary (plan document §5.1: "재생·취소·완료 이벤트만 책임지고
엔진 내부 구현은 책임지지 않음"). `piper-tts` and `sounddevice` are optional
dependencies (`pip install document-parser[tts]`) and are imported lazily so
the rest of the accessibility package works without them installed.
"""

from __future__ import annotations

import threading
import wave
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class TtsEngineAdapter(Protocol):
    def speak(self, text: str, generation: int) -> None: ...
    def cancel(self) -> None: ...
    def on_complete(self, callback: Callable[[int], None]) -> None: ...


def load_piper_voice(model_path: str | Path, espeak_data_dir: str | Path, use_cuda: bool = False) -> Any:
    """Load a Piper voice, enforcing the ASCII-only `espeak_data_dir`
    requirement below. Shared by `PiperTtsEngineAdapter` (live playback) and
    the datapack ingest job (batch pre-synthesis, see
    `document_parser.datapack.ingest`) so the safety check and the load call
    exist in exactly one place.
    """
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

    return PiperVoice.load(str(model_path), espeak_data_dir=str(espeak_data_dir), use_cuda=use_cuda)


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

    def __init__(
        self,
        model_path: str | Path,
        espeak_data_dir: str | Path,
        use_cuda: bool = False,
        record_dir: str | Path | None = None,
        play_audio: bool = True,
    ) -> None:
        """`record_dir`, if given, makes every `speak()` call also write the
        synthesized audio to a numbered `.wav` file in that directory (in
        addition to live playback) -- for offline debugging/listening back to
        exactly what a given test run produced, since a live speaker isn't
        something a test log can capture. See `recorded_files` for the paths
        written so far this session. `play_audio=False` skips live sounddevice
        playback entirely (still synthesizes and still records if `record_dir`
        is set) -- for unattended/automated runs where triggering real speaker
        output on whatever machine happens to run the test would be an
        unwanted side effect."""
        self._voice = load_piper_voice(model_path, espeak_data_dir, use_cuda=use_cuda)
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._on_complete: Callable[[int], None] | None = None
        self._lock = threading.Lock()
        self._record_dir = Path(record_dir) if record_dir is not None else None
        if self._record_dir is not None:
            self._record_dir.mkdir(parents=True, exist_ok=True)
        self._record_counter = 0
        self.recorded_files: list[Path] = []
        self._play_audio = play_audio

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

    def wait_until_idle(self, timeout: float = 30.0) -> None:
        """Block until the current utterance's background thread (if any)
        finishes on its own -- unlike `cancel()`, does NOT interrupt it.
        Not part of the `TtsEngineAdapter` protocol (no navigation logic
        needs it); for callers that are about to exit the process and need
        an in-flight `record_dir` write to actually land on disk first,
        since the synthesis thread is a daemon thread that would otherwise
        be killed mid-write when the process exits."""
        with self._lock:
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def _run(self, text: str, generation: int, cancel_event: threading.Event) -> None:
        stream = None
        recorded_chunks: list[bytes] = []
        sample_rate: int | None = None
        sample_channels: int | None = None
        completed = False
        try:
            for chunk in self._voice.synthesize(text):
                if cancel_event.is_set():
                    return
                if self._play_audio and stream is None:
                    import sounddevice as sd  # deferred: optional dependency

                    stream = sd.OutputStream(
                        samplerate=chunk.sample_rate,
                        channels=chunk.sample_channels,
                        dtype="int16",
                    )
                    stream.start()
                if self._record_dir is not None:
                    recorded_chunks.append(chunk.audio_int16_bytes)
                    sample_rate, sample_channels = chunk.sample_rate, chunk.sample_channels
                if cancel_event.is_set():
                    return
                if stream is not None:
                    audio = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                    if chunk.sample_channels > 1:
                        audio = audio.reshape(-1, chunk.sample_channels)
                    stream.write(audio)
            completed = not cancel_event.is_set()
        finally:
            if stream is not None:
                stream.stop()
                stream.close()
            # Write the file (and only then fire on_complete) before the
            # caller can possibly be told "done" -- otherwise a caller that
            # reacts to on_complete by immediately inspecting/cleaning up
            # recorded_files can race the file still being written.
            if self._record_dir is not None and recorded_chunks:
                self._write_wav(text, generation, recorded_chunks, sample_rate, sample_channels)
            if completed and self._on_complete is not None:
                self._on_complete(generation)

    def _write_wav(
        self, text: str, generation: int, chunks: list[bytes], sample_rate: int | None, sample_channels: int | None,
    ) -> Path:
        """Write one synthesized utterance to a numbered `.wav` file (not
        overwritten between calls) plus a sibling `.txt` with the source
        text, so a debugging session ends up with a listenable, labeled
        record of every utterance a test run actually produced."""
        self._record_counter += 1
        assert self._record_dir is not None
        wav_path = self._record_dir / f"tts_{self._record_counter:04d}_gen{generation}.wav"
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(sample_channels or 1)
            wav_file.setsampwidth(2)  # int16
            wav_file.setframerate(sample_rate or 22050)
            wav_file.writeframes(b"".join(chunks))
        wav_path.with_suffix(".txt").write_text(text, encoding="utf-8")
        self.recorded_files.append(wav_path)
        return wav_path


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
