from __future__ import annotations

from asl_device.adapters.local_controls import ScriptedControlSource
from asl_device.application import DeviceApplication
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


def test_reading_lever_does_not_interrupt_audio() -> None:
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
    app.submit_input(_input("lever", DeviceControl.LEVER))

    app.step()

    assert audio.interruptions == 0
