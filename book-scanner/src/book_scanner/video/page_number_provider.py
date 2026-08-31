"""Page-number provider for corrected V2 artifacts and masked previews."""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from .config import PageNumberPolicy
from .page_number import (
    PageNumberObservation,
    PageNumberRecognition,
    PageNumberRecognitionCache,
    PageNumberSource,
    PageNumberStatus,
    SpreadPageKey,
    SpreadPageNumberObservation,
    SpreadPageNumberStatus,
    normalize_page_label,
    roi_sha256,
)
from .protocols import PageNumberRecognizer
from .page_number_roi import corrected_page_number_roi, preview_page_number_roi
from .types import ArtifactId, FrameId, PageSide, SpreadArtifactRef


class OpenCVBottomRoiPageNumberProvider:
    def __init__(
        self,
        policy: PageNumberPolicy = PageNumberPolicy(),
        recognizer: PageNumberRecognizer | None = None,
    ) -> None:
        if recognizer is None:
            raise ValueError("recognizer must be selected explicitly after backend evaluation")
        self.policy = policy
        self.recognizer = recognizer
        self.cache = PageNumberRecognitionCache(policy.cache_capacity)

    def observe_artifact(
        self,
        artifact: SpreadArtifactRef,
        data_pack_id: str,
    ) -> SpreadPageNumberObservation:
        started = time.perf_counter()
        pages = []
        for page in (artifact.left, artifact.right):
            image = cv2.imread(str(Path(page.image_path)), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"cannot decode {page.side.value} corrected page")
            roi, bbox = corrected_page_number_roi(image, page.side, self.policy)
            pages.append(
                self._observe_roi(
                    roi,
                    bbox,
                    page.side,
                    PageNumberSource.CORRECTED,
                    artifact.source_frame_id,
                    artifact.artifact_id,
                )
            )
        return _spread(pages[0], pages[1], data_pack_id, self.policy, (time.perf_counter() - started) * 1000.0)

    def observe_preview(
        self,
        gray_preview: np.ndarray,
        mask_preview: np.ndarray,
        seam_fraction: float | None,
        source_frame_id: FrameId,
        data_pack_id: str,
    ) -> SpreadPageNumberObservation:
        started = time.perf_counter()
        pages = []
        for side in (PageSide.LEFT, PageSide.RIGHT):
            try:
                roi, bbox = preview_page_number_roi(
                    gray_preview,
                    mask_preview,
                    seam_fraction,
                    side,
                    self.policy,
                )
                observation = self._observe_roi(
                    roi,
                    bbox,
                    side,
                    PageNumberSource.PREVIEW,
                    source_frame_id,
                    None,
                )
            except ValueError:
                observation = _missing_observation(
                    side,
                    PageNumberSource.PREVIEW,
                    source_frame_id,
                    self.recognizer,
                )
            pages.append(observation)
        return _spread(pages[0], pages[1], data_pack_id, self.policy, (time.perf_counter() - started) * 1000.0)

    def _observe_roi(
        self,
        roi: np.ndarray,
        bbox: tuple[int, int, int, int],
        side: PageSide,
        source_kind: PageNumberSource,
        source_frame_id: FrameId,
        artifact_id: ArtifactId | None,
    ) -> PageNumberObservation:
        digest = roi_sha256(roi)
        cache_key = (
            f"{self.recognizer.engine_id}:{self.recognizer.engine_version}",
            self.recognizer.preprocessing_version,
            side.value,
            source_kind.value,
            digest,
        )
        recognition = self.cache.get(cache_key)
        cache_hit = recognition is not None
        if recognition is None:
            recognition = self.recognizer.recognize(roi, side)
            self.cache.put(cache_key, recognition)
        normalized = normalize_page_label(recognition.raw_text, self.policy)
        status = recognition.status
        if status is PageNumberStatus.OBSERVED and normalized is None:
            status = PageNumberStatus.INVALID
        if status is PageNumberStatus.OBSERVED and (
            recognition.confidence is None
            or recognition.confidence < self.policy.min_confidence
            or recognition.variant_agreement < self.policy.required_variant_agreement
        ):
            status = PageNumberStatus.CONFLICT
            normalized = None
        translated_bbox = None
        if recognition.bbox is not None:
            translated_bbox = (
                bbox[0] + recognition.bbox[0],
                bbox[1] + recognition.bbox[1],
                recognition.bbox[2],
                recognition.bbox[3],
            )
        return PageNumberObservation(
            side,
            recognition.raw_text,
            normalized if status is PageNumberStatus.OBSERVED else None,
            recognition.confidence,
            translated_bbox,
            digest,
            source_kind,
            source_frame_id,
            artifact_id,
            self.recognizer.engine_id,
            self.recognizer.engine_version,
            self.recognizer.preprocessing_version,
            recognition.variant_agreement,
            status,
            cache_hit,
        )


def _spread(
    left: PageNumberObservation,
    right: PageNumberObservation,
    data_pack_id: str,
    policy: PageNumberPolicy,
    processing_ms: float,
) -> SpreadPageNumberObservation:
    if not data_pack_id.strip():
        raise ValueError("data_pack_id must be non-empty")
    observed = sum(item.status is PageNumberStatus.OBSERVED for item in (left, right))
    has_conflict = any(item.status in {PageNumberStatus.CONFLICT, PageNumberStatus.INVALID} for item in (left, right))
    if observed == 2:
        status = SpreadPageNumberStatus.COMPLETE
        assert left.normalized_label is not None and right.normalized_label is not None
        key = SpreadPageKey(
            data_pack_id,
            left.normalized_label,
            right.normalized_label,
            f"{policy.algorithm_version}:{left.engine_id}:{left.engine_version}",
        )
    elif has_conflict:
        status = SpreadPageNumberStatus.CONFLICT
        key = None
    elif observed == 1:
        status = SpreadPageNumberStatus.PARTIAL
        key = None
    else:
        status = SpreadPageNumberStatus.MISSING
        key = None
    return SpreadPageNumberObservation(left, right, key, status, max(0.0, processing_ms))


def _missing_observation(
    side: PageSide,
    source_kind: PageNumberSource,
    source_frame_id: FrameId,
    recognizer: PageNumberRecognizer,
) -> PageNumberObservation:
    return PageNumberObservation(
        side,
        None,
        None,
        None,
        None,
        "0" * 64,
        source_kind,
        source_frame_id,
        None,
        recognizer.engine_id,
        recognizer.engine_version,
        recognizer.preprocessing_version,
        0,
        PageNumberStatus.NOT_OBSERVED,
    )
