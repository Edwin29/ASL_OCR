from __future__ import annotations

from asl_device.hold_repeat import HoldRepeatController
from asl_device.types import DeviceControl, DeviceInputEvent, InputAction


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


def edge(event_id: str, action: InputAction, clock: FakeClock) -> DeviceInputEvent:
    return DeviceInputEvent(event_id, DeviceControl.DOWN, action, clock.now)


def test_press_repeats_on_deadlines_and_release_stops() -> None:
    clock = FakeClock()
    repeat = HoldRepeatController(monotonic=clock.monotonic)

    immediate = repeat.apply_edge(edge("down-a", InputAction.ACTIVATED, clock))
    assert [event.action for event in immediate] == [InputAction.SHORT]
    clock.now = 0.649
    assert repeat.due() == ()
    clock.now = 0.650
    assert len(repeat.due()) == 1
    clock.now = 0.829
    assert repeat.due() == ()
    clock.now = 0.831
    assert len(repeat.due()) == 1

    repeat.apply_edge(edge("down-r", InputAction.RELEASED, clock))
    clock.now = 100.0
    assert repeat.due() == ()


def test_delayed_loop_never_catches_up_and_duplicate_activation_is_noop() -> None:
    clock = FakeClock()
    repeat = HoldRepeatController(monotonic=clock.monotonic)
    assert len(repeat.apply_edge(edge("down-a", InputAction.ACTIVATED, clock))) == 1

    clock.now = 0.4
    assert repeat.apply_edge(edge("duplicate-a", InputAction.ACTIVATED, clock)) == ()
    clock.now = 1.650
    assert len(repeat.due()) == 1
    assert repeat.due() == ()
    clock.now = 1.829
    assert repeat.due() == ()
    clock.now = 1.831
    assert len(repeat.due()) == 1


def test_release_at_due_deadline_wins_when_applied_before_timer_check() -> None:
    clock = FakeClock()
    repeat = HoldRepeatController(monotonic=clock.monotonic)
    repeat.apply_edge(edge("down-a", InputAction.ACTIVATED, clock))
    clock.now = 0.650
    repeat.apply_edge(edge("down-r", InputAction.RELEASED, clock))
    assert repeat.due() == ()
