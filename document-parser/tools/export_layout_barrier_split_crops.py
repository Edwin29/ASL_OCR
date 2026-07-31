from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.structure import export_barrier_split_work_units


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export split work-unit crops for TEXT nodes crossing layout barriers.")
    parser.add_argument("--page-ir", type=Path, required=True)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--padding", type=int, default=8)
    parser.add_argument("--page-id", action="append", help="Limit export to one or more page IDs.")
    args = parser.parse_args(argv)

    payload = json.loads(args.page_ir.read_text(encoding="utf-8"))
    page_ids = set(args.page_id) if args.page_id else None
    manifest = export_barrier_split_work_units(
        payload,
        images_dir=args.images_dir,
        output_dir=args.output_dir,
        padding=args.padding,
        page_ids=page_ids,
    )
    manifest["page_ir"] = str(args.page_ir.resolve())
    manifest["images_dir"] = str(args.images_dir.resolve())
    manifest["output_dir"] = str(args.output_dir.resolve())
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {manifest['work_unit_count']} split work-unit crops to {args.output_dir.resolve()}")
    print(f"Manifest: {args.manifest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
