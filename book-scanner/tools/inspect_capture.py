"""Debug CLI: run measure_page + judge_capture on one image and show why.

Usage:
    python tools/inspect_capture.py path/to/photo.jpg
    python tools/inspect_capture.py path/to/photo.jpg --overlay out.jpg

--overlay writes a copy of the image with the detected rectangle drawn on
it (green = allowed, red = rejected) plus the verdict as a text label, so
you can eyeball whether the detector is even looking at the right region.
"""

from __future__ import annotations

import argparse
import sys

import cv2
import numpy as np

from book_scanner.capture.judge import judge_capture
from book_scanner.capture.measure import measure_page


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="path to the image to test")
    parser.add_argument("--overlay", help="optional path to write a debug overlay image")
    args = parser.parse_args()

    frame = cv2.imread(args.image)
    if frame is None:
        print(f"could not read image: {args.image}", file=sys.stderr)
        return 1

    geometry = measure_page(frame)
    verdict = judge_capture(geometry)

    print(f"image:      {args.image}")
    print(f"frame_size: {frame.shape[1]}x{frame.shape[0]}")
    if geometry is None:
        print("geometry:   NOT FOUND")
    else:
        print(f"angle_deg:  {geometry.angle_deg:.1f}")
        print(f"area_ratio: {geometry.area_ratio:.3f}")
        print(f"corners:    {geometry.corners}")
    print(f"allowed:    {verdict.allowed}")
    print(f"reason:     {verdict.reason.value if verdict.reason else None}")

    if args.overlay:
        overlay = frame.copy()
        color = (0, 200, 0) if verdict.allowed else (0, 0, 255)
        if geometry is not None:
            box = np.array(geometry.corners, dtype=np.int32)
            cv2.polylines(overlay, [box], isClosed=True, color=color, thickness=4)
        label = "ALLOWED" if verdict.allowed else f"REJECTED: {verdict.reason.value if verdict.reason else 'unknown'}"
        cv2.putText(overlay, label, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 6, cv2.LINE_AA)
        cv2.putText(overlay, label, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imwrite(args.overlay, overlay)
        print(f"overlay:    {args.overlay}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
