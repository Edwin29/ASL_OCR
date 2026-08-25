"""The repeated-capture session loop: capture -> segment -> judge geometry
+ stability -> (once stable) correct + judge quality -> transmit, or guide
the user and keep trying. Implemented as a generator so "button cancel" is
just the caller stopping iteration -- no separate cancel API needed.

First `capture_source.read()` call is treated as the empty reference frame
(function 4/5's button-enters-loop semantics: entering the loop starts with
an empty capture area). Each subsequent frame is split at the configured
spine centerline into independent left/right subframes (see detect/spread.py
for why an exact ribbon/curve shape isn't modeled); LEFT is judged and
transmitted first, then RIGHT, then the whole cycle auto-resumes for the
next page spread -- confirmed behavior, not an assumption.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator

import cv2

from book_scanner.correct.pipeline import correct_and_save
from book_scanner.correct.types import Corners
from book_scanner.detect.background import BackgroundRef, foreground_mask, register_background
from book_scanner.detect.corners import geometry_from_mask, order_corners
from book_scanner.detect.spread import SpreadConfig, split_spread
from book_scanner.detect.types import PageGeometry
from book_scanner.judge.geometry_judge import DEFAULT_THRESHOLDS as DEFAULT_GEOMETRY_THRESHOLDS
from book_scanner.judge.geometry_judge import GeometryThresholds, judge_geometry
from book_scanner.judge.stability_judge import DEFAULT_THRESHOLDS as DEFAULT_STABILITY_THRESHOLDS
from book_scanner.judge.stability_judge import StabilityThresholds, judge_stability
from book_scanner.judge.transmit_judge import judge_final
from book_scanner.judge.types import TransmitBlockReason


class Side(Enum):
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class GuidanceEvent:
    side: Side
    reason: TransmitBlockReason


@dataclass(frozen=True)
class PageTransmittedEvent:
    side: Side
    corrected_path: Path


@dataclass(frozen=True)
class SpreadCompleteEvent:
    pass


LoopEvent = GuidanceEvent | PageTransmittedEvent | SpreadCompleteEvent


def run_session(
    capture_source,
    output_dir: Path,
    transmit_fn: Callable[[Path], None],
    spread_config: SpreadConfig = SpreadConfig(),
    geometry_thresholds: GeometryThresholds = DEFAULT_GEOMETRY_THRESHOLDS,
    stability_thresholds: StabilityThresholds = DEFAULT_STABILITY_THRESHOLDS,
) -> Iterator[LoopEvent]:
    output_dir = Path(output_dir)

    first_frame = capture_source.read()
    if first_frame is None:
        return

    left_bg_frame, right_bg_frame = split_spread(first_frame, spread_config)
    backgrounds: dict[Side, BackgroundRef] = {
        Side.LEFT: register_background(left_bg_frame),
        Side.RIGHT: register_background(right_bg_frame),
    }
    history: dict[Side, list[PageGeometry]] = {Side.LEFT: [], Side.RIGHT: []}
    current_side = Side.LEFT

    while True:
        frame = capture_source.read()
        if frame is None:
            return

        left_frame, right_frame = split_spread(frame, spread_config)
        subframe = left_frame if current_side is Side.LEFT else right_frame

        mask = foreground_mask(subframe, backgrounds[current_side])
        geometry = geometry_from_mask(mask)

        reason = judge_geometry(geometry, geometry_thresholds)
        if reason is not None:
            history[current_side].clear()
            yield GuidanceEvent(current_side, reason)
            continue

        history[current_side].append(geometry)
        reason = judge_stability(history[current_side], stability_thresholds)
        if reason is not None:
            yield GuidanceEvent(current_side, reason)
            continue

        capture_id = f"{current_side.value}_{uuid.uuid4().hex[:8]}"
        raw_path = output_dir / f"{capture_id}_raw.png"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(raw_path), subframe)

        top_left, top_right, bottom_right, bottom_left = order_corners(geometry.corners)
        corners = Corners(top_left=top_left, top_right=top_right, bottom_right=bottom_right, bottom_left=bottom_left)
        metadata = correct_and_save(raw_path, corners, output_dir, capture_id=capture_id)

        quality_verdict = judge_final(Path(metadata.corrected_path))
        if not quality_verdict.transmittable:
            yield GuidanceEvent(current_side, quality_verdict.reason)
            continue

        transmit_fn(Path(metadata.corrected_path))
        yield PageTransmittedEvent(current_side, Path(metadata.corrected_path))
        history[current_side].clear()

        if current_side is Side.LEFT:
            current_side = Side.RIGHT
        else:
            current_side = Side.LEFT
            yield SpreadCompleteEvent()
