"""Host-owned hold-to-repeat lifecycle for physical navigation buttons."""

from __future__ import annotations

import time
from collections.abc import Callable

from .types import DeviceControl, DeviceInputEvent, InputAction


class HoldRepeatController:
    """Translate DOWN press/release edges into paced DOWN SHORT commands.

    The controller intentionally emits at most one command per ``due`` call.
    A delayed application loop therefore never catches up missed timer ticks
    with a burst after the user releases the button.
    """

    def __init__(
        self,
        *,
        initial_delay_seconds: float = 0.650,
        interval_seconds: float = 0.180,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0.300 <= initial_delay_seconds <= 1.500:
            raise ValueError("hold repeat initial delay must be in [0.300, 1.500] seconds")
        if not 0.100 <= interval_seconds <= 1.000:
            raise ValueError("hold repeat interval must be in [0.100, 1.000] seconds")
        self.initial_delay_seconds = initial_delay_seconds
        self.interval_seconds = interval_seconds
        self.monotonic = monotonic
        self._activation: DeviceInputEvent | None = None
        self._next_due: float | None = None
        self._counter = 0

    @property
    def active(self) -> bool:
        return self._activation is not None

    def apply_edge(self, event: DeviceInputEvent) -> tuple[DeviceInputEvent, ...]:
        if event.control is not DeviceControl.DOWN or event.action not in {
            InputAction.ACTIVATED,
            InputAction.RELEASED,
        }:
            raise ValueError("hold repeat accepts only DOWN activated/released edges")
        if event.action is InputAction.RELEASED:
            self.cancel()
            return ()
        if self.active:
            return ()
        self._activation = event
        self._counter = 0
        self._next_due = self.monotonic() + self.initial_delay_seconds
        return (self._short_event(),)

    def due(self) -> tuple[DeviceInputEvent, ...]:
        now = self.monotonic()
        if self._activation is None or self._next_due is None or now < self._next_due:
            return ()
        event = self._short_event()
        self._next_due = now + self.interval_seconds
        return (event,)

    def cancel(self) -> None:
        self._activation = None
        self._next_due = None
        self._counter = 0

    def _short_event(self) -> DeviceInputEvent:
        activation = self._activation
        assert activation is not None
        event = DeviceInputEvent(
            event_id=f"{activation.event_id}-hold-{self._counter:08d}",
            control=DeviceControl.DOWN,
            action=InputAction.SHORT,
            at_monotonic=self.monotonic(),
        )
        self._counter += 1
        return event
