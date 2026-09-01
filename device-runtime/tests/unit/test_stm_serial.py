from __future__ import annotations

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


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeSerial:
    def __init__(self, lines=()) -> None:
        self.lines = deque(lines)
        self.writes: list[bytes] = []
        self.closed = 0
        self.fail_read = False

    def readline(self) -> bytes:
        if self.fail_read:
            raise OSError("disconnected")
        return self.lines.popleft() if self.lines else b""

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def close(self) -> None:
        self.closed += 1


def _config() -> StmSerialConfig:
    return StmSerialConfig("COM5", reconnect_initial_ms=100, reconnect_max_ms=400)


def _snapshot(cells=(1, 2, 3)) -> ReadingSnapshot:
    return ReadingSnapshot(
        ReadingSessionId("reading-1"),
        DatapackId("book-1"),
        (
            ("page_index", 2),
            ("node_index", 3),
            ("math_span_index", 4),
            ("braille_offset", 5),
            ("generation", 6),
        ),
        tuple(cells),
    )


def test_stm_hello_and_nav_receive_frame_on_one_serial_connection() -> None:
    clock = ManualClock()
    serial = FakeSerial((b"HELLO\n",))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial, monotonic=clock)

    assert source.poll() == ()
    source.present(None)
    assert serial.writes == [b"FRAME,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\n"]

    clock.now = 1.0
    serial.lines.append(b"NAV,U,S\n")
    events = source.poll()
    assert len(events) == 1
    assert events[0].control is DeviceControl.UP
    assert events[0].action is InputAction.SHORT
    source.present(_snapshot())
    assert serial.writes[-1] == b"FRAME,2,3,4,5,6,1,2,3,0,0,0,0,0,0,0\n"


def test_stm_host_debounce_does_not_skip_required_frame_response() -> None:
    clock = ManualClock()
    serial = FakeSerial((b"NAV,R,S\n",))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial, monotonic=clock)
    assert len(source.poll()) == 1
    source.present(_snapshot())

    clock.now = 0.01
    serial.lines.append(b"NAV,R,S\n")
    assert source.poll() == ()
    source.present(_snapshot())

    assert len(serial.writes) == 2


def test_stm_reconnect_uses_bounded_backoff() -> None:
    clock = ManualClock()
    first = FakeSerial()
    first.fail_read = True
    second = FakeSerial((b"HELLO\n",))
    connections = deque((first, second))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: connections.popleft(), monotonic=clock)

    assert source.poll() == ()
    assert first.closed == 1
    assert not source.connected
    clock.now = 0.05
    assert source.poll() == ()
    clock.now = 0.1
    assert source.poll() == ()
    assert source.connected
    source.present(None)
    assert second.writes


def test_stm_rejects_cells_the_six_dot_firmware_cannot_render() -> None:
    serial = FakeSerial((b"HELLO\n",))
    source = StmSerialControlSource(_config(), serial_factory=lambda _config: serial)
    source.poll()

    with pytest.raises(ValueError, match="six-dot"):
        source.present(_snapshot((64,)))
