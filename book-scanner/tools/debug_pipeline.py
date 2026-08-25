"""Debug CLI: dump every intermediate step of measure_page's detection
pipeline as images, so a detection failure can be diagnosed from screenshots
alone (useful when the actual test photo isn't available locally).

Usage:
    python tools/debug_pipeline.py path/to/photo.jpg --out-dir debug_steps

Writes, into --out-dir:
    01_working_gray.jpg    -- grayscale, downscaled to measure_page's working
                               resolution (this is what detection actually sees)
    02_canny_edges.jpg      -- raw Canny edge map
    03_dilated_edges.jpg    -- edge map after the dilate step (what
                               findContours actually runs on)
    04_all_contours.jpg     -- every contour found, in a distinct color, with
                               the largest one outlined thick in red and
                               labeled with its area ratio
Also prints the top 5 contours by area (as a fraction of the working frame)
and whether each touches the frame boundary.
"""

from __future__ import annotations

import argparse
import os
import sys

import cv2
import numpy as np

import book_scanner.capture.measure as measure_mod


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="path to the image to test")
    parser.add_argument("--out-dir", default="debug_steps", help="directory to write step images into")
    args = parser.parse_args()

    frame = cv2.imread(args.image)
    if frame is None:
        print(f"could not read image: {args.image}", file=sys.stderr)
        return 1

    os.makedirs(args.out_dir, exist_ok=True)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    frame_h, frame_w = gray.shape[:2]

    scale = min(1.0, measure_mod._WORKING_MAX_DIM / max(frame_w, frame_h))
    working = (
        cv2.resize(gray, (int(round(frame_w * scale)), int(round(frame_h * scale))), interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else gray
    )
    working_h, working_w = working.shape[:2]
    working_area = float(working_w * working_h)

    blurred = cv2.GaussianBlur(working, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    dilated = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    cv2.imwrite(os.path.join(args.out_dir, "01_working_gray.jpg"), working)
    cv2.imwrite(os.path.join(args.out_dir, "02_canny_edges.jpg"), edges)
    cv2.imwrite(os.path.join(args.out_dir, "03_dilated_edges.jpg"), dilated)

    overlay = cv2.cvtColor(working, cv2.COLOR_GRAY2BGR)
    ranked = sorted(contours, key=cv2.contourArea, reverse=True)

    print(f"image:         {args.image}")
    print(f"frame_size:    {frame_w}x{frame_h}  (working: {working_w}x{working_h}, scale={scale:.3f})")
    print(f"contour count: {len(contours)}")
    print("top contours by area:")
    for i, c in enumerate(ranked[:5]):
        area_ratio = cv2.contourArea(c) / working_area
        touches = bool(
            (c[:, 0, 0] <= 2).any()
            or (c[:, 0, 1] <= 2).any()
            or (c[:, 0, 0] >= working_w - 3).any()
            or (c[:, 0, 1] >= working_h - 3).any()
        )
        color = (0, 255, 0) if i > 0 else (0, 0, 255)
        thickness = 2 if i > 0 else 4
        cv2.drawContours(overlay, [c], -1, color, thickness)
        print(f"  #{i}: area_ratio={area_ratio:.3f} touches_edge={touches}")

    cv2.imwrite(os.path.join(args.out_dir, "04_all_contours.jpg"), overlay)
    print(f"wrote step images to {args.out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
