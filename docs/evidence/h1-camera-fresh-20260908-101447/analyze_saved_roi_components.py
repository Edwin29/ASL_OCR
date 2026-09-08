from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2

repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo / "book-scanner" / "src"))
from book_scanner.video.page_number_recognizer import _candidate_clusters, _candidate_regions
from book_scanner.video.types import PageSide

root = Path(__file__).resolve().parent / "footer-30s-comparison-01"
rows = []
for phase in ("reference", "query"):
    for side in (PageSide.LEFT, PageSide.RIGHT):
        path = root / f"{phase}-{side.value}-footer-roi.png"
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise SystemExit(f"cannot read {path}")
        _binary, clusters = _candidate_clusters(image, side, 4)
        scaled = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        scaled_three = cv2.resize(image, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        scaled_four = cv2.resize(image, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
        rows.append(
            {
                "phase": phase,
                "side": side.value,
                "shape": list(image.shape),
                "candidate_regions": [list(item) for item in _candidate_regions(image, side, 4)],
                "candidate_clusters": [[list(box) for box in cluster] for cluster in clusters],
                "two_x_shape": list(scaled.shape),
                "two_x_candidate_regions": [list(item) for item in _candidate_regions(scaled, side, 4)],
                "three_x_candidate_regions": [list(item) for item in _candidate_regions(scaled_three, side, 4)],
                "four_x_candidate_regions": [list(item) for item in _candidate_regions(scaled_four, side, 4)],
            }
        )
result = {
    "kind": "saved_footer_roi_candidate_region_replay",
    "source_function": "book_scanner.video.page_number_recognizer._candidate_regions",
    "rows": rows,
}
output = Path(__file__).with_name("footer-roi-component-replay.json")
output.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
