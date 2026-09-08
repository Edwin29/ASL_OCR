from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from asl_device.adapters.local_feedback import (
    CompositeFeedbackSink,
    JsonLineFeedbackSink,
    JsonLineReadingPresenter,
)
from asl_device.adapters.stm_serial import StmSerialControlSource
from asl_device.app_config import DeviceAppConfig
from asl_device.local_composition import build_local_device
from asl_device.types import (
    DeviceControl,
    DeviceInputEvent,
    DeviceOperatingMode,
    InputAction,
)


ROOT = Path(
    r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration"
    r"\h3r-20260908-reading-output"
)
CONFIG = ROOT / "config" / "device-app.h3r-braille-only.toml"
LOG = ROOT / "logs" / "h3r-physical-down-events.jsonl"


class BootstrapThenStmControls:
    def __init__(self, stm: StmSerialControlSource) -> None:
        self.stm = stm
        sequence = [
            DeviceControl.CONFIRM,
            DeviceControl.PAGE_PREVIOUS,
            DeviceControl.PAGE_PREVIOUS,
            *([DeviceControl.DOWN] * 15),
        ]
        self.pending = [
            DeviceInputEvent(
                f"h3r-bootstrap-{index:04d}",
                control,
                InputAction.SHORT,
                time.monotonic(),
            )
            for index, control in enumerate(sequence, start=1)
        ]
        self.bootstrap_complete = False

    def poll(self) -> tuple[DeviceInputEvent, ...]:
        physical = self.stm.poll()
        if self.pending:
            event = self.pending.pop(0)
            if not self.pending:
                self.bootstrap_complete = True
            return (event,)
        return physical

    def close(self) -> None:
        self.stm.close()


class BootstrapGatedPresenter:
    def __init__(
        self,
        controls: BootstrapThenStmControls,
        stm: StmSerialControlSource,
        *logs: JsonLineReadingPresenter,
    ) -> None:
        self.controls = controls
        self.stm = stm
        self.logs = logs
        self.ready_emitted = False

    def present(self, snapshot) -> None:
        for logger in self.logs:
            logger.present(snapshot)
        if not self.controls.bootstrap_complete:
            return
        self.stm.present(snapshot)
        if snapshot is not None and not self.ready_emitted:
            cursor = dict(snapshot.cursor)
            print(
                json.dumps(
                    {
                        "type": "h3r_physical_down_ready",
                        "page_index": cursor.get("page_index"),
                        "node_index": cursor.get("node_index"),
                        "generation": cursor.get("generation"),
                        "focus_item_id": cursor.get("focus_item_id"),
                        "braille_cells": list(snapshot.braille_cells),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            self.ready_emitted = True

    def close(self) -> None:
        for logger in reversed(self.logs):
            logger.close()
        self.stm.close()


log_stream = LOG.open("a", encoding="utf-8", buffering=1)
config = DeviceAppConfig.from_toml(CONFIG)
assert not config.reading_audio.enabled
assert config.stm_serial is not None
assert config.stm_serial.port == "COM9"
assert config.stm_serial.cell_count == 10

stm = StmSerialControlSource(
    config.stm_serial,
    event_namespace="h3r-physical-down",
)
controls = BootstrapThenStmControls(stm)
feedback = CompositeFeedbackSink(
    JsonLineFeedbackSink(sys.stdout),
    JsonLineFeedbackSink(log_stream),
)
presenter = BootstrapGatedPresenter(
    controls,
    stm,
    JsonLineReadingPresenter(sys.stdout),
    JsonLineReadingPresenter(log_stream),
)

print(
    json.dumps(
        {
            "type": "h3r_physical_down_start",
            "controls": "bootstrap_then_physical_stm",
            "presenter": "stm_serial",
            "audio_enabled": False,
            "target_before_press": {
                "page_index": 0,
                "node_index": 15,
            },
            "expected_after_physical_down": {
                "page_index": 0,
                "node_index": 16,
                "focus_item_id": "pg-c4b5938b7318-00000001-L-vl012-L01",
                "braille_cells": [11, 38, 45, 52, 18, 18, 54, 55, 60, 1],
            },
            "product_source_modified": False,
        },
        ensure_ascii=False,
    ),
    flush=True,
)

composition = build_local_device(
    CONFIG,
    controls=controls,
    presenter=presenter,
    feedback=feedback,
    initial_mode=DeviceOperatingMode.READING,
)
try:
    composition.application.run()
except KeyboardInterrupt:
    composition.application.stop()
finally:
    print(
        json.dumps(
            {
                "type": "h3r_physical_down_stop",
                "presentation_failures": composition.application.presentation_failures,
            }
        ),
        flush=True,
    )
    log_stream.close()
