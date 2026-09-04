from __future__ import annotations

import pytest

from asl_device.adapters.local_controls import ScriptedControlSource
from asl_device.application import DeviceApplication
from asl_device.hold_repeat import HoldRepeatController
from asl_device.types import DeviceControl, DeviceFlowState, DeviceInputEvent, InputAction


class FakeScanner:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class FakeCoordinator:
    def __init__(self) -> None:
        self.state = DeviceFlowState.BOOTING
        self.reading_snapshot = None
        self.inputs: list[str] = []
        self.polls = 0
        self.stops = 0
        self.scanner = FakeScanner()

    def start(self):
        self.state = DeviceFlowState.SELECTING_DATAPACK
        return ()

    def handle_input(self, event):
        self.inputs.append(event.event_id)
        return ()

    def poll(self):
        self.polls += 1
        return ()

    def stop(self):
        self.stops += 1
        self.state = DeviceFlowState.STOPPED
        return ()


def _input(event_id: str, control: DeviceControl = DeviceControl.CONFIRM) -> DeviceInputEvent:
    return DeviceInputEvent(event_id, control, InputAction.SHORT, 0.0)


def test_application_drives_inputs_and_coordinator_on_one_step() -> None:
    coordinator = FakeCoordinator()
    controls = ScriptedControlSource(((_input("scripted"),),))
    app = DeviceApplication(coordinator, controls, poll_interval_seconds=0.01)
    app.start()
    app.submit_input(_input("submitted"))

    assert app.step() == ()
    assert coordinator.inputs == ["submitted", "scripted"]
    assert coordinator.polls == 1


def test_application_stop_closes_resources_once() -> None:
    coordinator = FakeCoordinator()
    app = DeviceApplication(
        coordinator,
        ScriptedControlSource(),
        poll_interval_seconds=0.01,
    )
    app.start()

    app.stop()
    app.stop()

    assert coordinator.stops == 1
    assert coordinator.scanner.closed == 1


def test_application_presents_after_input_and_closes_shared_stm_once() -> None:
    coordinator = FakeCoordinator()

    class StmIo(ScriptedControlSource):
        def __init__(self):
            super().__init__(((_input("stm"),),))
            self.presented = []
            self.closed = 0

        def present(self, snapshot):
            self.presented.append(snapshot)

        def close(self):
            self.closed += 1

    stm = StmIo()
    app = DeviceApplication(coordinator, stm, poll_interval_seconds=0.01, presenter=stm)

    app.start()
    app.step()
    app.stop()

    assert coordinator.inputs == ["stm"]
    assert stm.presented == [None, None]
    assert stm.closed == 1


def test_reading_navigation_interrupts_audio_before_command_and_closes_once() -> None:
    coordinator = FakeCoordinator()
    coordinator.state = DeviceFlowState.READING
    order = []

    def handle_input(event):
        order.append(("command", event.event_id))
        return ()

    coordinator.handle_input = handle_input

    class Audio:
        def __init__(self):
            self.closed = 0

        def present(self, snapshot):
            order.append(("present", snapshot))

        def interrupt(self):
            order.append(("interrupt", None))

        def close(self):
            self.closed += 1

    audio = Audio()
    app = DeviceApplication(
        coordinator,
        ScriptedControlSource(),
        poll_interval_seconds=0.01,
        audio_presenter=audio,
    )
    app._started = True
    app.submit_input(_input("next", DeviceControl.PAGE_NEXT))

    app.step()
    app.stop()

    assert order[:2] == [("interrupt", None), ("command", "next")]
    assert audio.closed == 1


def test_reading_snapshot_reaches_braille_before_audio_as_one_generation() -> None:
    coordinator = FakeCoordinator()
    snapshot = object()
    coordinator.reading_snapshot = snapshot
    order = []

    class Presenter:
        def present(self, value):
            order.append(("braille", value))

        def close(self):
            pass

    class Audio:
        def present(self, value):
            order.append(("audio", value))

        def interrupt(self):
            pass

        def close(self):
            pass

    app = DeviceApplication(
        coordinator,
        ScriptedControlSource(),
        poll_interval_seconds=0.01,
        presenter=Presenter(),
        audio_presenter=Audio(),
    )

    app._present()

    assert order == [("braille", snapshot), ("audio", snapshot)]


