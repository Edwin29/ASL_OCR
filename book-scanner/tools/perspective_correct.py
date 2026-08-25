"""CLI wrapper over book_scanner.correct.pipeline.correct_and_save (roadmap
Stage 6: "페이지 보정 및 스캔 산출물 생성").

Corner selection is manual for now (not measure.py's auto-detection, which
has known reliability issues on real photos -- see prior findings in this
project's README/memory). Writes both the corrected image and a metadata
JSON (original/corrected sha256, corners, output size, timestamp) into
--out-dir, via atomic temp-file-then-rename so a crash mid-write can never
leave a half-written file mistaken for a real output. The original file is
never modified.

Usage:
    python tools/perspective_correct.py photo.jpg \\
        --tl 150,58 --tr 2088,143 --br 2085,2685 --bl 67,2650 \\
        --out-dir corrected --capture-id p030_photo
"""

from __future__ import annotations

import argparse
from pathlib import Path

from book_scanner.correct.pipeline import correct_and_save
from book_scanner.correct.types import Corners


def _point(text: str) -> tuple[float, float]:
    x_str, y_str = text.split(",")
    return (float(x_str), float(y_str))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", help="path to the source photo")
    parser.add_argument("--tl", type=_point, required=True, help="top-left corner, 'x,y'")
    parser.add_argument("--tr", type=_point, required=True, help="top-right corner, 'x,y'")
    parser.add_argument("--br", type=_point, required=True, help="bottom-right corner, 'x,y'")
    parser.add_argument("--bl", type=_point, required=True, help="bottom-left corner, 'x,y'")
    parser.add_argument("--out-dir", required=True, help="directory to write the corrected image + metadata into")
    parser.add_argument("--capture-id", default=None, help="defaults to an auto-generated unique id")
    args = parser.parse_args()

    corners = Corners(top_left=args.tl, top_right=args.tr, bottom_right=args.br, bottom_left=args.bl)
    metadata = correct_and_save(Path(args.image), corners, Path(args.out_dir), capture_id=args.capture_id)

    print(f"capture_id:     {metadata.capture_id}")
    print(f"corrected_path: {metadata.corrected_path}")
    print(f"output_size:    {metadata.output_size[0]}x{metadata.output_size[1]}")
    print(f"original_sha256:  {metadata.original_sha256}")
    print(f"corrected_sha256: {metadata.corrected_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
