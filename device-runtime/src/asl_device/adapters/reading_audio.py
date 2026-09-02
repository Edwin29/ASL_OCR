"""Authenticated S0 WAV download and desktop PCM playback adapters."""

from __future__ import annotations

import hashlib
import io
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import wave
from collections.abc import Callable
from typing import Any

from asl_device.reading_audio import AudioOperationCancelled, AudioResourceError
from asl_device.types import AudioResource, DeviceId, ReadingSessionId


_AUDIO_REF = re.compile(r"s0-audio:([0-9a-f]{32})\Z")
_SYSTEM_AUDIO_REF = re.compile(r"s0-system-audio:([0-9a-f]{32})\Z")
_SYSTEM_CUE_REF = re.compile(r"s0-system-cue:([a-z0-9._-]{1,80})\Z")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class S0AudioResourceHttpAdapter:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 10.0,
        max_resource_bytes: int = 4 * 1024 * 1024,
        chunk_bytes: int = 64 * 1024,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be an HTTP(S) URL")
        if not api_key:
            raise ValueError("api_key must be non-empty")
        if timeout_seconds <= 0 or max_resource_bytes <= 0 or chunk_bytes <= 0:
            raise ValueError("audio HTTP bounds must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_resource_bytes = max_resource_bytes
        self.chunk_bytes = chunk_bytes
        self._opener = opener or urllib.request.build_opener(_NoRedirect()).open

    def fetch(
        self,
        reading_session_id: ReadingSessionId,
        audio_ref: str,
        cancelled: Callable[[], bool],
    ) -> AudioResource:
        match = _AUDIO_REF.fullmatch(audio_ref)
        if match is None:
            raise AudioResourceError("audio reference is malformed", retryable=False)
        audio_id = match.group(1)
        session = urllib.parse.quote(reading_session_id.value, safe="")
        url = f"{self.base_url}/api/v1/reading-sessions/{session}/audio/{audio_id}"
        return self._fetch_url(url, cancelled)

    def _fetch_url(
        self, url: str, cancelled: Callable[[], bool]
    ) -> AudioResource:
        request = urllib.request.Request(
            url,
            headers={
                "X-API-Key": self.api_key,
                "Accept": "audio/wav",
            },
            method="GET",
        )
        if cancelled():
            raise AudioOperationCancelled()
        try:
            response = self._opener(request, timeout=self.timeout_seconds)
            with response:
                status = int(getattr(response, "status", 200))
                if not 200 <= status < 300:
                    raise AudioResourceError(
                        f"audio server returned HTTP {status}", retryable=status >= 500
                    )
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type not in {"audio/wav", "audio/x-wav", "audio/wave"}:
                    raise AudioResourceError("audio response content type is not WAV", retryable=False)
                content_length = _optional_int(response.headers.get("Content-Length"))
                if content_length is not None and content_length > self.max_resource_bytes:
                    raise AudioResourceError("audio resource exceeds configured limit", retryable=False)
                body = bytearray()
                digest = hashlib.sha256()
                while True:
                    if cancelled():
                        raise AudioOperationCancelled()
                    chunk = response.read(self.chunk_bytes)
                    if not chunk:
                        break
                    body.extend(chunk)
                    digest.update(chunk)
                    if len(body) > self.max_resource_bytes:
                        raise AudioResourceError("audio resource exceeds configured limit", retryable=False)
        except AudioOperationCancelled:
            raise
        except urllib.error.HTTPError as exc:
            raise AudioResourceError(
                f"audio server returned HTTP {exc.code}",
                retryable=exc.code >= 500 or exc.code in {408, 429},
            ) from exc
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise AudioResourceError("audio server transport unavailable", retryable=True) from exc
        raw = bytes(body)
        if content_length is not None and len(raw) != content_length:
            raise AudioResourceError("audio Content-Length mismatch", retryable=True)
        sha256 = digest.hexdigest()
        etag = response.headers.get("ETag", "").strip().strip('"').lower()
        if etag and etag != sha256:
            raise AudioResourceError("audio ETag digest mismatch", retryable=False)
        return _validate_wav(raw, sha256)


class S0SystemAudioResourceHttpAdapter(S0AudioResourceHttpAdapter):
    """Fetch fixed system cues or device-scoped opaque title resources."""

    def fetch(
        self,
        device_id: DeviceId,
        audio_ref: str,
        cancelled: Callable[[], bool],
    ) -> AudioResource:
        device = urllib.parse.quote(device_id.value, safe="")
        cue_match = _SYSTEM_CUE_REF.fullmatch(audio_ref)
        opaque_match = _SYSTEM_AUDIO_REF.fullmatch(audio_ref)
        if cue_match is not None:
            cue = urllib.parse.quote(cue_match.group(1), safe="")
            url = f"{self.base_url}/api/v1/devices/{device}/system-audio/cues/{cue}"
        elif opaque_match is not None:
            audio_id = opaque_match.group(1)
            url = f"{self.base_url}/api/v1/devices/{device}/system-audio/{audio_id}"
        else:
            raise AudioResourceError(
                "system audio reference is malformed", retryable=False
            )
        return self._fetch_url(url, cancelled)


class SoundDeviceWavPlayer:
    """Blocking WAV player with thread-safe, immediate stream interruption."""

    def __init__(self, *, sounddevice_module: Any | None = None, frames_per_chunk: int = 2048) -> None:
        if frames_per_chunk <= 0:
            raise ValueError("frames_per_chunk must be positive")
        if sounddevice_module is None:
            try:
                import sounddevice as sounddevice_module  # type: ignore[no-redef]
            except ImportError as exc:
                raise RuntimeError(
                    "reading audio requires the optional 'audio' dependency (sounddevice)"
                ) from exc
        self._sounddevice = sounddevice_module
        self.frames_per_chunk = frames_per_chunk
        self._lock = threading.Lock()
        self._stream: Any | None = None
        self._closed = False

    def play(self, resource: AudioResource, cancelled: Callable[[], bool]) -> None:
        with wave.open(io.BytesIO(resource.wav_bytes), "rb") as reader:
            stream = self._sounddevice.RawOutputStream(
                samplerate=reader.getframerate(),
                channels=reader.getnchannels(),
                dtype="int16",
                blocksize=self.frames_per_chunk,
            )
            with self._lock:
                if self._closed or cancelled():
                    stream.close()
                    raise AudioOperationCancelled()
                self._stream = stream
            try:
                stream.start()
                while not cancelled():
                    frames = reader.readframes(self.frames_per_chunk)
                    if not frames:
                        break
                    stream.write(frames)
                if cancelled():
                    raise AudioOperationCancelled()
            finally:
                with self._lock:
                    if self._stream is stream:
                        self._stream = None
                _stop_and_close(stream)

    def stop(self) -> None:
        with self._lock:
            stream = self._stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.stop()


def _validate_wav(raw: bytes, sha256: str) -> AudioResource:
    try:
        with wave.open(io.BytesIO(raw), "rb") as reader:
            channels = reader.getnchannels()
            sample_width = reader.getsampwidth()
            sample_rate = reader.getframerate()
            frame_count = reader.getnframes()
            compression = reader.getcomptype()
    except (EOFError, wave.Error) as exc:
        raise AudioResourceError("audio response is not a valid WAV", retryable=False) from exc
    if compression != "NONE" or sample_width != 2:
        raise AudioResourceError("audio WAV must be uncompressed 16-bit PCM", retryable=False)
    if frame_count <= 0:
        raise AudioResourceError("audio WAV contains no frames", retryable=False)
    if channels not in {1, 2} or not 8_000 <= sample_rate <= 48_000:
        raise AudioResourceError("audio WAV format is outside playback bounds", retryable=False)
    duration_ms = max(1, round(frame_count * 1000 / sample_rate))
    if duration_ms > 120_000:
        raise AudioResourceError("audio WAV duration exceeds 120 seconds", retryable=False)
    return AudioResource(
        raw,
        sha256,
        len(raw),
        sample_rate,
        channels,
        sample_width,
        duration_ms,
    )


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise AudioResourceError("audio Content-Length is malformed", retryable=False) from exc
    if parsed < 0:
        raise AudioResourceError("audio Content-Length is malformed", retryable=False)
    return parsed


def _stop_and_close(stream: Any) -> None:
    try:
        stream.stop()
    except Exception:
        pass
    try:
        stream.close()
    except Exception:
        pass
