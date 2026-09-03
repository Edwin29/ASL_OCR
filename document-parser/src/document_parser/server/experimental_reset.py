"""Recoverably reset one stopped E0-B experimental server state root."""

from __future__ import annotations

import argparse
import json
import shutil
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


CONFIRMATION_TOKEN = "RESET-E0B-EXPERIMENT"
_STATE_ENTRIES = (
    "server.sqlite3",
    "server.sqlite3-wal",
    "server.sqlite3-shm",
    "datapacks",
    "jobs",
)


class ExperimentalResetError(RuntimeError):
    pass


def reset_experimental_state(
    state_root: str | Path,
    *,
    confirmation: str,
    health_url: str | None = "http://127.0.0.1:8421/api/v1/health",
    health_probe: Callable[[str], bool] | None = None,
) -> dict[str, object]:
    root = _validated_state_root(state_root)
    if confirmation != CONFIRMATION_TOKEN:
        raise ExperimentalResetError(
            f"confirmation must be exactly {CONFIRMATION_TOKEN}"
        )
    probe = health_probe or _server_is_running
    if health_url and probe(health_url):
        raise ExperimentalResetError(
            f"server is still reachable at {health_url}; stop it before resetting state"
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_root = root.parent / f"{root.name}-reset-backups" / f"{stamp}-{uuid.uuid4().hex[:8]}"
    moved: list[str] = []
    for name in _STATE_ENTRIES:
        source = root / name
        if not source.exists():
            continue
        destination = backup_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        moved.append(name)

    (root / "datapacks").mkdir(parents=True, exist_ok=True)
    (root / "jobs").mkdir(parents=True, exist_ok=True)
    return {
        "status": "reset",
        "state_root": str(root),
        "backup_root": str(backup_root) if moved else None,
        "moved_entries": moved,
        "recreated_entries": ["datapacks", "jobs"],
        "recoverable": True,
    }


def _validated_state_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ExperimentalResetError(f"state root is not a directory: {root}")
    if root == Path(root.anchor) or root.parent == root:
        raise ExperimentalResetError("a drive/filesystem root cannot be reset")
    if root.name in {"", ".", ".."}:
        raise ExperimentalResetError("state root must have a concrete directory name")
    return root


def _server_is_running(url: str) -> bool:
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=1.0):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reset a stopped experimental E0-B Server state root by moving its DB, "
            "datapacks, and jobs to a recoverable sibling backup."
        )
    )
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--confirm", required=True)
    parser.add_argument(
        "--health-url",
        default="http://127.0.0.1:8421/api/v1/health",
        help="Local Server health URL; reset is refused while it responds.",
    )
    args = parser.parse_args(argv)
    try:
        result = reset_experimental_state(
            args.state_root,
            confirmation=args.confirm,
            health_url=args.health_url or None,
        )
    except ExperimentalResetError as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
