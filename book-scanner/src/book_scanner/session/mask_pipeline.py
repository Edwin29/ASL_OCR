"""Stage 1 frame preparation boundary for a future mask-based session loop.

This deliberately stops before stability, correction, quality, and transmit.
Those policies remain in the established loop until Stage 6 decides how a
partial spread failure should retry.  A fake segmenter can nevertheless run
the exact ROI -> mask -> crop preparation that the session will consume.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from book_scanner.detect.page_mask import (
    MaskPostprocessConfig,
    PageCrop,
    PageMask,
    build_page_mask,
    crop_page,
)
from book_scanner.detect.roi import ROIConfig, PageROI, PageSide, extract_page_rois
from book_scanner.detect.segmenter import PageSegmenter, SegmentationResult


@dataclass(frozen=True)
class MaskPageCandidate:
    side: PageSide
    roi: PageROI
    segmentation: SegmentationResult
    page_mask: PageMask | None
    crop: PageCrop | None
    reject_reason: str | None


class MaskFramePipeline:
    def __init__(
        self,
        segmenter: PageSegmenter,
        roi_config: ROIConfig = ROIConfig(),
        postprocess_config: MaskPostprocessConfig = MaskPostprocessConfig(),
        crop_padding_fraction: float = 0.03,
        neutralize_outside: bool = False,
    ):
        self.segmenter = segmenter
        self.roi_config = roi_config
        self.postprocess_config = postprocess_config
        self.crop_padding_fraction = crop_padding_fraction
        self.neutralize_outside = neutralize_outside

    def process(self, frame: np.ndarray) -> dict[PageSide, MaskPageCandidate]:
        candidates: dict[PageSide, MaskPageCandidate] = {}
        for side, roi in extract_page_rois(frame, self.roi_config).items():
            segmentation = self.segmenter.segment(roi)
            page_mask = build_page_mask(roi, segmentation, self.postprocess_config)
            crop = (
                crop_page(
                    frame,
                    page_mask,
                    padding_fraction=self.crop_padding_fraction,
                    neutralize_outside=self.neutralize_outside,
                )
                if page_mask is not None
                else None
            )
            candidates[side] = MaskPageCandidate(
                side=side,
                roi=roi,
                segmentation=segmentation,
                page_mask=page_mask,
                crop=crop,
                reject_reason=None if page_mask is not None else "no_plausible_page_component",
            )
        return candidates
