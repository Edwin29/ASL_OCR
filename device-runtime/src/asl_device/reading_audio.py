"""Bounded, latest-generation reading audio orchestration."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from .events import FeedbackCode, FeedbackEvent
from .protocols import AudioPlaybackPort, AudioResourcePort, FeedbackSink
from .types import AudioResource, ReadingSessionId, ReadingSnapshot


class AudioOperationCancelled(RuntimeError):
    """The requested fetch or playback was superseded by a newer generation."""


class AudioResourceError(RuntimeError):
    """An audio resource could not be fetched or validated."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class AudioResourceCache:
    """In-memory LRU cache bounded by both byte count and entry count."""

    def __init__(self, *, max_bytes: int, max_entries: int) -> None:
        if max_bytes <= 0 or max_entries <= 0:
            raise ValueError("audio cache bounds must be positive")
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._items: OrderedDict[tuple[str, str, str], AudioResource] = OrderedDict()
        self._total_bytes = 0
        self._lock = threading.Lock()

    def get(self, reading_session_id: ReadingSessionId, audio_ref: str) -> AudioResource | None:
        with self._lock:
            for key in reversed(self._items):
                if key[:2] == (reading_session_id.value, audio_ref):
                    resource = self._items[key]
                    self._items.move_to_end(key)
                    return resource
            return None

    def put(self, reading_session_id: ReadingSessionId, audio_ref: str, resource: AudioResource) -> bool:
        if resource.content_length > self.max_bytes:
            return False
        key = (reading_session_id.value, audio_ref, resource.sha256)
        with self._lock:
            for existing_key in tuple(self._items):
                if existing_key[:2] == key[:2] and existing_key != key:
                    self._total_bytes -= self._items.pop(existing_key).content_length
            previous = self._items.pop(key, None)
            if previous is not None:
                self._total_bytes -= previous.content_length
            self._items[key] = resource
            self._total_bytes += resource.content_length
            while len(self._items) > self.max_entries or self._total_bytes > self.max_bytes:
                _, evicted = self._items.popitem(last=False)
                self._total_bytes -= evicted.content_length
        return True

    def clear_session(self, reading_session_id: ReadingSessionId) -> None:
        prefix = reading_session_id.value
        with self._lock:
            for key in tuple(self._items):
                if key[0] == prefix:
                    self._total_bytes -= self._items.pop(key).content_length

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._total_bytes = 0

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes


@dataclass(frozen=True, slots=True)
class _AudioJob:
    epoch: int
    snapshot: ReadingSnapshot


