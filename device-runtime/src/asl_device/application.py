"""Single-threaded application shell for the E0-Core Device composition."""

from __future__ import annotations

import queue
import time
import warnings
from collections.abc import Callable, Iterable
from typing import Protocol

from .adapters.local_controls import ControlSource
from .coordinator import DeviceFlowCoordinator
from .events import CoordinatorEvent
from .types import DeviceControl, DeviceFlowState, DeviceInputEvent, InputAction


class ReadingPresenter(Protocol):
    def present(self, snapshot) -> None: ...

    def close(self) -> None: ...


class ReadingAudioPresenter(Protocol):
    def present(self, snapshot) -> None: ...

    def interrupt(self) -> None: ...

    def close(self) -> None: ...


class DeviceApplication:
    def __init__(
        self,
        coordinator: DeviceFlowCoordinator,
        controls: ControlSource,
        *,
        poll_interval_seconds: float,
        presenter: ReadingPresenter | None = None,
        audio_presenter: ReadingAudioPresenter | None = None,
        closeables: Iterable[object] = (),
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self.coordinator = coordinator
        self.controls = controls
        self.poll_interval_seconds = poll_interval_seconds
        self.presenter = presenter
        self.audio_presenter = audio_presenter
        self.closeables = tuple(closeables)
        self.sleeper = sleeper
        self._submitted: queue.SimpleQueue[DeviceInputEvent] = queue.SimpleQueue()
        self._presentation_failures: dict[str, int] = {"braille": 0, "audio": 0}
        self._warned_presentation_failures: set[tuple[str, str]] = set()
        self._started = False
        self._stopped = False

    def start(self) -> tuple[CoordinatorEvent, ...]:
        if self._started:
            raise RuntimeError("Device application is already started")
        if self._stopped:
            raise RuntimeError("Device application cannot restart after stop")
        try:
            events = self.coordinator.start()
            self._started = True
            self._present()
        except BaseException:
            self._stopped = True
            try:
                if self._started:
                    self.coordinator.stop()
                close = getattr(self.coordinator.scanner, "close", None)
                if close is not None:
                    close()
            finally:
                self._close_host_io()
            raise
        return events

    def submit_input(self, event: DeviceInputEvent) -> None:
        if not isinstance(event, DeviceInputEvent):
            raise TypeError("submitted input must be a DeviceInputEvent")
        if self._stopped:
            return
        self._submitted.put(event)

    def step(self) -> tuple[CoordinatorEvent, ...]:
        if not self._started or self._stopped:
            raise RuntimeError("Device application is not running")
        events: list[CoordinatorEvent] = []
        for input_event in self._drain_inputs() + self.controls.poll():
            if (
                self.audio_presenter is not None
                and self.coordinator.state is DeviceFlowState.READING
                and (
                    input_event.control is not DeviceControl.LEVER
                    or input_event.action is InputAction.ACTIVATED
                )
            ):
                self.audio_presenter.interrupt()
            events.extend(self.coordinator.handle_input(input_event))
        events.extend(self.coordinator.poll())
        self._present()
        return tuple(events)

    def run(self) -> None:
        if not self._started:
            self.start()
        try:
            while self.coordinator.state is not DeviceFlowState.STOPPED:
                self.step()
                self.sleeper(self.poll_interval_seconds)
        finally:
            self.stop()

    def stop(self) -> tuple[CoordinatorEvent, ...]:
        if self._stopped:
            return ()
        self._stopped = True
        events: tuple[CoordinatorEvent, ...] = ()
        try:
            if self._started:
                events = self.coordinator.stop()
        finally:
            try:
                close = getattr(self.coordinator.scanner, "close", None)
                if close is not None:
                    close()
            finally:
                self._close_host_io()
        return events

    def _drain_inputs(self) -> tuple[DeviceInputEvent, ...]:
        events: list[DeviceInputEvent] = []
        while True:
            try:
                events.append(self._submitted.get_nowait())
            except queue.Empty:
                return tuple(events)

    def _present(self) -> None:
        if self.presenter is not None:
            self._present_contained("braille", self.presenter)
        if self.audio_presenter is not None:
            self._present_contained("audio", self.audio_presenter)

    @property
    def presentation_failures(self) -> dict[str, int]:
        return dict(self._presentation_failures)

    def _present_contained(self, channel: str, presenter: object) -> None:
        try:
            presenter.present(self.coordinator.reading_snapshot)
        except Exception as exc:
            # Braille and audio are independent projections of one committed
            # reading snapshot.  A physical display/driver failure must not
            # suppress the other projection or terminate navigation.
            self._presentation_failures[channel] += 1
            signature = (channel, type(exc).__name__)
            if signature not in self._warned_presentation_failures:
                self._warned_presentation_failures.add(signature)
                warnings.warn(
                    f"{channel} presentation failed and was contained: {type(exc).__name__}",
                    RuntimeWarning,
                    stacklevel=2,
                )

    def _close_host_io(self) -> None:
        seen: set[int] = set()
        for resource in (self.controls, self.presenter, self.audio_presenter, *self.closeables):
            if resource is None or id(resource) in seen:
                continue
            seen.add(id(resource))
            close = getattr(resource, "close", None)
            if close is not None:
                close()
