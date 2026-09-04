from __future__ import annotations

import io
import time

import pytest

from asl_device.adapters.local_controls import ConsoleControlSource, _parse_command
from asl_device.types import DeviceControl, InputAction


def _read_events(source: ConsoleControlSource, expected: int) -> tuple:
    events = ()
    deadline = time.monotonic() + 1.0
    while len(events) < expected and time.monotonic() < deadline:
        events += source.poll()
        if len(events) < expected:
            time.sleep(0.001)
    source.close()
    assert len(events) == expected
    return events


def test_console_event_ids_include_injected_process_namespace_and_counter() -> None:
    source = ConsoleControlSource(
        io.StringIO("down\nconfirm\n"),
        event_namespace="process-test-a",
    )

    events = _read_events(source, 2)

    assert [event.event_id for event in events] == [
        "console-process-test-a-00000001",
        "console-process-test-a-00000002",
    ]


def test_separate_console_processes_do_not_reuse_first_event_id() -> None:
    first = ConsoleControlSource(io.StringIO("confirm\n"))
    second = ConsoleControlSource(io.StringIO("confirm\n"))

    first_event = _read_events(first, 1)[0]
    second_event = _read_events(second, 1)[0]

    assert first_event.event_id != second_event.event_id
    assert len(first_event.event_id + ":scan-open") <= 128
    assert len(second_event.event_id + ":scan-open") <= 128


@pytest.mark.parametrize(
    "namespace",
    ("", "contains space", "한글", "a" * 81, "-leading-hyphen"),
)
def test_console_rejects_unsafe_event_namespace(namespace: str) -> None:
    with pytest.raises(ValueError, match="event_namespace"):
        ConsoleControlSource(io.StringIO(), event_namespace=namespace)


def test_console_down_press_release_and_single_step_contract() -> None:
    assert _parse_command("down") == (DeviceControl.DOWN, InputAction.SHORT)
    assert _parse_command("down press") == (DeviceControl.DOWN, InputAction.ACTIVATED)
    assert _parse_command("down release") == (DeviceControl.DOWN, InputAction.RELEASED)


def test_console_rejects_navigation_long() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        _parse_command("down long")
