from __future__ import annotations

import hashlib
import threading
import time

from asl_device.events import FeedbackCode
from asl_device.reading_audio import AudioOperationCancelled, AudioResourceCache, ReadingAudioController
from asl_device.types import AudioResource, DatapackId, ReadingSessionId, ReadingSnapshot


def _resource(payload: bytes = b"wav") -> AudioResource:
    return AudioResource(payload, hashlib.sha256(payload).hexdigest(), len(payload), 16000, 1, 2, 20)


def _snapshot(generation: int, ref: str, session: str = "reading-1") -> ReadingSnapshot:
    return ReadingSnapshot(
        ReadingSessionId(session),
        DatapackId("datapack-1"),
        (("generation", generation),),
        (),
        ref,
    )


def test_snapshot_audio_requires_valid_generation() -> None:
    for cursor in ((), (("generation", True),), (("generation", -1),)):
        try:
            ReadingSnapshot(
                ReadingSessionId("reading-1"),
                DatapackId("datapack-1"),
                cursor,
                (),
                "s0-audio:" + "a" * 32,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("invalid reading generation was accepted")

    assert _snapshot(0, "s0-audio:" + "a" * 32).generation == 0


class Sink:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


class ResourcePort:
    def __init__(self) -> None:
        self.calls = []

    def fetch(self, session, ref, cancelled):
        self.calls.append((session, ref))
        if cancelled():
            raise AudioOperationCancelled()
        return _resource(ref.encode())


class Player:
    def __init__(self) -> None:
        self.played = []
        self.stops = 0
        self.closed = 0

    def play(self, resource, cancelled):
        if cancelled():
            raise AudioOperationCancelled()
        self.played.append(resource.wav_bytes)

    def stop(self):
        self.stops += 1

    def close(self):
        self.closed += 1


def test_cache_is_bounded_lru_and_session_scoped() -> None:
    cache = AudioResourceCache(max_bytes=7, max_entries=2)
    first = _resource(b"111")
    second = _resource(b"222")
    third = _resource(b"333")
    session = ReadingSessionId("reading-1")

    assert cache.put(session, "a", first)
    assert cache.put(session, "b", second)
    assert cache.get(session, "a") is first
    assert cache.put(session, "c", third)

    assert cache.get(session, "b") is None
    assert cache.entry_count == 2
    assert cache.total_bytes == 6
    cache.clear_session(session)
    assert cache.entry_count == 0


def test_controller_deduplicates_generation_and_reuses_cached_audio() -> None:
    resource = ResourcePort()
    player = Player()
    sink = Sink()
    controller = ReadingAudioController(
        resource, player, AudioResourceCache(max_bytes=100, max_entries=4), feedback=sink
    )
    try:
        controller.present(_snapshot(1, "s0-audio:" + "1" * 32))
        assert controller.wait_idle(1)
        controller.present(_snapshot(1, "s0-audio:" + "1" * 32))
        controller.present(_snapshot(2, "s0-audio:" + "1" * 32))
        assert controller.wait_idle(1)
    finally:
        controller.close()

    assert len(resource.calls) == 1
    assert len(player.played) == 2
    assert FeedbackCode.READING_AUDIO_CACHE_HIT in [event.code for event in sink.events]
    assert player.closed == 1


def test_new_generation_cancels_late_fetch_before_playback() -> None:
    entered = threading.Event()

    class BlockingResource(ResourcePort):
        def fetch(self, session, ref, cancelled):
            self.calls.append((session, ref))
            if ref.endswith("1" * 32):
                entered.set()
                deadline = time.monotonic() + 1
                while not cancelled() and time.monotonic() < deadline:
                    time.sleep(0.005)
                raise AudioOperationCancelled()
            return _resource(b"new")

    resource = BlockingResource()
    player = Player()
    controller = ReadingAudioController(
        resource, player, AudioResourceCache(max_bytes=100, max_entries=4)
    )
    try:
        controller.present(_snapshot(1, "s0-audio:" + "1" * 32))
        assert entered.wait(1)
        controller.present(_snapshot(2, "s0-audio:" + "2" * 32))
        assert controller.wait_idle(2)
    finally:
        controller.close()

    assert player.played == [b"new"]
    assert len(resource.calls) == 2


def test_failure_is_reported_without_exposing_audio_ref() -> None:
    secret_ref = "s0-audio:" + "a" * 32

    class FailingResource(ResourcePort):
        def fetch(self, session, ref, cancelled):
            raise RuntimeError("boom")

    sink = Sink()
    controller = ReadingAudioController(
        FailingResource(), Player(), AudioResourceCache(max_bytes=100, max_entries=4), feedback=sink
    )
    try:
        controller.present(_snapshot(3, secret_ref))
        assert controller.wait_idle(1)
    finally:
        controller.close()

    failed = next(event for event in sink.events if event.code is FeedbackCode.READING_AUDIO_FAILED)
    assert secret_ref not in repr(failed.details)
    assert dict(failed.details)["error_class"] == "RuntimeError"
