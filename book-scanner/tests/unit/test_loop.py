"""Orchestration test for session/loop.py's state machine. Geometry and
stability axes run for real (cheap, small synthetic frames); the quality
axis is monkeypatched to always pass -- it's already covered in isolation
by test_quality_judge.py / test_transmit_judge.py, and exercising the real
document-parser ImageQualityGate here would just force every test frame to
be full document-quality resolution for no orchestration-relevant reason.
"""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

import book_scanner.session.loop as loop_module
from book_scanner.judge.types import TransmitBlockReason, TransmitVerdict
from book_scanner.session.loop import GuidanceEvent, PageTransmittedEvent, Side, SpreadCompleteEvent, run_session

FRAME_W, FRAME_H = 400, 300  # full frame; each half is 200x300


@contextmanager
def _tmp_dir():
    with tempfile.TemporaryDirectory(prefix="book_scanner_loop_test_") as d:
        yield Path(d)


def _background_frame() -> np.ndarray:
    return np.full((FRAME_H, FRAME_W, 3), 100, dtype=np.uint8)


def _frame_with_book(side: Side) -> np.ndarray:
    frame = _background_frame()
    # a well-margined rectangle inside whichever half is "active"
    x_offset = 0 if side is Side.LEFT else FRAME_W // 2
    frame[40:260, x_offset + 30 : x_offset + 170] = 255
    return frame


class ListCaptureSource:
    def __init__(self, frames: list[np.ndarray]):
        self._frames = frames
        self._index = 0

    def read(self):
        if self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame


def _always_transmittable(_path):
    return TransmitVerdict(transmittable=True, reason=None)


def test_full_spread_cycle(monkeypatch):
    monkeypatch.setattr(loop_module, "judge_final", _always_transmittable)

    frames = (
        [_background_frame()]  # registered as background
        + [_background_frame()]  # LEFT: no book yet -> PAGE_NOT_FOUND
        + [_frame_with_book(Side.LEFT)] * 5  # LEFT: settles after min_frames=5
        + [_frame_with_book(Side.RIGHT)] * 5  # RIGHT: settles after min_frames=5
    )

    with _tmp_dir() as output_dir:
        transmitted: list[Path] = []
        events = list(
            run_session(
                ListCaptureSource(frames),
                output_dir,
                transmit_fn=transmitted.append,
            )
        )

    guidance = [e for e in events if isinstance(e, GuidanceEvent)]
    transmits = [e for e in events if isinstance(e, PageTransmittedEvent)]
    completes = [e for e in events if isinstance(e, SpreadCompleteEvent)]

    assert guidance[0].side is Side.LEFT
    assert guidance[0].reason is TransmitBlockReason.PAGE_NOT_FOUND

    left_unstable = [e for e in guidance if e.side is Side.LEFT and e.reason is TransmitBlockReason.UNSTABLE]
    assert len(left_unstable) == 4  # frames 1-4 of the 5 consistent LEFT frames

    assert len(transmits) == 2
    assert transmits[0].side is Side.LEFT
    assert transmits[1].side is Side.RIGHT
    assert len(transmitted) == 2  # transmit_fn was actually called for both

    assert len(completes) == 1  # only after RIGHT finishes, not after LEFT


def test_history_resets_between_pages(monkeypatch):
    """After LEFT transmits, a bad RIGHT frame shouldn't be judged against
    LEFT's leftover stability history."""
    monkeypatch.setattr(loop_module, "judge_final", _always_transmittable)

    frames = (
        [_background_frame()]
        + [_frame_with_book(Side.LEFT)] * 5  # LEFT settles and transmits
        + [_background_frame()]  # RIGHT: no book -> must be PAGE_NOT_FOUND, not stale UNSTABLE
    )

    with _tmp_dir() as output_dir:
        events = list(run_session(ListCaptureSource(frames), output_dir, transmit_fn=lambda _p: None))

    last_guidance = [e for e in events if isinstance(e, GuidanceEvent)][-1]
    assert last_guidance.side is Side.RIGHT
    assert last_guidance.reason is TransmitBlockReason.PAGE_NOT_FOUND


def test_no_background_frame_yields_nothing():
    with _tmp_dir() as output_dir:
        events = list(run_session(ListCaptureSource([]), output_dir, transmit_fn=lambda _p: None))
    assert events == []
