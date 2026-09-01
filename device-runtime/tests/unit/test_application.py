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


def _input(event_id: str) -> DeviceInputEvent:
    return DeviceInputEvent(event_id, DeviceControl.CONFIRM, InputAction.SHORT, 0.0)


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
