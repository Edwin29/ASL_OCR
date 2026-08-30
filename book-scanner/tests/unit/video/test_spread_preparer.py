from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from book_scanner.correct.unwarper import UnwarpFailureReason, UnwarpResult
from book_scanner.correct.uvdoc_adapter import UVDocConfig
from book_scanner.detect.roi import PageSide as DetectionPageSide
from book_scanner.detect.spine_seam import SpineSeam
from book_scanner.detect.spread_extraction import ExtractedPage, SpreadExtractionResult
from book_scanner.video.artifacts import FilesystemArtifactStore
from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.config import CandidatePolicy
from book_scanner.video.engine import SampledFrameEngine
from book_scanner.video.protocols import FrameSample
from book_scanner.video.spread_preparer import (
    SeamUVDocPreparerConfig,
    SeamUVDocSpreadPreparer,
)
from book_scanner.video.types import (
    FrameId,
    PreparationState,
    ProcessingJobId,
    ReadinessReason,
    SpreadId,
    VideoSessionState,
)

from .fakes import FakeCameraSource, ManualClock
from .test_candidate import spread_frame


class FakeExtractor:
    name = "fake-seam-conservative"

    def extract(self, frame: np.ndarray) -> SpreadExtractionResult:
        return _extraction(frame)


class FakeUnwarper:
    name = "fake-uvdoc"

    def __init__(self, failures: dict[int, UnwarpFailureReason] | None = None):
        self.failures = failures or {}
        self.calls = 0
        self.load_count = 0

    def unwarp(self, image: np.ndarray) -> UnwarpResult:
        self.calls += 1
        if self.load_count == 0:
            self.load_count = 1
        reason = self.failures.get(self.calls)
        if reason is not None:
            return UnwarpResult(
                False,
                None,
                self.name,
                "test",
                2.0,
                (image.shape[1], image.shape[0]),
                None,
                reason,
                {"call": self.calls},
            )
        return UnwarpResult(
            True,
            image.copy(),
            self.name,
            "test",
            2.0,
            (image.shape[1], image.shape[0]),
            (image.shape[1], image.shape[0]),
            None,
            {"call": self.calls, "load_count": self.load_count, "sampling_mode": "bilinear"},
        )


def test_v2_preparer_writes_complete_bundle_and_store_commits_atomically(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "staging", tmp_path / "ready")
    unwarper = FakeUnwarper()
    preparer = SeamUVDocSpreadPreparer(
        SeamUVDocPreparerConfig(
            staging_root=store.staging_root,
            min_page_width_px=32,
            min_page_height_px=32,
        ),
        extractor=FakeExtractor(),
        unwarper=unwarper,
    )
    frame = _frame()

    decision = preparer.prepare(
        frame,
        SpreadId("session-1-spread-000001"),
        ProcessingJobId("session-1-job-000001"),
        "session-1",
    )

    assert decision.state is PreparationState.PREPARED
    assert decision.prepared is not None
    staging = Path(decision.prepared.staging_path)
    expected = {
        "manifest.json",
        "source_frame.jpg",
        "left/mask.png",
        "left/crop.jpg",
        "left/uvdoc.jpg",
        "left/diagnostics.json",
        "right/mask.png",
        "right/crop.jpg",
        "right/uvdoc.jpg",
        "right/diagnostics.json",
    }
    assert {path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file()} == expected
    manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["session_id"] == "session-1"
    assert manifest["source_frame_id"] == frame.frame_id.value
    assert manifest["local_readiness"]["ready"] is True
    assert manifest["pipeline"]["silent_uncorrected_fallback"] is False
    assert manifest["uvdoc_runtime"]["load_count"] == 1
    assert len(manifest["files"]) == 9

    artifact = store.commit(decision.prepared)

    assert Path(artifact.manifest_path).is_file()
    assert Path(artifact.left.image_path).is_file()
    assert Path(artifact.right.image_path).is_file()
    assert not staging.exists()
    assert unwarper.calls == 2
    assert unwarper.load_count == 1


@pytest.mark.parametrize(
    ("failure", "state", "reason"),
    [
        (
            UnwarpFailureReason.INFERENCE_FAILED,
            PreparationState.RETRY_LOCAL,
            ReadinessReason.UVDOC_FAILED,
        ),
        (
            UnwarpFailureReason.INVALID_OUTPUT,
            PreparationState.RETRY_LOCAL,
            ReadinessReason.UVDOC_INVALID_OUTPUT,
        ),
        (
            UnwarpFailureReason.MODEL_NOT_FOUND,
            PreparationState.FATAL,
            ReadinessReason.UVDOC_CONFIGURATION_FAILED,
        ),
        (
            UnwarpFailureReason.MODEL_LOAD_FAILED,
            PreparationState.FATAL,
            ReadinessReason.UVDOC_CONFIGURATION_FAILED,
        ),
    ],
)
def test_one_side_uvdoc_failure_never_creates_prepared_bundle(
    tmp_path: Path,
    failure: UnwarpFailureReason,
    state: PreparationState,
    reason: ReadinessReason,
) -> None:
    unwarper = FakeUnwarper({2: failure})
    preparer = SeamUVDocSpreadPreparer(
        SeamUVDocPreparerConfig(
            staging_root=tmp_path / "staging",
            min_page_width_px=32,
            min_page_height_px=32,
        ),
        extractor=FakeExtractor(),
        unwarper=unwarper,
    )

    decision = preparer.prepare(
        _frame(), SpreadId("spread-1"), ProcessingJobId("job-1"), "session-1"
    )

    assert decision.state is state
    assert decision.reasons == (reason,)
    assert decision.prepared is None
    assert not (tmp_path / "staging" / "job-1").exists()


