from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import serial


LOG = Path(
    r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration"
    r"\h3r-20260908-reading-output\logs\h3r-physical-down-com5.jsonl"
)


LOG.parent.mkdir(parents=True, exist_ok=True)
with serial.Serial("COM5", 115200, timeout=0.25) as port, LOG.open(
    "a", encoding="utf-8", buffering=1
) as output:
    while True:
        raw = port.readline()
        if not raw:
            continue
        record = {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "text": raw.decode("utf-8", errors="replace").rstrip("\r\n"),
            "raw_hex": raw.hex(),
        }
        output.write(json.dumps(record, ensure_ascii=False) + "\n")