class ReadingAudioController:
    """Fetch and play only the newest presented reading generation."""

    def __init__(
        self,
        resource_port: AudioResourcePort,
        playback_port: AudioPlaybackPort,
        cache: AudioResourceCache,
        *,
        feedback: FeedbackSink | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.resource_port = resource_port
        self.playback_port = playback_port
        self.cache = cache
        self.feedback = feedback
        self.monotonic = monotonic
        self._condition = threading.Condition()
        self._epoch = 0
        self._pending: _AudioJob | None = None
        self._active = False
        self._closed = False
        self._last_key: tuple[str, int, str] | None = None
        self._session_id: ReadingSessionId | None = None
        self._worker = threading.Thread(
            target=self._run, name="reading-audio", daemon=True
        )
        self._worker.start()

    def present(self, snapshot: ReadingSnapshot | None) -> None:
        if snapshot is None:
            with self._condition:
                previous_session = self._session_id
                has_context = previous_session is not None
                self._session_id = None
            if has_context:
                self.interrupt()
                assert previous_session is not None
                self.cache.clear_session(previous_session)
            return
        if snapshot.audio_ref is None:
            self.interrupt()
            return
        key = (snapshot.reading_session_id.value, snapshot.generation, snapshot.audio_ref)
        with self._condition:
            if self._closed or key == self._last_key:
                return
            previous_session = self._session_id
            self._session_id = snapshot.reading_session_id
            self._last_key = key
            self._epoch += 1
            job = _AudioJob(self._epoch, snapshot)
            self._pending = job
            self._condition.notify_all()
        self.playback_port.stop()
        if previous_session is not None and previous_session != snapshot.reading_session_id:
            self.cache.clear_session(previous_session)

    def interrupt(self) -> None:
        with self._condition:
            if self._closed:
                return
            had_work = self._active or self._pending is not None
            interrupted_key = self._last_key
            self._epoch += 1
            self._pending = None
            self._last_key = None
            self._condition.notify_all()
        self.playback_port.stop()
        if had_work:
            details = {}
            if interrupted_key is not None:
                details = {
                    "generation": interrupted_key[1],
                    "audio_ref_digest": _ref_digest(interrupted_key[2]),
                }
            self._emit(FeedbackCode.READING_AUDIO_INTERRUPTED, **details)

    def wait_idle(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while self._active or self._pending is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def close(self) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._epoch += 1
            self._pending = None
            self._condition.notify_all()
        self.playback_port.stop()
        self._worker.join(timeout=30.5)
        self.playback_port.close()
        self.cache.clear()

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                job = self._pending
                self._pending = None
                self._active = True
            assert job is not None
            try:
                self._execute(job)
            except AudioOperationCancelled:
                pass
            except Exception as exc:
                if self._is_current(job.epoch):
                    self._emit(
                        FeedbackCode.READING_AUDIO_FAILED,
                        generation=job.snapshot.generation,
                        audio_ref_digest=_ref_digest(job.snapshot.audio_ref or ""),
                        error_class=type(exc).__name__,
                        retryable=bool(getattr(exc, "retryable", False)),
                    )
            finally:
                with self._condition:
                    self._active = False
                    self._condition.notify_all()

    def _execute(self, job: _AudioJob) -> None:
        snapshot = job.snapshot
        assert snapshot.audio_ref is not None
        cancelled = lambda: not self._is_current(job.epoch)
        resource = self.cache.get(snapshot.reading_session_id, snapshot.audio_ref)
        if resource is None:
            self._emit_for(job, FeedbackCode.READING_AUDIO_FETCH_STARTED)
            resource = self.resource_port.fetch(
                snapshot.reading_session_id, snapshot.audio_ref, cancelled
            )
            if cancelled():
                raise AudioOperationCancelled()
            self.cache.put(snapshot.reading_session_id, snapshot.audio_ref, resource)
        else:
            self._emit_for(job, FeedbackCode.READING_AUDIO_CACHE_HIT)
        if cancelled():
            raise AudioOperationCancelled()
        self._emit_for(
            job,
            FeedbackCode.READING_AUDIO_PLAYBACK_STARTED,
            content_length=resource.content_length,
            duration_ms=resource.duration_ms,
        )
        self.playback_port.play(resource, cancelled)
        if cancelled():
            raise AudioOperationCancelled()
        self._emit_for(job, FeedbackCode.READING_AUDIO_PLAYBACK_COMPLETED)

    def _is_current(self, epoch: int) -> bool:
        with self._condition:
            return not self._closed and self._epoch == epoch

    def _emit_for(self, job: _AudioJob, code: FeedbackCode, **details: object) -> None:
        if not self._is_current(job.epoch):
            return
        snapshot = job.snapshot
        self._emit(
            code,
            generation=snapshot.generation,
            audio_ref_digest=_ref_digest(snapshot.audio_ref or ""),
            **details,
        )

    def _emit(self, code: FeedbackCode, **details: object) -> None:
        if self.feedback is None:
            return
        self.feedback.emit(
            FeedbackEvent(code, self.monotonic(), tuple(details.items()))
        )


def _ref_digest(audio_ref: str) -> str:
    return hashlib.sha256(audio_ref.encode("utf-8")).hexdigest()[:12]
