"""Obstruction detector boundary and a non-authoritative chroma baseline."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

import cv2
import numpy as np

from .types import PageSide


@dataclass(frozen=True, slots=True)
class ObstructionResult:
    detected: bool
    content_occluded: bool
    confidence: float
    side: PageSide | None
    bbox_preview: tuple[int, int, int, int] | None
    component_area_fraction: float
    content_overlap_fraction: float
    detector_name: str
    detector_version: str
    runtime_provenance: str


class ObstructionDetector(Protocol):
    def detect(
        self,
        image_bgr: np.ndarray,
        page_masks: Mapping[PageSide, np.ndarray],
    ) -> ObstructionResult: ...


@dataclass(frozen=True, slots=True)
class ChromaContourConfig:
    min_component_area_fraction: float = 0.025
    content_inset_fraction: float = 0.04
    min_content_overlap_fraction: float = 0.35


class DiagnosticChromaContourObstructionDetector:
    """Skin-like connected-component comparison signal, never a hard gate.

    Warm paper, colored boxes, illumination, and skin-tone diversity make this
    unsuitable as an authoritative detector.  ``content_occluded`` therefore
    remains false even when the diagnostic reports a likely component.
    """

    name = "chroma-contour-diagnostic"
    version = "v1"
    provenance = "local-classical-baseline-no-model"

    def __init__(self, config: ChromaContourConfig = ChromaContourConfig()):
        self.config = config

    def detect(
        self,
        image_bgr: np.ndarray,
        page_masks: Mapping[PageSide, np.ndarray],
    ) -> ObstructionResult:
        ycrcb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2YCrCb)
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        chroma = (
            (ycrcb[:, :, 1] >= 133)
            & (ycrcb[:, :, 1] <= 173)
            & (ycrcb[:, :, 2] >= 77)
            & (ycrcb[:, :, 2] <= 127)
            & (hsv[:, :, 1] >= 20)
            & (hsv[:, :, 1] <= 180)
        )
        chroma_u8 = chroma.astype(np.uint8)
        chroma_u8 = cv2.morphologyEx(chroma_u8, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        chroma_u8 = cv2.morphologyEx(chroma_u8, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

        best: tuple[float, float, PageSide, tuple[int, int, int, int]] | None = None
        for side, page_mask in page_masks.items():
            active = page_mask > 0
            page_area = int(np.count_nonzero(active))
            if page_area == 0:
                continue
            restricted = np.where(active, chroma_u8, 0).astype(np.uint8)
            count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
                restricted, connectivity=8
            )
            if count <= 1:
                continue
            component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            area = int(stats[component, cv2.CC_STAT_AREA])
            area_fraction = area / page_area
            component_mask = (_labels == component).astype(np.uint8)
            inset = max(3, round(min(image_bgr.shape[:2]) * self.config.content_inset_fraction))
            kernel_size = inset * 2 + 1
            content_proxy = cv2.erode(
                active.astype(np.uint8), np.ones((kernel_size, kernel_size), np.uint8)
            )
            overlap = int(np.count_nonzero(component_mask & content_proxy)) / max(1, area)
            bbox = tuple(int(value) for value in stats[component, :4])
            if best is None or area_fraction > best[0]:
                best = (area_fraction, overlap, side, bbox)

        if best is None:
            return self._empty()
        area_fraction, overlap, side, bbox = best
        detected = bool(
            area_fraction >= self.config.min_component_area_fraction
            and overlap >= self.config.min_content_overlap_fraction
        )
        confidence = min(1.0, area_fraction / max(self.config.min_component_area_fraction * 4, 1e-9))
        return ObstructionResult(
            detected=detected,
            content_occluded=False,
            confidence=float(confidence),
            side=side if detected else None,
            bbox_preview=bbox if detected else None,
            component_area_fraction=float(area_fraction),
            content_overlap_fraction=float(overlap),
            detector_name=self.name,
            detector_version=self.version,
            runtime_provenance=self.provenance,
        )

    def _empty(self) -> ObstructionResult:
        return ObstructionResult(
            False,
            False,
            0.0,
            None,
            None,
            0.0,
            0.0,
            self.name,
            self.version,
            self.provenance,
        )


@dataclass(frozen=True, slots=True)
class EdgeChromaIntrusionConfig:
    """Provisional fixed-camera hand ingress thresholds at preview resolution."""

    min_luminance: int = 35
    cr_min: int = 133
    cr_max: int = 180
    cb_min: int = 75
    cb_max: int = 135
    saturation_min: int = 20
    saturation_max: int = 200
    border_depth_px: int = 2
    min_component_area_fraction: float = 0.003
    page_proximity_dilation_fraction: float = 0.03
    min_page_proximity_fraction: float = 0.05

    def __post_init__(self) -> None:
        for name in (
            "min_luminance",
            "cr_min",
            "cr_max",
            "cb_min",
            "cb_max",
            "saturation_min",
            "saturation_max",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
                raise ValueError(f"{name} must be an integer in [0, 255]")
        if self.cr_min > self.cr_max or self.cb_min > self.cb_max:
            raise ValueError("chroma minimums must not exceed maximums")
        if self.saturation_min > self.saturation_max:
            raise ValueError("saturation_min must not exceed saturation_max")
        if self.border_depth_px <= 0:
            raise ValueError("border_depth_px must be positive")
        for name in (
            "min_component_area_fraction",
            "page_proximity_dilation_fraction",
            "min_page_proximity_fraction",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
                raise ValueError(f"{name} must be in (0, 1]")


class EdgeChromaIntrusionObstructionDetector:
    """Detect a skin-like component entering a page from the frame boundary.

    The scanner has a fixed overhead composition and users manipulate the book
    from outside the frame.  This makes border connectivity a useful, cheap
    discriminator that also catches partial fingers missed by landmark models.
    The color range is intentionally provisional until held-out skin tones and
    backgrounds are available.
    """

    name = "edge-chroma-intrusion"
    version = "v1"
    provenance = "local-classical-fixed-camera-provisional"

    def __init__(self, config: EdgeChromaIntrusionConfig = EdgeChromaIntrusionConfig()):
        self.config = config

    def detect(
        self,
        image_bgr: np.ndarray,
        page_masks: Mapping[PageSide, np.ndarray],
    ) -> ObstructionResult:
        height, width = image_bgr.shape[:2]
        page_union = np.zeros((height, width), dtype=np.uint8)
        for page_mask in page_masks.values():
            page_union |= (page_mask > 0).astype(np.uint8)
        if not np.any(page_union):
            return self._empty()

        ycrcb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2YCrCb)
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        skin = (
            (ycrcb[:, :, 0] >= self.config.min_luminance)
            & (ycrcb[:, :, 1] >= self.config.cr_min)
            & (ycrcb[:, :, 1] <= self.config.cr_max)
            & (ycrcb[:, :, 2] >= self.config.cb_min)
            & (ycrcb[:, :, 2] <= self.config.cb_max)
            & (hsv[:, :, 1] >= self.config.saturation_min)
            & (hsv[:, :, 1] <= self.config.saturation_max)
        ).astype(np.uint8)
        skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

        dilation = max(
            3,
            round(min(height, width) * self.config.page_proximity_dilation_fraction),
        )
        page_near = cv2.dilate(
            page_union,
            np.ones((dilation * 2 + 1, dilation * 2 + 1), np.uint8),
        )
        count, labels, stats, _centroids = cv2.connectedComponentsWithStats(skin, connectivity=8)
        image_area = max(1, height * width)
        best: tuple[float, float, int, tuple[int, int, int, int]] | None = None
        for component in range(1, count):
            x, y, component_width, component_height, area = (
                int(value) for value in stats[component, :5]
            )
            depth = self.config.border_depth_px
            touches_border = bool(
                x < depth
                or y < depth
                or x + component_width > width - depth
                or y + component_height > height - depth
            )
            area_fraction = area / image_area
            if not touches_border or area_fraction < self.config.min_component_area_fraction:
                continue
            component_mask = labels == component
            proximity = int(np.count_nonzero(component_mask & (page_near > 0))) / max(1, area)
            if proximity < self.config.min_page_proximity_fraction:
                continue
            bbox = (x, y, component_width, component_height)
            rank = (area_fraction, proximity)
            if best is None or rank > (best[0], best[1]):
                best = (area_fraction, proximity, component, bbox)

        if best is None:
            return self._empty()
        area_fraction, proximity, component, bbox = best
        component_mask = labels == component
        best_side: PageSide | None = None
        best_side_overlap = 0
        for side, page_mask in page_masks.items():
            side_near = cv2.dilate(
                (page_mask > 0).astype(np.uint8),
                np.ones((dilation * 2 + 1, dilation * 2 + 1), np.uint8),
            )
            overlap = int(np.count_nonzero(component_mask & (side_near > 0)))
            if overlap > best_side_overlap:
                best_side_overlap = overlap
                best_side = side
        confidence = min(
            1.0,
            0.5 * area_fraction / (self.config.min_component_area_fraction * 10)
            + 0.5 * proximity / (self.config.min_page_proximity_fraction * 10),
        )
        return ObstructionResult(
            True,
            True,
            float(confidence),
            best_side,
            bbox,
            float(area_fraction),
            float(proximity),
            self.name,
            self.version,
            self.provenance,
        )

    def _empty(self) -> ObstructionResult:
        return ObstructionResult(
            False,
            False,
            0.0,
            None,
            None,
            0.0,
            0.0,
            self.name,
            self.version,
            self.provenance,
        )


@dataclass(frozen=True, slots=True)
class MediaPipeHandConfig:
    model_path: Path
    expected_sha256: str
    min_hand_detection_confidence: float = 0.10
    min_hand_presence_confidence: float = 0.10
    bbox_padding_fraction: float = 0.18
    content_inset_fraction: float = 0.04
    min_content_overlap_fraction: float = 0.10

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", self.expected_sha256):
            raise ValueError("expected_sha256 must be 64 hexadecimal characters")
        for name in (
            "min_hand_detection_confidence",
            "min_hand_presence_confidence",
            "bbox_padding_fraction",
            "content_inset_fraction",
            "min_content_overlap_fraction",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")


class MediaPipeHandObstructionDetector:
    """Offline MediaPipe hand adapter with an explicitly pinned model file.

    The adapter never downloads a model.  Model redistribution/license review
    is an integration responsibility separate from the Apache-2.0 SDK code.
    """

    name = "mediapipe-hand-landmarker"
    version = "sdk-0.10.35-adapter-v1"

    def __init__(self, config: MediaPipeHandConfig):
        self.config = config
        model_path = Path(config.model_path).resolve()
        if not model_path.is_file():
            raise FileNotFoundError(f"MediaPipe hand model does not exist: {model_path}")
        actual_sha = _sha256_file(model_path)
        if actual_sha.lower() != config.expected_sha256.lower():
            raise ValueError(
                f"MediaPipe hand model SHA-256 mismatch: expected {config.expected_sha256}, "
                f"got {actual_sha}"
            )
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe runtime is unavailable; install the hand-detection optional dependency"
            ) from exc
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_hands=2,
            min_hand_detection_confidence=config.min_hand_detection_confidence,
            min_hand_presence_confidence=config.min_hand_presence_confidence,
        )
        self._mp = mp
        self._detector = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self.runtime_provenance = (
            f"mediapipe=0.10.35;model_sha256={actual_sha.lower()};model_path={model_path}"
        )

    def close(self) -> None:
        self._detector.close()

    def detect(
        self,
        image_bgr: np.ndarray,
        page_masks: Mapping[PageSide, np.ndarray],
    ) -> ObstructionResult:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        detected = self._detector.detect(image)
        if not detected.hand_landmarks:
            return ObstructionResult(
                False,
                False,
                0.0,
                None,
                None,
                0.0,
                0.0,
                self.name,
                self.version,
                self.runtime_provenance,
            )

        height, width = image_bgr.shape[:2]
        best: tuple[float, float, PageSide | None, tuple[int, int, int, int], float] | None = None
        for ordinal, landmarks in enumerate(detected.hand_landmarks):
            xs = [float(item.x) * width for item in landmarks]
            ys = [float(item.y) * height for item in landmarks]
            x0, x1 = min(xs), max(xs)
            y0, y1 = min(ys), max(ys)
            pad_x = (x1 - x0) * self.config.bbox_padding_fraction
            pad_y = (y1 - y0) * self.config.bbox_padding_fraction
            left = max(0, int(round(x0 - pad_x)))
            top = max(0, int(round(y0 - pad_y)))
            right = min(width, int(round(x1 + pad_x)))
            bottom = min(height, int(round(y1 + pad_y)))
            bbox = (left, top, max(1, right - left), max(1, bottom - top))
            bbox_mask = np.zeros((height, width), dtype=np.uint8)
            bbox_mask[top:bottom, left:right] = 1
            bbox_area = max(1, int(np.count_nonzero(bbox_mask)))
            best_side: PageSide | None = None
            best_overlap = 0.0
            best_page_fraction = 0.0
            inset = max(3, round(min(height, width) * self.config.content_inset_fraction))
            kernel = np.ones((inset * 2 + 1, inset * 2 + 1), np.uint8)
            for side, page_mask in page_masks.items():
                page_active = page_mask > 0
                content_proxy = cv2.erode(page_active.astype(np.uint8), kernel)
                overlap = int(np.count_nonzero(bbox_mask & content_proxy)) / bbox_area
                page_fraction = int(np.count_nonzero(bbox_mask & page_active)) / max(
                    1, int(np.count_nonzero(page_active))
                )
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_page_fraction = page_fraction
                    best_side = side
            handedness = detected.handedness[ordinal] if ordinal < len(detected.handedness) else ()
            confidence = max((float(item.score) for item in handedness), default=0.0)
            rank = (best_overlap, confidence)
            if best is None or rank > (best[0], best[1]):
                best = (best_overlap, confidence, best_side, bbox, best_page_fraction)

        assert best is not None
        overlap, confidence, side, bbox, page_fraction = best
        content_occluded = bool(
            side is not None and overlap >= self.config.min_content_overlap_fraction
        )
        return ObstructionResult(
            True,
            content_occluded,
            confidence,
            side,
            bbox,
            page_fraction,
            overlap,
            self.name,
            self.version,
            self.runtime_provenance,
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
