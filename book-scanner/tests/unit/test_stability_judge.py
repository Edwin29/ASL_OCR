from __future__ import annotations

from book_scanner.detect.types import PageGeometry
from book_scanner.judge.stability_judge import StabilityThresholds, judge_stability
from book_scanner.judge.types import TransmitBlockReason

FRAME = (400, 300)


def _geometry(center: tuple[float, float], area_ratio: float = 0.5) -> PageGeometry:
    return PageGeometry(
        corners=((50.0, 50.0), (350.0, 50.0), (350.0, 250.0), (50.0, 250.0)),
        center=center,
        size=(300.0, 200.0),
        angle_deg=0.0,
        area_ratio=area_ratio,
        frame_size=FRAME,
    )


def test_not_enough_history_is_unstable():
    history = [_geometry((200.0, 150.0))] * 2
    assert judge_stability(history, StabilityThresholds(min_frames=5)) is TransmitBlockReason.UNSTABLE


def test_jittery_history_is_unstable():
    history = [_geometry((200.0, 150.0)), _geometry((250.0, 150.0)), _geometry((180.0, 150.0)),
               _geometry((220.0, 150.0)), _geometry((190.0, 150.0))]
    assert judge_stability(history, StabilityThresholds(min_frames=5, max_center_drift_px=15.0)) is TransmitBlockReason.UNSTABLE


def test_settled_history_is_stable():
    history = [_geometry((200.0, 150.0))] * 5
    assert judge_stability(history, StabilityThresholds(min_frames=5)) is None


def test_area_ratio_swing_is_unstable():
    history = [_geometry((200.0, 150.0), area_ratio=r) for r in [0.5, 0.5, 0.5, 0.5, 0.7]]
    assert judge_stability(history, StabilityThresholds(min_frames=5, max_area_ratio_delta=0.05)) is TransmitBlockReason.UNSTABLE


def test_only_recent_window_considered():
    # a jittery start followed by a settled tail long enough to fill the window
    jittery = [_geometry((100.0 + i * 40, 150.0)) for i in range(5)]
    settled = [_geometry((200.0, 150.0))] * 5
    history = jittery + settled
    assert judge_stability(history, StabilityThresholds(min_frames=5)) is None
