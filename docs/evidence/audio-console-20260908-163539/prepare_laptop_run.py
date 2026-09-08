from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

source_root = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447")
run_root = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\audio-console-20260908-163539")

if run_root.exists():
    raise SystemExit("run root already exists; refusing to overwrite preserved evidence")

run_root.mkdir(parents=True)
shutil.copytree(source_root / "config", run_root / "config")
for name in ("state", "evidence", "logs", "launcher"):
    (run_root / name).mkdir()

device_config = run_root / "config" / "device-app.h1-camera-console.toml"
text = device_config.read_text(encoding="utf-8")
old_posix = source_root.as_posix()
new_posix = run_root.as_posix()
if old_posix not in text:
    raise SystemExit("expected source run root was not present in copied config")
device_config.write_text(text.replace(old_posix, new_posix), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


manifest = {
    "schema_version": 1,
    "run_id": run_root.name,
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "source_root": r"C:\ASL_OCR_INTEGRATION",
    "python": r"C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe",
    "launcher": "bounded custom composition",
    "initial_mode": "reading",
    "config": str(device_config),
    "config_sha256": sha256(device_config),
    "connectivity_config_sha256": sha256(run_root / "config" / "device-connectivity.integration.toml"),
    "runtime_overrides": [
        "ConsoleControlSource",
        "JsonLineReadingPresenter",
        "initial_mode=READING",
    ],
    "production_classes_preserved": [
        "DeviceApplication",
        "DeviceFlowCoordinator",
        "S0ReadingHttpAdapter",
        "S0AudioResourceHttpAdapter",
        "S0SystemAudioResourceHttpAdapter",
        "ReadingAudioController",
        "SoundDeviceWavPlayer",
    ],
    "boundaries_bypassed": [
        "live capture",
        "V4 upload",
        "S1 finalize",
        "physical controls",
        "STM presenter",
        "PCA and servo cells",
    ],
    "state_isolated": True,
    "existing_state_modified": False,
    "credential_files_copied": 2,
    "credential_values_recorded": False,
}
(run_root / "run-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest, indent=2))
