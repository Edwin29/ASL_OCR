from __future__ import annotations

import queue
import threading
import time
from collections import deque

import pytest

from asl_device.adapters.stm_serial import StmSerialControlSource
from asl_device.app_config import StmSerialConfig
from asl_device.types import (
    DatapackId,
    DeviceControl,
    InputAction,
    ReadingSessionId,
    ReadingSnapshot,
)


class FakeSerial:
    def __init__(self, lines=(), *, write_delay: float = 0.0) -> None:
        self.lines: queue.Queue[bytes] = queue.Queue()
        for line in lines:
            self.lines.put(line)
        self.writes: list[bytes] = []
        self.closed = 0
        self.fail_read = False
        self.write_delay = write_delay
        self._lock = threading.Lock()

    def readline(self) -> bytes:
        if self.fail_read:
            raise OSError("disconnected")
        try:
            return self.lines.get(timeout=0.005)
        except queue.Empty:
            return b""

    def write(self, data: bytes) -> int:
        if self.write_delay:
            time.sleep(self.write_delay)
        with self._lock:
            self.writes.append(data)
        return len(data)

    def close(self) -> None:
        self.closed += 1

    def push(self, line: bytes) -> None:
        self.lines.put(line)

    def written(self) -> tuple[bytes, ...]:
        with self._lock:
            return tuple(self.writes)


def _config() -> StmSerialConfig:
    return StmSerialConfig(
        "COM5",
        read_timeout_ms=5,
        reconnect_initial_ms=10,
        reconnect_max_ms=20,
    )


def _snapshot(cells=(1, 2, 3), *, generation: int = 6) -> ReadingSnapshot:
    return ReadingSnapshot(
        ReadingSessionId("reading-1"),
        DatapackId("book-1"),
        (
            ("page_index", 2),
            ("node_index", 3),
            ("math_span_index", 4),
            ("braille_offset", 5),
            ("generation", generation),
        ),
        tuple(cells),
    )


def _wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition did not become true")


def _next_events(source: StmSerialControlSource, count: int = 1):
    found = []

    def ready() -> bool:
        found.extend(source.poll())
        return len(found) >= count

    _wait_until(ready)
    return tuple(found)


def test_v2_hello_and_nav_are_acked_before_application_poll() -> None:
    serial = FakeSerial((b"HELLO,2\n",))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial)
    try:
        source.present(None)
        _wait_until(lambda: len(serial.written()) >= 2)
        assert serial.written()[:2] == (
            b"ACK,HELLO,2\n",
            b"FRAME,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\n",
        )
        assert source.protocol_version == 2

        serial.push(b"NAV,U,S,7\n")
        _wait_until(lambda: b"ACK,7\n" in serial.written())

        events = source.poll()
        assert len(events) == 1
        assert events[0].control is DeviceControl.UP
        assert events[0].action is InputAction.SHORT
        assert events[0].hardware_sequence == 7
    finally:
        source.close()


def test_v2_duplicate_sequence_is_reacked_but_applied_once() -> None:
    serial = FakeSerial((b"HELLO,2\n",))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial)
    try:
        source.present(None)
        _wait_until(lambda: source.protocol_version == 2)
        serial.push(b"NAV,R,S,19\n")
        serial.push(b"NAV,R,S,19\n")
        _wait_until(lambda: serial.written().count(b"ACK,19\n") == 2)

        assert len(_next_events(source)) == 1
        time.sleep(0.03)
        assert source.poll() == ()
    finally:
        source.close()


def test_v2_rehandshake_starts_a_new_sequence_epoch_on_the_same_port() -> None:
    serial = FakeSerial((b"HELLO,2\n",))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial)
    try:
        source.present(None)
        _wait_until(lambda: source.protocol_version == 2)
        serial.push(b"NAV,U,S,1\n")
        first = _next_events(source)[0]

        serial.push(b"HELLO,2\n")
        _wait_until(lambda: serial.written().count(b"ACK,HELLO,2\n") == 2)
        serial.push(b"NAV,D,S,1\n")
        second = _next_events(source)[0]

        assert first.control is DeviceControl.UP
        assert second.control is DeviceControl.DOWN
        assert first.event_id != second.event_id
        assert serial.written().count(b"ACK,1\n") == 2
    finally:
        source.close()


def test_v2_changed_frames_are_pushed_independently_and_latest_wins_before_handshake() -> None:
    serial = FakeSerial()
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial)
    try:
        source.present(_snapshot((1,), generation=1))
        source.present(_snapshot((2,), generation=2))
        source.present(_snapshot((3,), generation=3))
        serial.push(b"HELLO,2\n")
        _wait_until(lambda: len(serial.written()) >= 2)

        frames = [line for line in serial.written() if line.startswith(b"FRAME,")]
        assert frames == [b"FRAME,2,3,4,5,3,3,0,0,0,0,0,0,0,0,0\n"]

        source.present(_snapshot((4,), generation=4))
        _wait_until(lambda: len([line for line in serial.written() if line.startswith(b"FRAME,")]) == 2)
        assert serial.written()[-1] == b"FRAME,2,3,4,5,4,4,0,0,0,0,0,0,0,0,0\n"
    finally:
        source.close()


