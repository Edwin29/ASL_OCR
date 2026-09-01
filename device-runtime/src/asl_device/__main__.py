"""Command-line entrypoint for the E0-Core local Device host."""

from __future__ import annotations

import argparse
import json

from .laptop_acceptance import run_laptop_preflight, write_laptop_preflight_report
from .local_composition import build_local_device


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the ASL OCR E0-Core local Device host")
    parser.add_argument("--config", required=True, help="Path to the E0 Device application TOML")
    parser.add_argument("--preflight", action="store_true", help="Run E0-B Laptop hardware checks and exit")
    parser.add_argument("--report", help="Write the E0-B preflight JSON report to this path")
    args = parser.parse_args()
    if args.preflight:
        report = run_laptop_preflight(args.config)
        if args.report:
            write_laptop_preflight_report(report, args.report)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["passed"] else 2
    composition = build_local_device(args.config)
    try:
        composition.application.run()
    except KeyboardInterrupt:
        composition.application.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
