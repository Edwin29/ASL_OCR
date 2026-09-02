"""Bounded, latest-generation reading audio orchestration."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Callable

from .events import FeedbackCode, FeedbackEvent
from .protocols import (
    AudioPlaybackPort,
    AudioResourcePort,
    FeedbackSink,
    SystemAudioResourcePort,
)
from .types import AudioResource, DeviceId, ReadingSessionId, ReadingSnapshot


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

    def get(self, scope_id: ReadingSessionId | DeviceId, audio_ref: str) -> AudioResource | None:
        with self._lock:
            for key in reversed(self._items):
                if key[:2] == (scope_id.value, audio_ref):
                    resource = self._items[key]
                    self._items.move_to_end(key)
                    return resource
            return None

    def put(
        self,
        scope_id: ReadingSessionId | DeviceId,
        audio_ref: str,
        resource: AudioResource,
    ) -> bool:
        if resource.content_length > self.max_bytes:
            return False
        key = (scope_id.value, audio_ref, resource.sha256)
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
    kind: str
    scope_id: ReadingSessionId | DeviceId
    audio_ref: str
    priority: int
    group: str
    generation: int | None = None

    @property
    def dedupe_key(self) -> tuple[str, str, int | None, str]:
        return (self.kind, self.scope_id.value, self.generation, self.audio_ref)


class ReadingAudioController:
    """Single playback arbiter for reading generations and Piper UI prompts."""

    def __init__(
        self,
        resource_port: AudioResourcePort,
        playback_port: AudioPlaybackPort,
        cache: AudioResourceCache,
        *,
        device_id: DeviceId | None = None,
        system_resource_port: SystemAudioResourcePort | None = None,
        feedback: FeedbackSink | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.resource_port = resource_port
        self.playback_port = playback_port
        self.cache = cache
        self.device_id = device_id
        self.system_resource_port = system_resource_port
        self.feedback = feedback
        self.monotonic = monotonic
        self._condition = threading.Condition()
        self._epoch = 0
        self._pending: list[_AudioJob] = []
        self._active_job: _AudioJob | None = None
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
                self._session_id = None
                self._last_key = None
            if previous_session is not None:
                assert previous_session is not None
                self.cache.clear_session(previous_session)
            return
        if snapshot.audio_ref is None:
            return
        key = (snapshot.reading_session_id.value, snapshot.generation, snapshot.audio_ref)
        with self._condition:
            if self._closed or key == self._last_key:
                return
            previous_session = self._session_id
            self._session_id = snapshot.reading_session_id
            self._last_key = key
        self._submit(
            _AudioJob(
                0,
                "reading",
                snapshot.reading_session_id,
                snapshot.audio_ref,
                90,
                "reading",
                snapshot.generation,
            ),
            interrupt=True,
        )
        if previous_session is not None and previous_session != snapshot.reading_session_id:
            self.cache.clear_session(previous_session)

    def emit(self, event: FeedbackEvent) -> None:
        """FeedbackSink entry point for server-synthesized system prompts."""

        if self.device_id is None or self.system_resource_port is None:
            return
        request = _system_audio_request(event)
        if request is None:
            return
        audio_ref, priority, group, interrupt_lower = request
        self._submit(
            _AudioJob(0, "system", self.device_id, audio_ref, priority, group),
            replace_group=group in {"catalog", "screen", "guidance", "process"},
            interrupt_lower=interrupt_lower,
        )

    def interrupt(self) -> None:
        with self._condition:
            if self._closed:
                return
            had_work = self._active_job is not None or bool(self._pending)
            interrupted_key = self._last_key
            self._epoch += 1
            self._pending.clear()
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
            while self._active_job is not None or self._pending:
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
            self._pending.clear()
            self._condition.notify_all()
        self.playback_port.stop()
        self._worker.join(timeout=30.5)
        self.playback_port.close()
        self.cache.clear()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                index = max(
                    range(len(self._pending)),
                    key=lambda item: self._pending[item].priority,
                )
                job = self._pending.pop(index)
                self._active_job = job
            try:
                self._execute(job)
            except AudioOperationCancelled:
                pass
            except Exception as exc:
                if self._is_current(job):
                    self._emit(
                        FeedbackCode.READING_AUDIO_FAILED,
                        **self._job_details(job),
                        error_class=type(exc).__name__,
                        retryable=bool(getattr(exc, "retryable", False)),
                    )
            finally:
                with self._condition:
                    if self._active_job is job:
                        self._active_job = None
                    self._condition.notify_all()

    def _execute(self, job: _AudioJob) -> None:
        cancelled = lambda: not self._is_current(job)
        resource = self.cache.get(job.scope_id, job.audio_ref)
        if resource is None:
            self._emit_for(job, FeedbackCode.READING_AUDIO_FETCH_STARTED)
            if job.kind == "reading":
                assert isinstance(job.scope_id, ReadingSessionId)
                resource = self.resource_port.fetch(job.scope_id, job.audio_ref, cancelled)
            else:
                assert isinstance(job.scope_id, DeviceId)
                assert self.system_resource_port is not None
                resource = self.system_resource_port.fetch(
                    job.scope_id, job.audio_ref, cancelled
                )
            if cancelled():
                raise AudioOperationCancelled()
            self.cache.put(job.scope_id, job.audio_ref, resource)
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

    def _is_current(self, job: _AudioJob) -> bool:
        with self._condition:
            return (
                not self._closed
                and self._epoch == job.epoch
                and self._active_job is job
            )

    def _emit_for(self, job: _AudioJob, code: FeedbackCode, **details: object) -> None:
        if not self._is_current(job):
            return
        self._emit(code, **self._job_details(job), **details)

    def _job_details(self, job: _AudioJob) -> dict[str, object]:
        details: dict[str, object] = {
            "audio_kind": job.kind,
            "audio_ref_digest": _ref_digest(job.audio_ref),
        }
        if job.generation is not None:
            details["generation"] = job.generation
        return details

    def _submit(
        self,
        job: _AudioJob,
        *,
        interrupt: bool = False,
        replace_group: bool = False,
        interrupt_lower: bool = False,
    ) -> None:
        stop = False
        with self._condition:
            if self._closed:
                return
            if (
                self._active_job is not None
                and self._active_job.dedupe_key == job.dedupe_key
            ) or any(item.dedupe_key == job.dedupe_key for item in self._pending):
                return
            active = self._active_job
            should_interrupt = interrupt or (
                (
                    active is not None
                    and (
                        (replace_group and active.group == job.group)
                        or (interrupt_lower and job.priority > active.priority)
                    )
                )
                or (
                    interrupt_lower
                    and any(item.priority < job.priority for item in self._pending)
                )
            )
            if should_interrupt:
                self._epoch += 1
                self._pending.clear()
                stop = active is not None
            elif replace_group:
                self._pending = [
                    item for item in self._pending if item.group != job.group
                ]
            job = replace(job, epoch=self._epoch)
            self._pending.append(job)
            self._condition.notify_all()
        if stop or interrupt:
            self.playback_port.stop()

    def _emit(self, code: FeedbackCode, **details: object) -> None:
        if self.feedback is None:
            return
        self.feedback.emit(
            FeedbackEvent(code, self.monotonic(), tuple(details.items()))
        )


def _ref_digest(audio_ref: str) -> str:
    return hashlib.sha256(audio_ref.encode("utf-8")).hexdigest()[:12]


def _system_audio_request(
    event: FeedbackEvent,
) -> tuple[str, int, str, bool] | None:
    details = dict(event.details)
    if event.code is FeedbackCode.SCREEN_CHANGED:
        screen = details.get("screen")
        mode = details.get("mode")
        if screen == "datapack_selection":
            cue = (
                "screen.capture_catalog"
                if mode == "capture"
                else "screen.reading_catalog"
            )
        elif screen == "capture":
            cue = "screen.capture"
        elif screen == "reading":
            cue = "screen.reading"
        else:
            return None
        return (f"s0-system-cue:{cue}", 50, "screen", False)
    if event.code is FeedbackCode.SPEAK_CATALOG_TITLE:
        title_ref = details.get("title_audio_ref")
        if isinstance(title_ref, str) and title_ref.startswith("s0-system-audio:"):
            return (title_ref, 40, "catalog", False)
        if details.get("kind") == "new_datapack":
            return ("s0-system-cue:catalog.new_datapack", 40, "catalog", False)
        return None
    fixed = {
        FeedbackCode.SCAN_STARTED: ("scan.started", 60, "process", False),
        FeedbackCode.SCANNER_GUIDANCE: ("scan.guidance", 30, "guidance", False),
        FeedbackCode.SPREAD_SENT: ("scan.spread_sent", 80, "handoff", True),
        FeedbackCode.SCAN_STOPPING: ("scan.stopping", 60, "process", True),
        FeedbackCode.FINALIZING: ("scan.finalizing", 60, "process", False),
        FeedbackCode.DATAPACK_SAVED: ("scan.saved", 80, "completion", True),
        FeedbackCode.SERVER_CONNECTION_LOST: (
            "server.connection_lost",
            100,
            "error",
            True,
        ),
        FeedbackCode.SERVER_RECOVERED: ("server.recovered", 90, "recovery", True),
        FeedbackCode.SERVER_AUTH_FAILED: ("server.auth_failed", 100, "error", True),
        FeedbackCode.PARSER_REJECTED: ("parser.rejected", 100, "error", True),
        FeedbackCode.NO_READABLE_DATAPACK: ("catalog.empty", 80, "catalog", True),
    }.get(event.code)
    if fixed is None:
        return None
    cue, priority, group, interrupt_lower = fixed
    return (f"s0-system-cue:{cue}", priority, group, interrupt_lower)