def test_braille_presentation_failure_is_contained_and_audio_still_runs() -> None:
    coordinator = FakeCoordinator()
    snapshot = object()
    coordinator.reading_snapshot = snapshot
    heard = []

    class BrokenBraille:
        def present(self, value):
            raise ValueError("bad hardware frame")

        def close(self):
            pass

    class Audio:
        def present(self, value):
            heard.append(value)

        def interrupt(self):
            pass

        def close(self):
            pass

    app = DeviceApplication(
        coordinator,
        ScriptedControlSource(),
        poll_interval_seconds=0.01,
        presenter=BrokenBraille(),
        audio_presenter=Audio(),
    )

    with pytest.warns(RuntimeWarning, match="braille presentation failed and was contained"):
        app._present()

    assert heard == [snapshot]
    assert app.presentation_failures == {"braille": 1, "audio": 0}


def test_reading_mode_lever_interrupts_audio_before_mode_transition() -> None:
    coordinator = FakeCoordinator()
    coordinator.state = DeviceFlowState.READING

    class Audio:
        interruptions = 0

        def present(self, snapshot):
            pass

        def interrupt(self):
            self.interruptions += 1

        def close(self):
            pass

    audio = Audio()
    app = DeviceApplication(
        coordinator,
        ScriptedControlSource(),
        poll_interval_seconds=0.01,
        audio_presenter=audio,
    )
    app._started = True
    app.submit_input(
        DeviceInputEvent(
            "lever",
            DeviceControl.LEVER,
            InputAction.ACTIVATED,
            0.0,
        )
    )

    app.step()

    assert audio.interruptions == 1


def test_reading_mode_alignment_lever_does_not_interrupt_current_audio() -> None:
    coordinator = FakeCoordinator()
    coordinator.state = DeviceFlowState.READING

    class Audio:
        interruptions = 0

        def present(self, snapshot):
            pass

        def interrupt(self):
            self.interruptions += 1

        def close(self):
            pass

    audio = Audio()
    app = DeviceApplication(
        coordinator,
        ScriptedControlSource(),
        poll_interval_seconds=0.01,
        audio_presenter=audio,
    )
    app._started = True
    app.submit_input(
        DeviceInputEvent(
            "lever",
            DeviceControl.LEVER,
            InputAction.RELEASED,
            0.0,
        )
    )

    app.step()

    assert audio.interruptions == 0


def test_down_hold_repeats_only_until_release_and_release_keeps_final_audio() -> None:
    coordinator = FakeCoordinator()
    coordinator.state = DeviceFlowState.READING

    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

    class Audio:
        interruptions = 0

        def present(self, snapshot):
            pass

        def interrupt(self):
            self.interruptions += 1

        def close(self):
            pass

    clock = Clock()
    audio = Audio()
    app = DeviceApplication(
        coordinator,
        ScriptedControlSource(),
        poll_interval_seconds=0.01,
        audio_presenter=audio,
        hold_repeat=HoldRepeatController(monotonic=clock.monotonic),
    )
    app._started = True
    app.submit_input(DeviceInputEvent("edge-a", DeviceControl.DOWN, InputAction.ACTIVATED, 0.0))
    app.step()
    assert coordinator.inputs == ["edge-a-hold-00000000"]

    clock.now = 0.650
    app.step()
    assert coordinator.inputs[-1] == "edge-a-hold-00000001"

    app.submit_input(DeviceInputEvent("edge-r", DeviceControl.DOWN, InputAction.RELEASED, 0.650))
    app.step()
    interruptions_at_release = audio.interruptions
    clock.now = 10.0
    app.step()

    assert len(coordinator.inputs) == 2
    assert interruptions_at_release == 2
    assert audio.interruptions == 2


def test_release_queued_during_slow_initial_command_prevents_second_dispatch() -> None:
    coordinator = FakeCoordinator()

    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

    clock = Clock()
    release = DeviceInputEvent("edge-r", DeviceControl.DOWN, InputAction.RELEASED, 0.7)

    class Controls(ScriptedControlSource):
        def __init__(self):
            super().__init__(
                (
                    (DeviceInputEvent("edge-a", DeviceControl.DOWN, InputAction.ACTIVATED, 0.0),),
                    (release,),
                )
            )

    original_handle = coordinator.handle_input

    def slow_handle(event):
        result = original_handle(event)
        clock.now = 0.7
        return result

    coordinator.handle_input = slow_handle
    app = DeviceApplication(
        coordinator,
        Controls(),
        poll_interval_seconds=0.01,
        hold_repeat=HoldRepeatController(monotonic=clock.monotonic),
    )
    app.start()

    app.step()
    assert coordinator.inputs == ["edge-a-hold-00000000"]
    app.step()
    assert coordinator.inputs == ["edge-a-hold-00000000"]
