"""Minimal local controls for E0-Core; physical STM input remains a later adapter."""

from __future__ import annotations

import queue
import sys
import threading
import time
from collections import deque
from collections.abc import Iterable
from typing import Protocol, TextIO

from asl_device.types import DeviceControl, DeviceInputEvent, InputAction


class ControlSource(Protocol):
    def poll(self) -> tuple[DeviceInputEvent, ...]: ...

    def close(self) -> None: ...


class NullControlSource:
    def poll(self) -> tuple[DeviceInputEvent, ...]:
        return ()

    def close(self) -> None:
        return None


class ScriptedControlSource:
    def __init__(self, batches: Iterable[Iterable[DeviceInputEvent]] = ()) -> None:
        self._batches = deque(tuple(batch) for batch in batches)

    def poll(self) -> tuple[DeviceInputEvent, ...]:
        return self._batches.popleft() if self._batches else ()

    def close(self) -> None:
        self._batches.clear()


class ConsoleControlSource:
    """Read simple newline commands without mutating the Coordinator off-thread."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdin
        self._lines: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._closed = False
        self._counter = 0
        self._thread = threading.Thread(target=self._read_lines, name="asl-local-controls", daemon=True)
        self._thread.start()

    def poll(self) -> tuple[DeviceInputEvent, ...]:
        events: list[DeviceInputEvent] = []
        while True:
            try:
                line = self._lines.get_nowait()
            except queue.Empty:
                break
            command = line.strip().lower()
            if not command:
                continue
            control, action = _parse_command(command)
            self._counter += 1
            events.append(
                DeviceInputEvent(
                    f"console-{self._counter:08d}",
                    control,
                    action,
                    time.monotonic(),
                )
            )
        return tuple(events)

    def close(self) -> None:
        self._closed = True

    def _read_lines(self) -> None:
        while not self._closed:
            line = self.stream.readline()
            if not line:
                return
            self._lines.put(line)


def _parse_command(command: str) -> tuple[DeviceControl, InputAction]:
    aliases = {
        "next": DeviceControl.PAGE_NEXT,
        "previous": DeviceControl.PAGE_PREVIOUS,
        "prev": DeviceControl.PAGE_PREVIOUS,
    }
    parts = command.replace("-", " ").split()
    control_text = parts[0]
    try:
        control = aliases[control_text] if control_text in aliases else DeviceControl(control_text)
    except ValueError as exc:
        raise ValueError(f"unknown local control command: {command}") from exc
    action_text = parts[1] if len(parts) > 1 else "short"
    try:
        action = InputAction(action_text)
    except ValueError as exc:
        raise ValueError(f"unknown local control action: {command}") from exc
    return control, action
