"""Dependency-free E0-B health probe used by the Windows batch wrappers."""

from __future__ import annotations

import json
import sys
import urllib.request


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: e0b_health_check.py <server-origin>", file=sys.stderr)
        return 2
    origin = argv[1].rstrip("/")
    url = f"{origin}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.load(response)
            status = response.status
    except Exception as exc:
        print(f"[E0-B] Health check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if status != 200 or not isinstance(payload, dict) or payload.get("status") != "ok":
        print("[E0-B] Health response is not HTTP 200 status=ok.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
