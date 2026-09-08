from __future__ import annotations
import json,sys
from pathlib import Path
from asl_device.adapters.local_controls import ConsoleControlSource
from asl_device.adapters.local_feedback import CompositeFeedbackSink,JsonLineFeedbackSink,JsonLineReadingPresenter
from asl_device.adapters.stm_serial import StmSerialControlSource
from asl_device.app_config import DeviceAppConfig
from asl_device.local_composition import build_local_device
from asl_device.types import DeviceOperatingMode

ROOT=Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3r-20260908-reading-output")
CONFIG=ROOT/"config"/"device-app.h3r-braille-only.toml"
LOG=ROOT/"logs"/"h3r-braille-events.jsonl"
log=LOG.open("a",encoding="utf-8",buffering=1)
class MultiPresenter:
    def __init__(self,*items): self.items=items
    def present(self,snapshot):
        for item in self.items: item.present(snapshot)
    def close(self):
        for item in reversed(self.items):
            try: item.close()
            except Exception: pass
cfg=DeviceAppConfig.from_toml(CONFIG)
assert cfg.stm_serial is not None and cfg.stm_serial.port=="COM9" and cfg.stm_serial.cell_count==10
namespace="h3r-20260908-reading-output"
controls=ConsoleControlSource(event_namespace=namespace)
stm=StmSerialControlSource(cfg.stm_serial,event_namespace=namespace)
feedback=CompositeFeedbackSink(JsonLineFeedbackSink(sys.stdout),JsonLineFeedbackSink(log))
presenter=MultiPresenter(JsonLineReadingPresenter(sys.stdout),JsonLineReadingPresenter(log),stm)
print(json.dumps({"type":"h3r_braille_start","run_root":str(ROOT),"controls":"console","presenter":"stm_serial","stm_port":"COM9","initial_mode":"reading","physical_stm_nav_applied":False,"product_source_modified":False}),flush=True)
composition=build_local_device(CONFIG,controls=controls,presenter=presenter,feedback=feedback,initial_mode=DeviceOperatingMode.READING)
try: composition.application.run()
except KeyboardInterrupt: composition.application.stop()
finally:
    print(json.dumps({"type":"h3r_braille_stop","presentation_failures":composition.application.presentation_failures}),flush=True)
    log.close()