def test_legacy_hello_and_nav_keep_frame_response_contract() -> None:
    serial = FakeSerial((b"HELLO\n",))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial)
    try:
        source.present(None)
        _wait_until(lambda: len(serial.written()) == 1)
        assert source.protocol_version == 1

        serial.push(b"NAV,U,S\n")
        events = _next_events(source)
        assert len(events) == 1
        assert len(serial.written()) == 1

        source.present(_snapshot())
        _wait_until(lambda: len(serial.written()) == 2)
        assert serial.written()[-1] == b"FRAME,2,3,4,5,6,1,2,3,0,0,0,0,0,0,0\n"
    finally:
        source.close()


def test_v2_debounce_still_acks_each_distinct_hardware_sequence() -> None:
    serial = FakeSerial((b"HELLO,2\n",))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial)
    try:
        source.present(None)
        _wait_until(lambda: source.protocol_version == 2)
        serial.push(b"NAV,R,S,1\n")
        serial.push(b"NAV,R,S,2\n")
        _wait_until(lambda: b"ACK,1\n" in serial.written() and b"ACK,2\n" in serial.written())

        assert len(_next_events(source)) == 1
        time.sleep(0.03)
        assert source.poll() == ()
    finally:
        source.close()


def test_v2_full_input_queue_returns_busy_without_false_ack() -> None:
    serial = FakeSerial((b"HELLO,2\n",))
    source = StmSerialControlSource(
        _config(),
        serial_factory=lambda _config: serial,
        input_queue_capacity=1,
    )
    try:
        source.present(None)
        _wait_until(lambda: source.protocol_version == 2)
        serial.push(b"NAV,U,S,1\n")
        serial.push(b"NAV,D,S,2\n")
        _wait_until(lambda: b"NACK,2,BUSY\n" in serial.written())

        assert b"ACK,1\n" in serial.written()
        assert b"ACK,2\n" not in serial.written()
        assert len(source.poll()) == 1
    finally:
        source.close()


def test_present_and_poll_do_not_wait_for_slow_serial_write() -> None:
    serial = FakeSerial((b"HELLO,2\n",), write_delay=0.15)
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial)
    try:
        started = time.monotonic()
        source.present(_snapshot())
        assert time.monotonic() - started < 0.05

        started = time.monotonic()
        assert source.poll() == ()
        assert time.monotonic() - started < 0.05
    finally:
        source.close()


def test_stm_reconnect_uses_bounded_background_backoff() -> None:
    first = FakeSerial()
    first.fail_read = True
    second = FakeSerial((b"HELLO,2\n",))
    connections = deque((first, second))
    source = StmSerialControlSource(
        _config(),
        serial_factory=lambda _config: connections.popleft(),
    )
    try:
        source.present(None)
        _wait_until(lambda: first.closed == 1)
        _wait_until(lambda: source.protocol_version == 2)
        assert second.written()[0] == b"ACK,HELLO,2\n"
    finally:
        source.close()


def test_stm_rejects_cells_the_six_dot_firmware_cannot_render() -> None:
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: FakeSerial())
    try:
        with pytest.raises(ValueError, match="six-dot"):
            source.present(_snapshot((64,)))
    finally:
        source.close()


@pytest.mark.parametrize(
    ("wire", "control", "action"),
    (
        (b"NAV,U,S,1\n", DeviceControl.UP, InputAction.SHORT),
        (b"NAV,D,S,2\n", DeviceControl.DOWN, InputAction.SHORT),
        (b"NAV,L,S,3\n", DeviceControl.LEFT, InputAction.SHORT),
        (b"NAV,R,S,4\n", DeviceControl.RIGHT, InputAction.SHORT),
        (b"NAV,N,S,5\n", DeviceControl.PAGE_NEXT, InputAction.SHORT),
        (b"NAV,P,S,6\n", DeviceControl.PAGE_PREVIOUS, InputAction.SHORT),
        (b"NAV,C,S,7\n", DeviceControl.CONFIRM, InputAction.SHORT),
        (b"NAV,C,L,8\n", DeviceControl.CONFIRM, InputAction.LONG),
        (b"NAV,V,A,9\n", DeviceControl.LEVER, InputAction.ACTIVATED),
        (b"NAV,V,R,10\n", DeviceControl.LEVER, InputAction.RELEASED),
    ),
)
def test_stm_v2_formal_wire_contract(wire, control, action) -> None:
    serial = FakeSerial((b"HELLO,2\n",))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial)
    try:
        source.present(None)
        _wait_until(lambda: source.protocol_version == 2)
        serial.push(wire)

        event = _next_events(source)[0]
        assert event.control is control
        assert event.action is action
        assert any(line.startswith(b"ACK,") for line in serial.written()[2:])
    finally:
        source.close()


@pytest.mark.parametrize(
    "wire",
    (
        b"PAGE,NEXT\n",
        b"NAV,U,L,1\n",
        b"NAV,N,L,2\n",
        b"NAV,V,S,3\n",
        b"NAV,C,A,4\n",
        b"NAV,U,S,-1\n",
        b"NAV,U,S,0\n",
        b"NAV,U,S,4294967296\n",
        b"NAV,U,S,not-a-number\n",
    ),
)
def test_stm_rejects_packets_outside_hardware_contract(wire) -> None:
    serial = FakeSerial((b"HELLO,2\n",))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial)
    try:
        source.present(None)
        _wait_until(lambda: source.protocol_version == 2)
        writes_before = len(serial.written())
        serial.push(wire)
        time.sleep(0.03)

        assert source.poll() == ()
        assert len(serial.written()) == writes_before
    finally:
        source.close()
