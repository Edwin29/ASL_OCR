from __future__ import annotations

from collections import deque
from pathlib import Path

from asl_device.adapters.stm_serial import StmSerialControlSource
from asl_device.app_config import StmSerialConfig
from asl_device.coordinator import DeviceFlowCoordinator
from asl_device.types import DeviceFlowState, DeviceId, DeviceOperatingMode
from tests.unit.fakes import (
    CollectingFeedback,
    FakeCatalogPort,
    FakeDeliveryPort,
    FakeReadingSessionPort,
    FakeScannerRuntime,
    FakeScanSessionPort,
    ManualClock,
    ready_entry,
)


class FakeSerial:
    def __init__(self) -> None:
        self.lines = deque()
        self.writes = []

    def readline(self):
        return self.lines.popleft() if self.lines else b""

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def close(self):
        pass


def test_actual_stm_wire_selects_ready_datapack_for_reading_without_scan() -> None:
    serial = FakeSerial()
    source = StmSerialControlSource(
        StmSerialConfig("COM5"),
        serial_factory=lambda _config: serial,
    )
    clock = ManualClock()
    catalog = FakeCatalogPort((ready_entry(),))
    scan = FakeScanSessionPort()
    scanner = FakeScannerRuntime()
    reading = FakeReadingSessionPort()
    coordinator = DeviceFlowCoordinator(
        device_id=DeviceId("device-1"),
        viewport_size=10,
        clock=clock,
        catalog_port=catalog,
        scan_session_port=scan,
        scanner=scanner,
        delivery=FakeDeliveryPort(),
        reading=reading,
        feedback=CollectingFeedback(),
    )
    coordinator.start()

    for wire in (
        b"NAV,V,R\n",
        b"NAV,C,S\n",
        b"NAV,D,S\n",
        b"NAV,C,L\n",
        b"NAV,C,S\n",
    ):
        serial.lines.append(wire)
        for event in source.poll():
            coordinator.handle_input(event)
        source.present(coordinator.reading_snapshot)

    assert coordinator.operating_mode is DeviceOperatingMode.READING
    assert coordinator.state is DeviceFlowState.READING
    assert scan.open_calls == []
    assert scanner.start_calls == []
    assert len(reading.open_calls) == 2
    assert len(reading.command_calls) == 1
    assert len(serial.writes) == 5
    assert serial.writes[-1].startswith(b"FRAME,3,7,0,0,0,1,2,3")


def test_checked_in_stm_source_and_cubemx_pin_contract_are_synchronized() -> None:
    repository = Path(__file__).resolve().parents[3]
    firmware = repository / "hardware/stm32/kitel2026final"
    main_c = (firmware / "Core/Src/main.c").read_text(encoding="utf-8")
    main_h = (firmware / "Core/Inc/main.h").read_text(encoding="utf-8")
    ioc_lines = (firmware / "kitel2026final.ioc").read_text(encoding="utf-8").splitlines()
    ioc = dict(line.split("=", 1) for line in ioc_lines if "=" in line)

    assert "PAGE,NEXT" not in main_c
    assert "#define BUTTON_REPEAT_DELAY_MS      650U" in main_c
    assert "#define BUTTON_REPEAT_INTERVAL_MS   180U" in main_c
    for call in (
        "SendControlAction('U', 'S')",
        "SendControlAction('D', 'S')",
        "SendControlAction('L', 'S')",
        "SendControlAction('R', 'S')",
        "SendControlAction('N', 'S')",
        "SendControlAction('P', 'S')",
        "SendControlAction('C', action)",
        "SendControlAction('V', action)",
    ):
        assert call in main_c

    expected = {
        "PA0-WKUP": ("UP", "GPIO_PIN_0", "GPIOA"),
        "PA1": ("DOWN", "GPIO_PIN_1", "GPIOA"),
        "PA4": ("LEFT", "GPIO_PIN_4", "GPIOA"),
        "PB0": ("RIGHT", "GPIO_PIN_0", "GPIOB"),
        "PB1": ("PAGE_NEXT", "GPIO_PIN_1", "GPIOB"),
        "PC0": ("PAGE_PREVIOUS", "GPIO_PIN_0", "GPIOC"),
        "PC1": ("CONFIRM", "GPIO_PIN_1", "GPIOC"),
        "PC2": ("MODE_LEVER", "GPIO_PIN_2", "GPIOC"),
    }
    for pin, (label, hal_pin, port) in expected.items():
        assert ioc[f"{pin}.GPIO_Label"] == label
        assert ioc[f"{pin}.GPIO_PuPd"] == "GPIO_PULLUP"
        assert ioc[f"{pin}.Signal"] == "GPIO_Input"
        assert f"#define {label}_Pin {hal_pin}" in main_h
        assert f"#define {label}_GPIO_Port {port}" in main_h

    assert not (firmware / "Debug").exists()
