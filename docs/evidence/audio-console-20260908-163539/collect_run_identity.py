from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import subprocess

OUT = pathlib.Path(__file__).resolve().parent
REPO = OUT.parents[2]


def source_hashes(root: pathlib.Path) -> dict[str, dict[str, str]]:
    files = []
    for sub in (
        "device-runtime/src",
        "book-scanner/src",
        "document-parser/src",
        "hardware/stm32/kitel2026final/Core",
    ):
        files.extend(
            path for path in (root / sub).rglob("*") if path.suffix in {".py", ".c", ".h"}
        )
    return {
        path.relative_to(root).as_posix(): {
            "raw": hashlib.sha256(path.read_bytes()).hexdigest(),
            "lf": hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        }
        for path in sorted(files)
    }


remote_code = r'''
import hashlib,json,pathlib,sys
import asl_device,book_scanner,document_parser

def source_hashes(root):
    files=[]
    for sub in ("device-runtime/src","book-scanner/src","document-parser/src","hardware/stm32/kitel2026final/Core"):
        files.extend(path for path in (root/sub).rglob("*") if path.suffix in {".py",".c",".h"})
    return {path.relative_to(root).as_posix():{"raw":hashlib.sha256(path.read_bytes()).hexdigest(),"lf":hashlib.sha256(path.read_bytes().replace(b"\r\n",b"\n")).hexdigest()} for path in sorted(files)}

root=pathlib.Path(r"C:\ASL_OCR_INTEGRATION")
print(json.dumps({
    "python":sys.executable,
    "python_version":sys.version.split()[0],
    "imports":{"asl_device":asl_device.__file__,"book_scanner":book_scanner.__file__,"document_parser":document_parser.__file__},
    "hashes":source_hashes(root),
}))
'''
ps = "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\ASL_OCR_INTEGRATION\\.venv-e0b\\Scripts\\python.exe' -B -c \"import sys;exec(sys.stdin.read())\""
encoded = base64.b64encode(ps.encode("utf-16le")).decode()
proc = subprocess.run(
    ["ssh", "-o", "BatchMode=yes", "user@100.106.45.8", "powershell", "-NoProfile", "-EncodedCommand", encoded],
    input=remote_code.encode("utf-8"),
    capture_output=True,
    timeout=55,
    check=True,
)
laptop = json.loads(proc.stdout.decode("utf-8-sig"))
desktop = source_hashes(REPO)
mismatches = [
    path for path, value in desktop.items()
    if laptop["hashes"].get(path, {}).get("lf") != value["lf"]
]
result = {
    "schema_version": 1,
    "desktop_file_count": len(desktop),
    "laptop_file_count": len(laptop["hashes"]),
    "mismatches": mismatches,
    "python": laptop["python"],
    "python_version": laptop["python_version"],
    "imports": laptop["imports"],
}
(OUT / "source-identity-before.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
