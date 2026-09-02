from __future__ import annotations

import hashlib
import io
import wave

import pytest

from asl_device.adapters.reading_audio import S0AudioResourceHttpAdapter, SoundDeviceWavPlayer
from asl_device.reading_audio import AudioOperationCancelled, AudioResourceError
from asl_device.types import ReadingSessionId


def _wav(frames: int = 160) -> bytes:
    target = io.BytesIO()
    with wave.open(target, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00\x00" * frames)
    return target.getvalue()


class Response:
    status = 200

    def __init__(self, body: bytes, *, content_type: str = "audio/wav", etag: str | None = None):
        self.body = io.BytesIO(body)
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "ETag": f'"{etag or hashlib.sha256(body).hexdigest()}"',
        }

    def read(self, size=-1):
        return self.body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_audio_http_adapter_uses_session_scoped_authenticated_route() -> None:
    body = _wav()
    calls = []

    def opener(request, timeout):
        calls.append((request, timeout))
        return Response(body)

    adapter = S0AudioResourceHttpAdapter(
        "http://server", "secret", chunk_bytes=31, opener=opener
    )
    resource = adapter.fetch(
        ReadingSessionId("reading-1"), "s0-audio:" + "a" * 32, lambda: False
    )

    request, timeout = calls[0]
    assert request.full_url.endswith("/api/v1/reading-sessions/reading-1/audio/" + "a" * 32)
    assert request.headers["X-api-key"] == "secret"
    assert timeout == 10.0
    assert resource.wav_bytes == body
    assert resource.sample_rate == 16000


@pytest.mark.parametrize(
    "ref", ["relative.wav", "s0-audio:abc", "s0-audio:" + "A" * 32]
)
def test_audio_http_adapter_rejects_malformed_reference(ref: str) -> None:
    adapter = S0AudioResourceHttpAdapter("http://server", "secret", opener=lambda *_a, **_k: None)

    with pytest.raises(AudioResourceError, match="reference"):
        adapter.fetch(ReadingSessionId("reading-1"), ref, lambda: False)


def test_audio_http_adapter_rejects_digest_mismatch_and_oversize() -> None:
    body = _wav()
    mismatch = S0AudioResourceHttpAdapter(
        "http://server", "secret", opener=lambda *_a, **_k: Response(body, etag="0" * 64)
    )
    with pytest.raises(AudioResourceError, match="digest"):
        mismatch.fetch(ReadingSessionId("reading-1"), "s0-audio:" + "b" * 32, lambda: False)

    oversized = S0AudioResourceHttpAdapter(
        "http://server", "secret", max_resource_bytes=10, opener=lambda *_a, **_k: Response(body)
    )
    with pytest.raises(AudioResourceError, match="limit"):
        oversized.fetch(ReadingSessionId("reading-1"), "s0-audio:" + "b" * 32, lambda: False)


def test_audio_http_adapter_rejects_non_wav_and_empty_pcm() -> None:
    wrong_type = S0AudioResourceHttpAdapter(
        "http://server", "secret", opener=lambda *_a, **_k: Response(b"plain", content_type="text/plain")
    )
    with pytest.raises(AudioResourceError, match="content type"):
        wrong_type.fetch(ReadingSessionId("reading-1"), "s0-audio:" + "b" * 32, lambda: False)

    empty = _wav(frames=0)
    empty_pcm = S0AudioResourceHttpAdapter(
        "http://server", "secret", opener=lambda *_a, **_k: Response(empty)
    )
    with pytest.raises(AudioResourceError, match="no frames"):
        empty_pcm.fetch(ReadingSessionId("reading-1"), "s0-audio:" + "b" * 32, lambda: False)


def test_audio_http_adapter_honors_preflight_cancellation() -> None:
    adapter = S0AudioResourceHttpAdapter("http://server", "secret", opener=lambda *_a, **_k: None)

    with pytest.raises(AudioOperationCancelled):
        adapter.fetch(ReadingSessionId("reading-1"), "s0-audio:" + "c" * 32, lambda: True)


def test_sounddevice_player_streams_pcm_without_disk_file() -> None:
    raw = _wav()
    resource = S0AudioResourceHttpAdapter(
        "http://server", "secret", opener=lambda *_a, **_k: Response(raw)
    ).fetch(ReadingSessionId("reading-1"), "s0-audio:" + "d" * 32, lambda: False)

    class Stream:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.writes = []
            self.started = False
            self.closed = False

        def start(self):
            self.started = True

        def write(self, payload):
            self.writes.append(payload)

        def stop(self):
            pass

        def abort(self):
            pass

        def close(self):
            self.closed = True

    class SoundDevice:
        def __init__(self):
            self.stream = None

        def RawOutputStream(self, **kwargs):
            self.stream = Stream(**kwargs)
            return self.stream

    module = SoundDevice()
    player = SoundDeviceWavPlayer(sounddevice_module=module, frames_per_chunk=32)
    player.play(resource, lambda: False)

    assert module.stream.started
    assert module.stream.closed
    assert b"".join(module.stream.writes) == b"\x00\x00" * 160
