"""Read-only, credential-safe Desktop production server inventory."""
import hashlib
import json
import pathlib
import sqlite3
import subprocess
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STATE = pathlib.Path(r"D:\device-config\state\e0b-production")
DB_PATH = STATE / "server.sqlite3"
LAUNCHER = ROOT / r"tools\windows\e0b-start-production-server.bat"
SERVER_MODULE = ROOT / r"document-parser\src\document_parser\server\combined_server.py"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


process_json = subprocess.check_output(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in 5456,26900,13620 } | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Compress"],
    text=True, encoding="utf-8-sig",
)
processes = json.loads(process_json)
if isinstance(processes, dict):
    processes = [processes]
safe_processes = []
for row in processes:
    command = row.pop("CommandLine", "") or ""
    safe_processes.append({
        "process_id": row.get("ProcessId"),
        "parent_process_id": row.get("ParentProcessId"),
        "name": row.get("Name"),
        "executable": row.get("ExecutablePath"),
        "combined_server_entrypoint": "document_parser.server.combined_server" in command,
        "launcher_entrypoint": "e0b-start-production-server.bat" in command,
    })

with urllib.request.urlopen("http://127.0.0.1:8421/api/v1/health", timeout=5) as response:
    local_health = json.loads(response.read())
with urllib.request.urlopen("https://desktop-ekp6an5.taild2128f.ts.net/api/v1/health", timeout=10) as response:
    external_health = json.loads(response.read())

db = sqlite3.connect(DB_PATH.as_uri() + "?mode=ro", uri=True)
db.row_factory = sqlite3.Row
ready = [dict(row) for row in db.execute(
    "select datapack_id,status,current_revision,created_by_device_id,updated_at from datapacks where status='ready' order by updated_at desc"
)]
progress = []
for row in db.execute(
    "select device_id,datapack_id,revision_seen,cursor_json,cursor_version,updated_at from reading_progress where device_id=? order by updated_at desc",
    ("laptop-device-001",),
):
    item = dict(row)
    item["cursor"] = json.loads(item.pop("cursor_json"))
    progress.append(item)
open_sessions = [dict(row) for row in db.execute(
    "select reading_session_id,device_id,datapack_id,revision,status,created_at,last_seen_at from reading_sessions where device_id=? and status!='closed' order by last_seen_at desc",
    ("laptop-device-001",),
)]
presence = [dict(row) for row in db.execute(
    "select presence_session_id,boot_id,status,last_heartbeat_sequence,started_at,last_seen_at,disconnected_at from device_presence_sessions where device_id=? order by last_seen_at desc limit 5",
    ("laptop-device-001",),
)]
db.close()

models = json.loads((HERE.parent / "h123-followup-20260908" / "g3a-evidence" / "e0b-production-model-manifest.json").read_text(encoding="utf-8"))
result = {
    "processes": safe_processes,
    "listener": {"host": "127.0.0.1", "port": 8421, "owning_process_id": 26900},
    "launcher": {"path": str(LAUNCHER), "sha256": sha(LAUNCHER)},
    "source": {
        "root_from_launcher_contract": str(ROOT / "document-parser" / "src"),
        "combined_server_path": str(SERVER_MODULE),
        "combined_server_sha256": sha(SERVER_MODULE),
        "runtime_module_file_directly_observed": False,
        "basis": "current process was launched by the checked launcher, which sets PYTHONPATH to this source root",
    },
    "health": {
        "local": local_health,
        "tailscale_https": external_health,
        "same_server_instance": local_health.get("server_instance_id") == external_health.get("server_instance_id"),
        "tailscale_proxy": {"public_origin": "https://desktop-ekp6an5.taild2128f.ts.net", "target": "http://127.0.0.1:8421"},
    },
    "models": models,
    "state": {
        "database_path": str(DB_PATH),
        "database_sha256_at_capture": sha(DB_PATH),
        "database_bytes": DB_PATH.stat().st_size,
        "ready_datapacks": ready,
        "stable_device_progress": progress,
        "open_reading_sessions": open_sessions,
        "recent_presence_rows": presence,
        "note": "Open/active rows are preserved state, not proof that a Laptop process is currently alive.",
    },
    "credentials_recorded": False,
}
(HERE / "desktop-runtime.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({
    "server_instance_id": local_health.get("server_instance_id"),
    "same_external_server": result["health"]["same_server_instance"],
    "ready_datapacks": len(ready),
    "stable_progress_rows": len(progress),
    "open_reading_sessions": len(open_sessions),
    "active_presence_rows": sum(row["status"] == "active" for row in presence),
}, indent=2))