def test_same_preparer_reuses_one_model_load_across_spreads(tmp_path: Path) -> None:
    unwarper = FakeUnwarper()
    preparer = SeamUVDocSpreadPreparer(
        SeamUVDocPreparerConfig(
            staging_root=tmp_path / "staging",
            min_page_width_px=32,
            min_page_height_px=32,
        ),
        extractor=FakeExtractor(),
        unwarper=unwarper,
    )

    first = preparer.prepare(_frame("f-1"), SpreadId("s-1"), ProcessingJobId("j-1"), "session")
    second = preparer.prepare(_frame("f-2"), SpreadId("s-2"), ProcessingJobId("j-2"), "session")

    assert first.state is PreparationState.PREPARED
    assert second.state is PreparationState.PREPARED
    assert unwarper.calls == 4
    assert unwarper.load_count == 1


def test_missing_real_uvdoc_checkpoint_is_explicit_fatal_configuration_error(
    tmp_path: Path,
) -> None:
    preparer = SeamUVDocSpreadPreparer(
        SeamUVDocPreparerConfig(
            staging_root=tmp_path / "staging",
            min_page_width_px=32,
            min_page_height_px=32,
        ),
        UVDocConfig(tmp_path / "missing-runtime", tmp_path / "missing-checkpoint.pkl"),
        extractor=FakeExtractor(),
    )

    decision = preparer.prepare(
        _frame(), SpreadId("spread-1"), ProcessingJobId("job-1"), "session"
    )

    assert decision.state is PreparationState.FATAL
    assert decision.reasons == (ReadinessReason.UVDOC_CONFIGURATION_FAILED,)
    assert decision.prepared is None


def test_v1_engine_publishes_artifact_through_real_v2_preparer_boundary(
    tmp_path: Path,
) -> None:
    clock = ManualClock()
    frames = [
        FrameSample(FrameId(f"frame-{index}"), index * 0.5, spread_frame())
        for index in range(1, 4)
    ]
    store = FilesystemArtifactStore(tmp_path / "staging", tmp_path / "ready")
    preparer = SeamUVDocSpreadPreparer(
        SeamUVDocPreparerConfig(
            staging_root=store.staging_root,
            min_page_width_px=32,
            min_page_height_px=32,
        ),
        extractor=FakeExtractor(),
        unwarper=FakeUnwarper(),
    )
    engine = SampledFrameEngine(
        FakeCameraSource(frames),
        OpenCVCandidateAnalyzer(),
        preparer,
        store,
        session_id="v2-engine-test",
        clock=clock,
        policy=CandidatePolicy(
            sample_interval_ms=100,
            stable_sample_count=3,
            sample_window_size=3,
        ),
    )
    engine.start()
    for _ in range(3):
        engine.poll()
        clock.advance(0.1)
    for _ in range(100):
        engine.poll()
        if engine.state is VideoSessionState.READY_FOR_SERVER_PREFLIGHT:
            break
        time.sleep(0.002)

    assert engine.state is VideoSessionState.READY_FOR_SERVER_PREFLIGHT
    ready = [path for path in store.final_root.iterdir() if path.is_dir()]
    assert len(ready) == 1
    manifest = json.loads((ready[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["session_id"] == "v2-engine-test"
    assert manifest["source_frame_id"] == "frame-3"
    engine.close()


def _frame(identifier: str = "frame-1") -> FrameSample[np.ndarray]:
    image = np.zeros((300, 400, 3), dtype=np.uint8)
    image[20:280, 20:190] = 210
    image[20:280, 210:380] = 220
    return FrameSample(FrameId(identifier), 12.5, image)


def _extraction(frame: np.ndarray) -> SpreadExtractionResult:
    height, width = frame.shape[:2]
    left_mask = np.zeros((height, width), dtype=np.uint8)
    right_mask = np.zeros((height, width), dtype=np.uint8)
    left_mask[20:280, 20:190] = 255
    right_mask[20:280, 210:380] = 255
    seam = SpineSeam(
        tuple((width // 2, y) for y in range(height)),
        0.8,
        8,
        "fake-luminance-valley",
        False,
        {"unit": True},
    )
    left = _page(DetectionPageSide.LEFT, frame, left_mask, (16, 12, 178, 276))
    right = _page(DetectionPageSide.RIGHT, frame, right_mask, (206, 12, 178, 276))
    return SpreadExtractionResult(
        True,
        left,
        right,
        seam,
        {"policy": "union-preserving", "ambiguous_px": 0},
        diagnostics={"source": "unit"},
    )


def _page(
    side: DetectionPageSide,
    frame: np.ndarray,
    full_mask: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> ExtractedPage:
    x, y, width, height = bbox
    return ExtractedPage(
        side,
        frame[y : y + height, x : x + width].copy(),
        full_mask[y : y + height, x : x + width].copy(),
        bbox,
        (4, 8),
        {"top": False, "bottom": False, "outer": False, "spine": False},
        bbox,
        1.0,
        {"unit": True},
    )
