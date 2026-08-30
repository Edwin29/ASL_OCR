"""Run UVDoc against human-labeled oracle left/right page crops."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from book_scanner.correct.uvdoc_adapter import UVDocAdapter, UVDocConfig
from book_scanner.evaluation.unwarp_experiment import run_oracle_unwarp_experiment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--label", type=Path, required=True)
    parser.add_argument("--uvdoc-runtime", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--padding-fraction", type=float, default=0.03)
    parser.add_argument("--neutral-value", type=int, default=255)
    args = parser.parse_args()

    adapter = UVDocAdapter(
        UVDocConfig(
            runtime_path=args.uvdoc_runtime,
            checkpoint_path=args.checkpoint,
            device=args.device,
        )
    )
    summary = run_oracle_unwarp_experiment(
        args.image,
        args.label,
        args.output_dir,
        adapter,
        padding_fraction=args.padding_fraction,
        neutral_value=args.neutral_value,
        runtime_path=args.uvdoc_runtime,
        checkpoint_path=args.checkpoint,
    )
    compact = {
        side: {
            variant: {
                "success": payload["success"],
                "reason": payload["reason"],
                "processing_ms": payload["processing_ms"],
            }
            for variant, payload in side_payload["variants"].items()
        }
        for side, side_payload in summary["sides"].items()
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0 if all(
        result["success"]
        for side_payload in summary["sides"].values()
        for result in side_payload["variants"].values()
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
