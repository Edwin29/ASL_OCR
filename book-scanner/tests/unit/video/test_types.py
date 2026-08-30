from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from book_scanner.video.types import (
    ArtifactId,
    FrameCandidate,
    FrameId,
    PageArtifactRef,
    PageSide,
    PreparationDecision,
    PreparationState,
    ProcessingJobId,
    ReadinessDecision,
    ReadinessReason,
    ReadinessState,
    ReasonCategory,
    SpreadArtifactRef,
    SpreadId,
    is_physical_guidance_reason,
    reason_category,
)
from tests.unit.video.fakes import make_prepared

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def artifact(frame: str = "frame-1") -> SpreadArtifactRef:
    frame_id = FrameId(frame)
    return SpreadArtifactRef(
        artifact_id=ArtifactId("artifact-1"),
        spread_id=SpreadId("spread-1"),
        source_frame_id=frame_id,
        left=PageArtifactRef(PageSide.LEFT, frame_id, "left.jpg", SHA_A, 100, 200),
        right=PageArtifactRef(PageSide.RIGHT, frame_id, "right.jpg", SHA_B, 100, 200),
        manifest_path="manifest.json",
        manifest_sha256=SHA_C,
        evaluator_version="artifact-evaluator-v1",
    )


def test_frame_candidate_round_trip_freezes_metrics() -> None:
    candidate = FrameCandidate(
        frame_id=FrameId("frame-1"),
        captured_at_monotonic=1.25,
        width=1920,
        height=1080,
        evaluator_version="candidate-v1",
        metrics={"motion": 0.01, "page_found": True},
        retry_reasons=(ReadinessReason.PAGE_MOVING,),
    )

    restored = FrameCandidate.from_dict(json.loads(json.dumps(candidate.to_dict())))

    assert restored == candidate
    assert restored.metrics == (("motion", 0.01), ("page_found", True))


def test_decision_round_trip_preserves_strict_reason_enum() -> None:
    item = artifact()
    decision = ReadinessDecision(
        state=ReadinessState.RETRY_REMOTE,
        evaluator_version="transport-v1",
        reasons=(ReadinessReason.NETWORK_UNAVAILABLE,),
        source_frame_id=item.source_frame_id,
        spread_id=item.spread_id,
        artifact=item,
        metrics={"attempt": 1},
        retry_after_ms=500,
    )

    restored = ReadinessDecision.from_dict(json.loads(json.dumps(decision.to_dict())))

    assert restored == decision


def test_preparation_round_trip_preserves_job_lineage() -> None:
    prepared = make_prepared()
    decision = PreparationDecision(
        PreparationState.PREPARED,
        "preparer-v1",
        job_id=prepared.job_id,
        source_frame_id=prepared.source_frame_id,
        spread_id=prepared.spread_id,
        prepared=prepared,
        metrics={"prepare_ms": 12.5},
    )

    restored = PreparationDecision.from_dict(json.loads(json.dumps(decision.to_dict())))

    assert restored == decision


def test_prepared_decision_rejects_mismatched_job() -> None:
    prepared = make_prepared()
    with pytest.raises(ValueError, match="lineage"):
        PreparationDecision(
            PreparationState.PREPARED,
            "preparer-v1",
            job_id=ProcessingJobId("another-job"),
            source_frame_id=prepared.source_frame_id,
            spread_id=prepared.spread_id,
            prepared=prepared,
        )


def test_unknown_schema_and_reason_are_rejected() -> None:
    payload = FrameCandidate(
        FrameId("frame-1"), 0.0, 10, 20, "candidate-v1"
    ).to_dict()
    payload["schema_version"] = "999"
    with pytest.raises(ValueError, match="unsupported video schema"):
        FrameCandidate.from_dict(payload)

    decision_payload = ReadinessDecision(
        state=ReadinessState.RETRY_LOCAL,
        evaluator_version="candidate-v1",
        reasons=(ReadinessReason.BLUR,),
    ).to_dict()
    decision_payload["reasons"] = ["made_up_reason"]
    with pytest.raises(ValueError, match="unknown reasons"):
        ReadinessDecision.from_dict(decision_payload)


def test_spread_artifact_rejects_cross_frame_pages() -> None:
    item = artifact()
    mismatched_right = PageArtifactRef(
        PageSide.RIGHT, FrameId("frame-2"), "right.jpg", SHA_B, 100, 200
    )
    with pytest.raises(ValueError, match="share source_frame_id"):
        SpreadArtifactRef(
            artifact_id=item.artifact_id,
            spread_id=item.spread_id,
            source_frame_id=item.source_frame_id,
            left=item.left,
            right=mismatched_right,
            manifest_path=item.manifest_path,
            manifest_sha256=item.manifest_sha256,
            evaluator_version=item.evaluator_version,
        )


def test_spread_artifact_requires_both_pages_and_hashes() -> None:
    item = artifact()
    with pytest.raises(ValueError, match="both left and right"):
        SpreadArtifactRef(
            artifact_id=item.artifact_id,
            spread_id=item.spread_id,
            source_frame_id=item.source_frame_id,
            left=item.left,
            right=None,  # type: ignore[arg-type]
            manifest_path=item.manifest_path,
            manifest_sha256=item.manifest_sha256,
            evaluator_version=item.evaluator_version,
        )
    with pytest.raises(ValueError, match="SHA-256"):
        PageArtifactRef(PageSide.LEFT, item.source_frame_id, "left.jpg", "", 100, 200)


def test_ready_and_accepted_decisions_require_evidence() -> None:
    with pytest.raises(ValueError, match="requires an artifact"):
        ReadinessDecision(ReadinessState.READY_FOR_PREFLIGHT, "artifact-v1")

    item = artifact()
    with pytest.raises(ValueError, match="delivery_receipt_id"):
        ReadinessDecision(
            ReadinessState.ACCEPTED,
            "parser-v1",
            artifact=item,
            source_frame_id=item.source_frame_id,
            spread_id=item.spread_id,
        )


def test_transport_reason_never_requests_physical_adjustment() -> None:
    assert is_physical_guidance_reason(ReadinessReason.MOVE_RIGHT)
    assert is_physical_guidance_reason(ReadinessReason.SHADOW_UNEVEN)
    assert not is_physical_guidance_reason(ReadinessReason.NETWORK_UNAVAILABLE)
    assert not is_physical_guidance_reason(ReadinessReason.SERVER_BUSY)


def test_every_reason_has_an_explicit_category() -> None:
    assert {reason_category(item) for item in ReadinessReason} == set(ReasonCategory)


def test_serialized_payload_is_detached_from_immutable_object() -> None:
    item = artifact()
    payload = item.to_dict()
    original = deepcopy(payload)
    payload["left"]["image_path"] = "mutated.jpg"
    assert item.to_dict() == original


def test_domain_types_are_frozen() -> None:
    candidate = FrameCandidate(FrameId("frame-1"), 0.0, 10, 20, "candidate-v1")
    with pytest.raises(FrozenInstanceError):
        candidate.width = 11  # type: ignore[misc]


def test_malformed_optional_wire_ids_are_rejected() -> None:
    payload = ReadinessDecision(
        ReadinessState.RETRY_LOCAL,
        "candidate-v1",
        reasons=(ReadinessReason.BLUR,),
    ).to_dict()
    payload["source_frame_id"] = 123
    with pytest.raises(ValueError, match="source_frame_id"):
        ReadinessDecision.from_dict(payload)
