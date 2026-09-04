"""Asynchronous Laptop STM serial input and braille FRAME transport."""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
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
_PROTOCOL_V1 = 1
_PROTOCOL_V2 = 2
_INPUT_QUEUE_CAPACITY = 128
_SEQUENCE_WINDOW = 256
_MAX_UINT32 = (1 << 32) - 1


class StmSerialControlSource:
    """Own one serial connection on a dedicated bounded I/O worker.

    Protocol v2 separates transport acceptance from presentation: ``HELLO,2``
    receives ``ACK,HELLO,2`` and every valid ``NAV,...,<sequence>`` receives an
    immediate ``ACK,<sequence>`` before the coordinator handles the command.
    Changed FRAME snapshots are then pushed independently with latest-wins
    coalescing.

    Legacy ``HELLO`` and three-field ``NAV`` remain supported. A legacy NAV
    still receives exactly one FRAME after the next application presentation,
    preserving the blocking firmware contract while new firmware migrates.
    """

    def __init__(
        self,
        config: StmSerialConfig,
        *,
        serial_factory: SerialFactory | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        max_lines_per_poll: int = 16,
        input_queue_capacity: int = _INPUT_QUEUE_CAPACITY,
    ) -> None:
        if max_lines_per_poll <= 0:
            raise ValueError("max_lines_per_poll must be positive")
        if input_queue_capacity <= 0:
            raise ValueError("input_queue_capacity must be positive")
        self.config = config
        self.serial_factory = serial_factory or _open_serial
        self.monotonic = monotonic
        self.max_lines_per_poll = max_lines_per_poll

        self._events: queue.Queue[DeviceInputEvent] = queue.Queue(input_queue_capacity)
        self._state_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connection: SerialConnection | None = None
        self._protocol_version: int | None = None
        self._worker_error: BaseException | None = None

        initial_frame = tuple(_format_frame(None, self.config.cell_count))
        self._desired_frame = initial_frame
        self._desired_frame_payload = _encode_frame(initial_frame)
        self._desired_frame_version = 0
        self._presentation_counter = 0

    @property
    def connected(self) -> bool:
        with self._state_lock:
            return self._connection is not None

    @property
    def protocol_version(self) -> int | None:
        with self._state_lock:
            return self._protocol_version

    def poll(self) -> tuple[DeviceInputEvent, ...]:
        if self._stop.is_set():
            return ()
        self._ensure_worker()
        self._raise_worker_error()
        events: list[DeviceInputEvent] = []
        for _ in range(self.max_lines_per_poll):
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return tuple(events)

    def present(self, snapshot: ReadingSnapshot | None) -> None:
        """Publish the latest desired braille frame without serial blocking."""

        if self._stop.is_set():
            return
        frame = tuple(_format_frame(snapshot, self.config.cell_count))
        payload = _encode_frame(frame)
        with self._state_lock:
            self._presentation_counter += 1
            if frame != self._desired_frame:
                self._desired_frame = frame
                self._desired_frame_payload = payload
                self._desired_frame_version += 1
        self._ensure_worker()
        self._raise_worker_error()
        self._wake.set()

    def close(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.config.read_timeout_ms / 1000.0 * 4.0))

    def _ensure_worker(self) -> None:
        if self._thread is not None:
            return
        with self._start_lock:
            if self._thread is not None or self._stop.is_set():
                return
            self._thread = threading.Thread(
                target=self._io_loop,
                name="asl-stm-serial-io",
                daemon=True,
            )
            self._thread.start()

    def _raise_worker_error(self) -> None:
        with self._state_lock:
            error = self._worker_error
        if error is not None:
            raise RuntimeError("STM serial I/O worker failed") from error

    def _io_loop(self) -> None:
        connection: SerialConnection | None = None
        retry_seconds = self.config.reconnect_initial_ms / 1000.0
        next_connect_at = 0.0
        connection_epoch = 0
        event_counter = 0
        protocol_version: int | None = None
        handshake_seen = False
        sent_frame_version = -1
        legacy_response_after: int | None = None
        last_input: tuple[DeviceControl, InputAction, float] | None = None
        seen_sequences: set[int] = set()
        sequence_order: deque[int] = deque()

        try:
            while not self._stop.is_set():
                now = self.monotonic()
                if connection is None:
                    if now < next_connect_at:
                        self._wait(min(next_connect_at - now, 0.1))
                        continue
                    try:
                        connection = self.serial_factory(self.config)
                    except ImportError as exc:
                        raise RuntimeError("pyserial is required for stm_serial controls") from exc
                    except OSError:
                        next_connect_at = now + retry_seconds
                        retry_seconds = min(
                            self.config.reconnect_max_ms / 1000.0,
                            retry_seconds * 2.0,
                        )
                        self._wait(min(retry_seconds, 0.1))
                        continue
                    connection_epoch += 1
                    event_counter = 0
                    protocol_version = None
                    handshake_seen = False
                    sent_frame_version = -1
                    legacy_response_after = None
                    last_input = None
                    seen_sequences.clear()
                    sequence_order.clear()
                    retry_seconds = self.config.reconnect_initial_ms / 1000.0
                    with self._state_lock:
                        self._connection = connection
                        self._protocol_version = None

                try:
                    raw = connection.readline()
                    if raw:
                        line = raw.decode("ascii", errors="strict").strip()
                        if line == "HELLO,2":
                            if handshake_seen:
                                connection_epoch += 1
                            event_counter = 0
                            last_input = None
                            seen_sequences.clear()
                            sequence_order.clear()
                            legacy_response_after = None
                            self._write(connection, b"ACK,HELLO,2\n")
                            protocol_version = _PROTOCOL_V2
                            handshake_seen = True
                            with self._state_lock:
                                self._protocol_version = protocol_version
                                payload = self._desired_frame_payload
                                version = self._desired_frame_version
                            self._write(connection, payload)
                            sent_frame_version = version
                        elif line == "HELLO":
                            if handshake_seen:
                                connection_epoch += 1
                            event_counter = 0
                            last_input = None
                            seen_sequences.clear()
                            sequence_order.clear()
                            legacy_response_after = None
                            protocol_version = _PROTOCOL_V1
                            handshake_seen = True
                            with self._state_lock:
                                self._protocol_version = protocol_version
                                payload = self._desired_frame_payload
                            self._write(connection, payload)
                        else:
                            parsed = _parse_nav(line)
                            if parsed is not None:
                                control, action, hardware_sequence = parsed
                                now = self.monotonic()
                                duplicate_sequence = (
                                    hardware_sequence is not None
                                    and hardware_sequence in seen_sequences
                                )
                                debounced = (
                                    last_input is not None
                                    and last_input[0] is control
                                    and last_input[1] is action
                                    and now - last_input[2] < self.config.debounce_ms / 1000.0
                                )
                                if hardware_sequence is not None:
                                    if self._events.full() and not duplicate_sequence and not debounced:
                                        self._write(
                                            connection,
                                            f"NACK,{hardware_sequence},BUSY\n".encode("ascii"),
                                        )
                                        continue
                                    self._write(
                                        connection,
                                        f"ACK,{hardware_sequence}\n".encode("ascii"),
                                    )
                                    protocol_version = _PROTOCOL_V2
                                    handshake_seen = True
                                    with self._state_lock:
                                        self._protocol_version = protocol_version
                                else:
                                    protocol_version = _PROTOCOL_V1
                                    handshake_seen = True
                                    with self._state_lock:
                                        self._protocol_version = protocol_version
                                        legacy_response_after = self._presentation_counter + 1

                                if not duplicate_sequence and not debounced:
                                    last_input = (control, action, now)
                                    event_counter += 1
                                    suffix = (
                                        hardware_sequence
                                        if hardware_sequence is not None
                                        else event_counter
                                    )
                                    event = DeviceInputEvent(
                                        f"stm-{connection_epoch:04d}-{suffix:010d}",
                                        control,
                                        action,
                                        now,
                                        hardware_sequence,
                                    )
                                    try:
                                        self._events.put_nowait(event)
                                    except queue.Full:
                                        if hardware_sequence is None:
                                            legacy_response_after = None
                                    if hardware_sequence is not None:
                                        seen_sequences.add(hardware_sequence)
                                        sequence_order.append(hardware_sequence)
                                        if len(sequence_order) > _SEQUENCE_WINDOW:
                                            seen_sequences.discard(sequence_order.popleft())

                    if handshake_seen and protocol_version == _PROTOCOL_V2:
                        with self._state_lock:
                            payload = self._desired_frame_payload
                            version = self._desired_frame_version
                        if version != sent_frame_version:
                            self._write(connection, payload)
                            sent_frame_version = version
                    elif legacy_response_after is not None:
                        with self._state_lock:
                            counter = self._presentation_counter
                            payload = self._desired_frame_payload
                        if counter >= legacy_response_after:
                            self._write(connection, payload)
                            legacy_response_after = None
                except (OSError, UnicodeError):
                    self._close_connection(connection)
                    connection = None
                    protocol_version = None
                    handshake_seen = False
                    legacy_response_after = None
                    with self._state_lock:
                        self._connection = None
                        self._protocol_version = None
                    now = self.monotonic()
                    next_connect_at = now + retry_seconds
                    retry_seconds = min(
                        self.config.reconnect_max_ms / 1000.0,
                        retry_seconds * 2.0,
                    )
                    continue

                if not raw:
                    self._wait(self.config.read_timeout_ms / 1000.0)
        except Exception as exc:
            with self._state_lock:
                self._worker_error = exc
        finally:
            if connection is not None:
                self._close_connection(connection)
            with self._state_lock:
                self._connection = None
                self._protocol_version = None

    def _wait(self, timeout: float) -> None:
        self._wake.wait(max(0.0, timeout))
        self._wake.clear()

    @staticmethod
    def _write(connection: SerialConnection, payload: bytes) -> None:
        if connection.write(payload) != len(payload):
            raise OSError("STM serial write was incomplete")

    @staticmethod
    def _close_connection(connection: SerialConnection) -> None:
        try:
            connection.close()
        except OSError:
            pass


def _parse_nav(line: str) -> tuple[DeviceControl, InputAction, int | None] | None:
    parts = line.split(",")
    if len(parts) not in {3, 4} or parts[0] != "NAV":
        return None
    control = _DIRECTION_TO_CONTROL.get(parts[1])
    action = _TOKEN_TO_ACTION.get(parts[2])
    if control is None or action is None or action not in _VALID_ACTIONS_BY_CONTROL[control]:
        return None
    hardware_sequence: int | None = None
    if len(parts) == 4:
        try:
            hardware_sequence = int(parts[3])
        except ValueError:
            return None
        if not 1 <= hardware_sequence <= _MAX_UINT32:
            return None
    return control, action, hardware_sequence


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


def _encode_frame(frame: tuple[int | str, ...]) -> bytes:
    return (",".join(str(value) for value in frame) + "\n").encode("ascii")


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
