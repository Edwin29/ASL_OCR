"""Laptop STM serial adapter for input and braille FRAME responses."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from asl_device.app_config import StmSerialConfig
from asl_device.types import DeviceControl, DeviceInputEvent, InputAction, ReadingSnapshot


class SerialConnection(Protocol):
    def readline(self) -> bytes: ...

    def write(self, data: bytes) -> int: ...

    def close(self) -> None: ...


SerialFactory = Callable[[StmSerialConfig], SerialConnection]

_DIRECTION_TO_CONTROL = {
    "U": DeviceControl.UP,
    "D": DeviceControl.DOWN,
    "L": DeviceControl.LEFT,
    "R": DeviceControl.RIGHT,
    "N": DeviceControl.PAGE_NEXT,
    "P": DeviceControl.PAGE_PREVIOUS,
    "C": DeviceControl.CONFIRM,
    "V": DeviceControl.LEVER,
}
_TOKEN_TO_ACTION = {
    "S": InputAction.SHORT,
    "L": InputAction.LONG,
    "A": InputAction.ACTIVATED,
    "R": InputAction.RELEASED,
}
_VALID_ACTIONS_BY_CONTROL = {
    DeviceControl.UP: {InputAction.SHORT},
    DeviceControl.DOWN: {InputAction.SHORT},
    DeviceControl.LEFT: {InputAction.SHORT},
    DeviceControl.RIGHT: {InputAction.SHORT},
    DeviceControl.PAGE_NEXT: {InputAction.SHORT},
    DeviceControl.PAGE_PREVIOUS: {InputAction.SHORT},
    DeviceControl.CONFIRM: {InputAction.SHORT, InputAction.LONG},
    DeviceControl.LEVER: {InputAction.ACTIVATED, InputAction.RELEASED},
}


class StmSerialControlSource:
    """Poll a bounded number of STM lines and answer every valid HELLO/NAV with FRAME.

    The current STM firmware waits for one FRAME after both its HELLO handshake
    and every navigation command.  Keeping input and presentation on the same
    connection prevents a second writer from interleaving serial responses.
    """

    def __init__(
        self,
        config: StmSerialConfig,
        *,
        serial_factory: SerialFactory | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        max_lines_per_poll: int = 16,
    ) -> None:
        if max_lines_per_poll <= 0:
            raise ValueError("max_lines_per_poll must be positive")
        self.config = config
        self.serial_factory = serial_factory or _open_serial
        self.monotonic = monotonic
        self.max_lines_per_poll = max_lines_per_poll
        self._connection: SerialConnection | None = None
        self._closed = False
        self._connection_epoch = 0
        self._event_counter = 0
        self._response_due = False
        self._last_frame: tuple[int | str, ...] | None = None
        self._last_input: tuple[DeviceControl, InputAction, float] | None = None
        self._next_connect_at = 0.0
        self._retry_seconds = config.reconnect_initial_ms / 1000.0

    @property
    def connected(self) -> bool:
        return self._connection is not None

    def poll(self) -> tuple[DeviceInputEvent, ...]:
        if self._closed:
            return ()
        now = self.monotonic()
        if self._connection is None:
            if now < self._next_connect_at:
                return ()
            self._connect(now)
        connection = self._connection
        if connection is None:
            return ()
        events: list[DeviceInputEvent] = []
        try:
            for _ in range(self.max_lines_per_poll):
                raw = connection.readline()
                if not raw:
                    break
                line = raw.decode("ascii", errors="strict").strip()
                event = self._parse_line(line)
                if event is not None:
                    events.append(event)
        except (OSError, UnicodeError):
            self._disconnect(now)
        return tuple(events)

    def present(self, snapshot: ReadingSnapshot | None) -> None:
        """Write the current reading frame when the board expects a response.

        A blank frame completes the handshake while the application is in
        catalog/scanning states.  Once reading begins, changed snapshots are
        also pushed without waiting for another input.
        """

        connection = self._connection
        if self._closed or connection is None:
            return
        frame = _format_frame(snapshot, self.config.cell_count)
        signature = tuple(frame)
        if not self._response_due and (snapshot is None or signature == self._last_frame):
            return
        try:
            payload = (",".join(str(value) for value in frame) + "\n").encode("ascii")
            if connection.write(payload) != len(payload):
                raise OSError("STM serial write was incomplete")
        except OSError:
            self._disconnect(self.monotonic())
            return
        self._last_frame = signature
        self._response_due = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()

    def _connect(self, now: float) -> None:
        try:
            connection = self.serial_factory(self.config)
        except ImportError as exc:
            raise RuntimeError("pyserial is required for stm_serial controls") from exc
        except OSError:
            self._schedule_retry(now)
            return
        self._connection = connection
        self._connection_epoch += 1
        self._event_counter = 0
        self._last_frame = None
        self._retry_seconds = self.config.reconnect_initial_ms / 1000.0

    def _disconnect(self, now: float) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
        self._response_due = False
        self._last_frame = None
        self._schedule_retry(now)

    def _schedule_retry(self, now: float) -> None:
        self._next_connect_at = now + self._retry_seconds
        self._retry_seconds = min(
            self.config.reconnect_max_ms / 1000.0,
            self._retry_seconds * 2.0,
        )

    def _parse_line(self, line: str) -> DeviceInputEvent | None:
        if line == "HELLO":
            self._response_due = True
            return None
        parts = line.split(",")
        if len(parts) not in {3, 4} or parts[0] != "NAV":
            return None
        control = _DIRECTION_TO_CONTROL.get(parts[1])
        action = _TOKEN_TO_ACTION.get(parts[2])
        if control is None or action is None:
            return None
        if action not in _VALID_ACTIONS_BY_CONTROL[control]:
            return None
        hardware_sequence: int | None = None
        if len(parts) == 4:
            try:
                hardware_sequence = int(parts[3])
            except ValueError:
                return None
            if hardware_sequence < 0:
                return None
        self._response_due = True
        now = self.monotonic()
        previous = self._last_input
        if (
            previous is not None
            and previous[0] is control
            and previous[1] is action
            and now - previous[2] < self.config.debounce_ms / 1000.0
        ):
            return None
        self._last_input = (control, action, now)
        self._event_counter += 1
        suffix = hardware_sequence if hardware_sequence is not None else self._event_counter
        return DeviceInputEvent(
            f"stm-{self._connection_epoch:04d}-{suffix:010d}",
            control,
            action,
            now,
            hardware_sequence,
        )


def _format_frame(snapshot: ReadingSnapshot | None, cell_count: int) -> list[int | str]:
    if snapshot is None:
        state = (0, 0, 0, 0, 0)
        cells = [0] * cell_count
    else:
        cursor = dict(snapshot.cursor)
        state = tuple(
            _cursor_int(cursor, name)
            for name in ("page_index", "node_index", "math_span_index", "braille_offset", "generation")
        )
        cells = list(snapshot.braille_cells[:cell_count])
        cells.extend([0] * (cell_count - len(cells)))
        if any(cell > 63 for cell in cells):
            raise ValueError("STM firmware accepts only six-dot braille cells in [0, 63]")
    return ["FRAME", *state, *cells]


def _cursor_int(cursor: dict[str, object], name: str) -> int:
    value = cursor.get(name, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"reading cursor {name} must be a non-negative integer")
    return value


def _open_serial(config: StmSerialConfig) -> SerialConnection:
    import serial

    return serial.Serial(
        config.port,
        baudrate=config.baudrate,
        timeout=config.read_timeout_ms / 1000.0,
        write_timeout=config.read_timeout_ms / 1000.0,
    )
