from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

root = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447")
state = root / "state" / "camera-console"

files = []
for path in sorted(state.rglob("*")):
    if not path.is_file():
        continue
    row = {
        "relative": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
    }
    if path.suffix.lower() in {".json", ".jpeg", ".jpg", ".png"}:
        row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    files.append(row)

database = state / "delivery.sqlite3"
tables = {}
if database.exists():
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        names = [
            item[0]
            for item in connection.execute(
                "select name from sqlite_master where type='table' order by name"
            )
        ]
        for name in names:
            columns = [item[1] for item in connection.execute(f'pragma table_info("{name}")')]
            rows = connection.execute(f'select * from "{name}"').fetchall()
            tables[name] = {"columns": columns, "rows": rows}
    finally:
        connection.close()

result = {
    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    "files": files,
    "sqlite": tables,
}
print(json.dumps(result, indent=2, default=str))
