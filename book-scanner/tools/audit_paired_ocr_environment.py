"""Read-only audit for an existing GPU-capable PaddleOCR-VL environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


BOOK_SCANNER_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BOOK_SCANNER_ROOT.parent
DEFAULT_MODEL_HOME = WORKSPACE_ROOT / "document-parser" / "data" / "debug" / "model_home_vl"
DEFAULT_CHECKPOINT = WORKSPACE_ROOT / "tmp" / "uvdoc-runtime" / "model" / "best_model.pkl"


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], timeout: int = 20) -> dict[str, object]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {"returncode": None, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def _python_probe(executable: Path) -> dict[str, object]:
    probe = r'''
import importlib.metadata as metadata
import importlib.util
import json
import platform
import sys

payload = {
    "executable": sys.executable,
    "version": sys.version,
    "architecture": platform.architecture()[0],
    "paddle_installed": importlib.util.find_spec("paddle") is not None,
    "paddleocr_installed": importlib.util.find_spec("paddleocr") is not None,
}
for package in ("paddlepaddle", "paddlepaddle-gpu", "paddleocr", "torch"):
    try:
        payload[package + "_version"] = metadata.version(package)
    except metadata.PackageNotFoundError:
        payload[package + "_version"] = None
if payload["paddle_installed"]:
    try:
        import paddle
        payload["paddle_import_ok"] = True
        payload["cuda_compiled"] = bool(paddle.is_compiled_with_cuda())
        payload["cuda_device_count"] = int(paddle.device.cuda.device_count())
    except Exception as exc:
        payload["paddle_import_ok"] = False
        payload["paddle_import_error"] = type(exc).__name__ + ": " + str(exc)
print(json.dumps(payload, ensure_ascii=True))
'''
    result = _run([str(executable), "-c", probe])
    payload: dict[str, object] = {"requested_executable": str(executable), "probe": result}
    if result["returncode"] == 0:
        try:
            payload.update(json.loads(str(result["stdout"]).splitlines()[-1]))
        except (json.JSONDecodeError, IndexError) as exc:
            payload["parse_error"] = f"{type(exc).__name__}: {exc}"
    payload["gpu_ready"] = bool(
        payload.get("paddleocr_installed")
        and payload.get("paddle_import_ok")
        and payload.get("cuda_compiled")
        and int(payload.get("cuda_device_count") or 0) > 0
    )
    return payload


def classify_environment(
    gpu_present: bool,
    probes: list[dict[str, object]],
    model_assets: dict[str, bool],
) -> str:
    if not gpu_present:
        return "GPU_NOT_AVAILABLE"
    if not any(bool(probe.get("gpu_ready")) for probe in probes):
        return "GPU_PRESENT_ENV_MISSING"
    if not all(model_assets.values()):
        return "MODEL_ASSETS_INCOMPLETE"
    return "GPU_ENV_READY"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", action="append", type=Path, dest="pythons")
    parser.add_argument("--model-home", type=Path, default=DEFAULT_MODEL_HOME)
    parser.add_argument("--uvdoc-checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidates = args.pythons or [
        Path(sys.executable),
        Path(r"D:\venvs\gpu_ocr_test\Scripts\python.exe"),
        Path(r"D:\venvs\paddleocr-vl\Scripts\python.exe"),
        WORKSPACE_ROOT / "document-parser" / ".venv" / "Scripts" / "python.exe",
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        key = str(resolved).casefold()
        if key not in seen and resolved.is_file():
            seen.add(key)
            unique.append(resolved)

    nvidia_smi = shutil.which("nvidia-smi")
    gpu_query = _run([
        nvidia_smi,
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader,nounits",
    ]) if nvidia_smi else {"returncode": None, "stdout": "", "stderr": "nvidia-smi not found"}
    probes = [_python_probe(path) for path in unique]
    gpu_present = gpu_query.get("returncode") == 0 and bool(gpu_query.get("stdout"))
    official = args.model_home.resolve() / ".paddlex" / "official_models"
    required_models = ("PaddleOCR-VL-1.6", "PP-DocLayoutV3")
    model_assets = {name: (official / name).is_dir() for name in required_models}
    status = classify_environment(gpu_present, probes, model_assets)
    payload = {
        "schema_version": 1,
        "status": status,
        "read_only_audit": True,
        "install_or_download_attempted": False,
        "gpu": {"nvidia_smi_path": nvidia_smi, "query": gpu_query},
        "python_candidates": probes,
        "other_existing_runtimes": {
            "conda_on_path": shutil.which("conda"),
            "docker_on_path": shutil.which("docker"),
            "wsl_on_path": shutil.which("wsl"),
        },
        "model_home": str(args.model_home.resolve()),
        "model_assets": model_assets,
        "uvdoc_checkpoint": str(args.uvdoc_checkpoint.resolve()),
        "uvdoc_checkpoint_sha256": _sha256(args.uvdoc_checkpoint.resolve()),
        "next_action": (
            "GPU smoke may proceed with the ready candidate."
            if status == "GPU_ENV_READY"
            else "Stop before smoke/pilot; environment mutation requires separate approval."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if status == "GPU_ENV_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
