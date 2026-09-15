"""Boot orchestration only; unchanged production entrypoint and durable state."""
import hashlib, json, os, socket, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from asl_device.app_config import DeviceAppConfig

root = Path('/home/user/ASL_OCR_PI')
config = root / 'config/device-app.stm-capture-round2-20260915.toml'
cfg = DeviceAppConfig.from_toml(config)
run = root / 'runtime/boot-20260916' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + str(os.getpid()))
run.mkdir(parents=True, exist_ok=False)
log = os.open(run / 'stdout.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.dup2(log, 1)
os.dup2(log, 2)
os.close(log)
command = [sys.executable, '-u', '-m', 'asl_device', '--config', str(config), '--initial-mode', 'capture']
(run / 'manifest.json').write_text(json.dumps(dict(
    command=command, pid=os.getpid(), boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
    state_preserved=True, readiness='RFCOMM node and server TCP only; V3/API/audio require runtime evidence'
), indent=2))
url = urlsplit(cfg.connectivity.server_base_url)
deadline = time.monotonic() + 90
while time.monotonic() < deadline:
    try:
        if not Path('/dev/rfcomm0').exists():
            raise OSError('RFCOMM node unavailable')
        with socket.create_connection((url.hostname, url.port or (443 if url.scheme == 'https' else 80)), timeout=3):
            pass
        break
    except OSError:
        time.sleep(2)
else:
    print('BOOT_PREFLIGHT_TIMEOUT: RFCOMM node or server TCP unavailable', flush=True)
    sys.exit(75)
print('BOOT_EXEC_PRODUCTION', flush=True)
os.chdir(root / 'source')
os.execv(sys.executable, command)
