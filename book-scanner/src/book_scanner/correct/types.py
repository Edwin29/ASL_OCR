"""Shared data types for the perspective-correction / scan-output stage
(roadmap Stage 6: "페이지 보정 및 스캔 산출물 생성")."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Corners:
    """Four corner points in the *original* (uncorrected) image's pixel
    coordinates. Order matters: top-left, top-right, bottom-right,
    bottom-left."""

    top_left: tuple[float, float]
    top_right: tuple[float, float]
    bottom_right: tuple[float, float]
    bottom_left: tuple[float, float]

    def as_tuple(self) -> tuple[tuple[float, float], ...]:
        return (self.top_left, self.top_right, self.bottom_right, self.bottom_left)


@dataclass(frozen=True)
class CorrectionMetadata:
    """Record tying an original capture to its perspective-corrected output.

    Exists so "원본, 보정본과 촬영 메타데이터의 관계를 추적할 수 있다" (Stage 6
    완료 조건) is actually checkable later, not just asserted -- both file
    hashes are of the files as they exist on disk right now, so a caller can
    re-hash and compare to detect tampering or a stale/mismatched pair.
    """

    capture_id: str
    original_path: str
    original_sha256: str
    corrected_path: str
    corrected_sha256: str
    corners: tuple[tuple[float, float], ...]
    output_size: tuple[int, int]  # (width, height) of the corrected image
    created_at_utc: str  # ISO 8601

    def to_jsonable(self) -> dict[str, object]:
        return {
            "capture_id": self.capture_id,
            "original_path": self.original_path,
            "original_sha256": self.original_sha256,
            "corrected_path": self.corrected_path,
            "corrected_sha256": self.corrected_sha256,
            "corners": [list(p) for p in self.corners],
            "output_size": list(self.output_size),
            "created_at_utc": self.created_at_utc,
        }
