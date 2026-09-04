from __future__ import annotations

import queue
import threading
import time
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
        self.lines: queue.Queue[bytes] = queue.Queue()
        self.writes = []
        self._lock = threading.Lock()

    def readline(self):
        try:
            return self.lines.get(timeout=0.005)
        except queue.Empty:
            return b""

    def write(self, data):
        with self._lock:
            self.writes.append(data)
        return len(data)

    def close(self):
        pass


def _next_event(source: StmSerialControlSource):
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        events = source.poll()
        if events:
            return events[0]
        time.sleep(0.005)
    raise AssertionError("STM event was not delivered")


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

    try:
        source.present(coordinator.reading_snapshot)
        serial.lines.put(b"HELLO,2\n")
        sequence = 1
        for control, action in (
            ("V", "R"),
            ("C", "S"),
            ("D", "S"),
            ("C", "L"),
            ("C", "S"),
        ):
            serial.lines.put(f"NAV,{control},{action},{sequence}\n".encode("ascii"))
            coordinator.handle_input(_next_event(source))
            source.present(coordinator.reading_snapshot)
            sequence += 1

        assert coordinator.operating_mode is DeviceOperatingMode.READING
        assert coordinator.state is DeviceFlowState.READING
        assert scan.open_calls == []
        assert scanner.start_calls == []
        assert len(reading.open_calls) == 2
        assert len(reading.command_calls) == 1

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            with serial._lock:
                if any(line.startswith(b"FRAME,3,7,0,0,0,1,2,3") for line in serial.writes):
                    break
            time.sleep(0.005)
        else:
            raise AssertionError("final braille FRAME was not presented")
    finally:
        source.close()


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
    assert 'static const char hello_v2[] = "HELLO,2\\n"' in main_c
    assert 'strcmp(line, "ACK,HELLO,2") == 0' in main_c
    assert '"NAV,%c,%c,%lu\\n"' in main_c
    assert 'sscanf(line, "ACK,%lu%c"' in main_c
    assert "static void PumpBluetoothInput(void)" in main_c
    assert "static void ServiceControlTransmit(void)" in main_c
    assert "if (bt_protocol_v2)" in main_c
    assert "ReceiveFrameFromPi(FRAME_TIMEOUT_MS)" in main_c
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
