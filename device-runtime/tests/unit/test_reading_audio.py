from __future__ import annotations

import hashlib
import threading
import time

from asl_device.events import FeedbackCode, FeedbackEvent
from asl_device.reading_audio import AudioOperationCancelled, AudioResourceCache, ReadingAudioController
from asl_device.types import (
    AudioResource,
    DatapackId,
    DeviceId,
    ReadingSessionId,
    ReadingSnapshot,
)


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


class SystemResourcePort(ResourcePort):
    pass


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


def _feedback(code: FeedbackCode, **details: object) -> FeedbackEvent:
    return FeedbackEvent(code, 1.0, tuple(details.items()))


def test_system_screen_then_catalog_title_share_one_serial_player() -> None:
    reading = ResourcePort()
    system = SystemResourcePort()
    player = Player()
    controller = ReadingAudioController(
        reading,
        player,
        AudioResourceCache(max_bytes=1000, max_entries=8),
        device_id=DeviceId("device-1"),
        system_resource_port=system,
    )
    title_ref = "s0-system-audio:" + "d" * 32
    try:
        controller.emit(
            _feedback(
                FeedbackCode.SCREEN_CHANGED,
                screen="datapack_selection",
                mode="capture",
            )
        )
        controller.emit(
            _feedback(
                FeedbackCode.SPEAK_CATALOG_TITLE,
                kind="existing",
                title_audio_ref=title_ref,
            )
        )
        assert controller.wait_idle(1)
    finally:
        controller.close()

    assert [ref for _scope, ref in system.calls] == [
        "s0-system-cue:screen.capture_catalog",
        title_ref,
    ]
    assert player.played == [
        b"s0-system-cue:screen.capture_catalog",
        title_ref.encode(),
    ]


def test_rapid_catalog_movement_drops_stale_title() -> None:
    entered = threading.Event()

    class BlockingSystem(SystemResourcePort):
        def fetch(self, scope, ref, cancelled):
            self.calls.append((scope, ref))
            if ref.endswith("1" * 32):
                entered.set()
                while not cancelled():
                    time.sleep(0.005)
                raise AudioOperationCancelled()
            return _resource(ref.encode())

    system = BlockingSystem()
    player = Player()
    controller = ReadingAudioController(
        ResourcePort(),
        player,
        AudioResourceCache(max_bytes=1000, max_entries=8),
        device_id=DeviceId("device-1"),
        system_resource_port=system,
    )
    try:
        for token in ("1", "2", "3"):
            controller.emit(
                _feedback(
                    FeedbackCode.SPEAK_CATALOG_TITLE,
                    kind="existing",
                    title_audio_ref="s0-system-audio:" + token * 32,
                )
            )
            if token == "1":
                assert entered.wait(1)
        assert controller.wait_idle(2)
    finally:
        controller.close()

    assert player.played == [("s0-system-audio:" + "3" * 32).encode()]


def test_reading_generation_interrupts_active_system_prompt() -> None:
    entered = threading.Event()
    cancelled = threading.Event()

    class BlockingPlayer(Player):
        def play(self, resource, is_cancelled):
            if resource.wav_bytes.startswith(b"s0-system"):
                entered.set()
                while not is_cancelled():
                    time.sleep(0.005)
                cancelled.set()
                raise AudioOperationCancelled()
            super().play(resource, is_cancelled)

    player = BlockingPlayer()
    controller = ReadingAudioController(
        ResourcePort(),
        player,
        AudioResourceCache(max_bytes=1000, max_entries=8),
        device_id=DeviceId("device-1"),
        system_resource_port=SystemResourcePort(),
    )
    try:
        controller.emit(_feedback(FeedbackCode.SPREAD_SENT))
        assert entered.wait(1)
        controller.present(_snapshot(7, "s0-audio:" + "7" * 32))
        assert controller.wait_idle(2)
    finally:
        controller.close()

    assert cancelled.is_set()
    assert player.played == [("s0-audio:" + "7" * 32).encode()]
