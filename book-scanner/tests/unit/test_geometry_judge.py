from __future__ import annotations

from book_scanner.detect.types import PageGeometry
from book_scanner.judge.geometry_judge import GeometryThresholds, judge_geometry
from book_scanner.judge.types import TransmitBlockReason

FRAME = (400, 300)


def _geometry(
    angle_deg: float = 0.0,
    area_ratio: float = 0.5,
    corners: tuple[tuple[float, float], ...] | None = None,
    touches_frame_edge: bool = False,
) -> PageGeometry:
    if corners is None:
        corners = ((50.0, 50.0), (350.0, 50.0), (350.0, 250.0), (50.0, 250.0))
    return PageGeometry(
        corners=corners,
        center=(200.0, 150.0),
        size=(300.0, 200.0),
        angle_deg=angle_deg,
        area_ratio=area_ratio,
        frame_size=FRAME,
        touches_frame_edge=touches_frame_edge,
    )


def test_none_geometry_is_page_not_found():
    assert judge_geometry(None) is TransmitBlockReason.PAGE_NOT_FOUND


def test_well_placed_page_passes():
    assert judge_geometry(_geometry()) is None


def test_rotated_too_much():
    assert judge_geometry(_geometry(angle_deg=30.0)) is TransmitBlockReason.ROTATED_TOO_MUCH


def test_too_small():
    assert judge_geometry(_geometry(area_ratio=0.05)) is TransmitBlockReason.TOO_SMALL


def test_too_large():
    assert judge_geometry(_geometry(area_ratio=0.99)) is TransmitBlockReason.TOO_LARGE


def test_out_of_frame():
    assert judge_geometry(_geometry(touches_frame_edge=True)) is TransmitBlockReason.OUT_OF_FRAME


def test_thresholds_are_overridable():
    strict = GeometryThresholds(max_skew_deg=1.0)
    assert judge_geometry(_geometry(angle_deg=5.0), strict) is TransmitBlockReason.ROTATED_TOO_MUCH
