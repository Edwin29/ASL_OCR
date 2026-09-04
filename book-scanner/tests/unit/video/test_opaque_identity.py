from __future__ import annotations

import pytest

from book_scanner.video.config import (
    OpaqueFooterIdentityPolicy,
    OpaqueFooterInputStage,
    OpaqueIdentityStrategy,
    VideoScannerConfig,
)
from book_scanner.video.opaque_identity import (
    InMemoryOpaqueIdentityLedger,
    OpaqueFooterTokenPair,
    OpaqueIdentityDecisionKind,
    OpaqueQueryCollector,
    OpaqueReferenceBank,
)
from book_scanner.video.types import ArtifactId, FrameId


def _pair(frame: int, left: str = "30", right: str = "309") -> OpaqueFooterTokenPair:
    return OpaqueFooterTokenPair(
        left,
        right,
        FrameId(f"frame-{frame}"),
        frame / 10.0,
        "preview_native",
        "fake:1:raw",
        f"{frame:064x}",
        f"{frame + 100:064x}",
    )


def _bank(artifact: str, pairs) -> OpaqueReferenceBank:
    return OpaqueReferenceBank(
        ArtifactId(artifact),
        f"receipt-{artifact}",
        "pack",
        tuple(pairs),
        "test",
    )


def test_application_default_selects_m1_native_n5_any_match():
    policy = VideoScannerConfig().opaque_footer_identity
    assert policy.strategy is OpaqueIdentityStrategy.M1_SELECTED_RAW_PAIR
    assert policy.input_stage is OpaqueFooterInputStage.PREVIEW_NATIVE
    assert (policy.query_sample_count, policy.k_same, policy.k_different) == (5, 1, 0)
    assert not policy.validated


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query_sample_count": 0},
        {"observation_interval_ms": 0},
        {"query_sample_count": 3, "k_same": 4},
        {"k_same": 0},
        {"k_different": 1, "k_same": 1},
        {"max_recognition_in_flight": 2},
    ],
)
def test_invalid_policy_is_rejected(kwargs):
    with pytest.raises((ValueError, TypeError)):
        OpaqueFooterIdentityPolicy(**kwargs)


def test_missing_does_not_consume_a_trial_or_become_different():
    policy = OpaqueFooterIdentityPolicy(query_sample_count=3)
    collector = OpaqueQueryCollector(policy, [_bank("a", [_pair(1)])], started_at=0.0)
    for _ in range(10):
        decision = collector.observe_missing()
    assert decision.kind is OpaqueIdentityDecisionKind.UNKNOWN
    assert decision.valid_observations == 0


def test_first_pair_match_decides_same_early_and_requires_both_raw_tokens():
    policy = OpaqueFooterIdentityPolicy(query_sample_count=5)
    collector = OpaqueQueryCollector(policy, [_bank("a", [_pair(1)])], started_at=0.0)
    decision = collector.observe(_pair(2))
    assert decision.kind is OpaqueIdentityDecisionKind.SAME
    assert decision.valid_observations == 1
    assert decision.matched_artifact_id == ArtifactId("a")
    with pytest.raises(ValueError):
        _pair(3, right="")


def test_different_requires_n_valid_all_mismatches_with_query_majority():
    policy = OpaqueFooterIdentityPolicy(query_sample_count=3)
    collector = OpaqueQueryCollector(policy, [_bank("a", [_pair(1)])], started_at=0.0)
    assert collector.observe(_pair(2, "31", "310")).kind is OpaqueIdentityDecisionKind.UNKNOWN
    assert collector.observe(_pair(3, "31", "310")).kind is OpaqueIdentityDecisionKind.UNKNOWN
    decision = collector.observe(_pair(4, "31", "310"))
    assert decision.kind is OpaqueIdentityDecisionKind.DIFFERENT
    assert decision.novel_consensus_count == 3
    assert not decision.coherent_numeric_difference


def test_consecutive_numeric_reference_and_query_corroborate_page_change():
    policy = OpaqueFooterIdentityPolicy(query_sample_count=5)
    collector = OpaqueQueryCollector(
        policy,
        [_bank("a", [_pair(frame, "26", "27") for frame in range(1, 6)])],
        started_at=0.0,
    )

    for frame in range(6, 11):
        decision = collector.observe(_pair(frame, "28", "29"))

    assert decision.kind is OpaqueIdentityDecisionKind.DIFFERENT
    assert decision.novel_consensus_count == 5
    assert decision.coherent_numeric_difference


def test_unrelated_ocr_mismatches_do_not_false_trigger_page_change():
    policy = OpaqueFooterIdentityPolicy(query_sample_count=5, max_collection_ms=100)
    collector = OpaqueQueryCollector(policy, [_bank("a", [_pair(1)])], started_at=0.0)

    for frame, value in enumerate(("31", "3I", "B1", "37", ""), start=2):
        decision = collector.observe(_pair(frame, value or "8I", f"R-{frame}"))

    assert decision.kind is OpaqueIdentityDecisionKind.UNKNOWN
    assert decision.novel_consensus_count == 1
    assert collector.decision(now=0.101).timed_out


def test_first_spread_also_requires_a_stable_opaque_pair():
    policy = OpaqueFooterIdentityPolicy(query_sample_count=5, max_collection_ms=100)
    collector = OpaqueQueryCollector(policy, [], started_at=0.0)

    for frame in range(1, 6):
        decision = collector.observe(_pair(frame, f"L-{frame}", f"R-{frame}"))

    assert decision.kind is OpaqueIdentityDecisionKind.UNKNOWN
    assert collector.decision(now=0.101).timed_out


def test_timeout_is_unknown_and_frame_overlap_is_rejected():
    policy = OpaqueFooterIdentityPolicy(max_collection_ms=100)
    collector = OpaqueQueryCollector(policy, [_bank("a", [_pair(1)])], started_at=0.0)
    assert collector.decision(now=0.101).timed_out
    with pytest.raises(ValueError, match="frame-disjoint"):
        collector.observe(_pair(1))


def test_ack_is_the_only_pending_to_accepted_transition_and_ring_is_bounded():
    policy = OpaqueFooterIdentityPolicy(reference_bank_size=2, accepted_bank_capacity=2)
    ledger = InMemoryOpaqueIdentityLedger(policy, "pack")
    ledger.register_pending(ArtifactId("a"), [_pair(1), _pair(2), _pair(3)])
    assert ledger.confirm(ArtifactId("stale"), "no") is None
    first = ledger.confirm(ArtifactId("a"), "r-a")
    assert first is not None and len(first.observations) == 2
    for index, name in enumerate(("b", "c"), start=4):
        ledger.register_pending(ArtifactId(name), [_pair(index)])
        assert ledger.confirm(ArtifactId(name), f"r-{name}") is not None
    assert [item.artifact_id.value for item in ledger.recent_accepted()] == ["c", "b"]


def test_reject_releases_only_matching_pending():
    ledger = InMemoryOpaqueIdentityLedger(OpaqueFooterIdentityPolicy(), "pack")
    ledger.register_pending(ArtifactId("a"), [_pair(1)])
    assert not ledger.reject_or_release(ArtifactId("stale"))
    assert ledger.reject_or_release(ArtifactId("a"))
    assert ledger.pending_artifact_id is None
