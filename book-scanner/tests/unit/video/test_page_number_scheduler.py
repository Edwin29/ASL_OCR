from __future__ import annotations

from book_scanner.video.config import PageNumberSchedulerMode, PageNumberSchedulerPolicy
from book_scanner.video.identity import IdentityMatchKind
from book_scanner.video.page_number_scheduler import (
    PageNumberRequestReason,
    PageNumberVerificationScheduler,
)


def test_every_eligible_preserves_existing_provider_call_boundary() -> None:
    scheduler = PageNumberVerificationScheduler()

    rejected = scheduler.observe(
        eligible=False,
        visual_match_kind=None,
        visual_stable_count=0,
    )
    requested = scheduler.observe(
        eligible=True,
        visual_match_kind=IdentityMatchKind.VISUAL_DUPLICATE,
        visual_stable_count=0,
    )

    assert rejected.requested is False
    assert rejected.reason is PageNumberRequestReason.HARD_GATE_REJECTED
    assert requested.requested is True
    assert requested.reason is PageNumberRequestReason.EVERY_ELIGIBLE
    assert scheduler.diagnostics.sampled_spreads == 2
    assert scheduler.diagnostics.hard_gate_rejected_spreads == 1
    assert scheduler.diagnostics.eligible_spreads == 1
    assert scheduler.diagnostics.requested_spreads == 1


def test_visual_triggered_skips_same_and_limits_changed_burst() -> None:
    scheduler = PageNumberVerificationScheduler(
        PageNumberSchedulerPolicy(
            mode=PageNumberSchedulerMode.VISUAL_TRIGGERED,
            burst_max_eligible_samples=3,
        )
    )

    same = scheduler.observe(
        eligible=True,
        visual_match_kind=IdentityMatchKind.VISUAL_DUPLICATE,
        visual_stable_count=0,
    )
    burst = [
        scheduler.observe(
            eligible=True,
            visual_match_kind=IdentityMatchKind.NEW_SPREAD,
            visual_stable_count=index,
        )
        for index in (1, 2, 3, 3)
    ]

    assert same.requested is False
    assert [item.requested for item in burst] == [True, True, True, False]
    assert burst[-1].reason is PageNumberRequestReason.BURST_TIMEOUT
    assert scheduler.diagnostics.verification_bursts == 1
    assert scheduler.diagnostics.burst_timeouts == 1


def test_hybrid_audit_requests_every_nth_visual_same_sample() -> None:
    scheduler = PageNumberVerificationScheduler(
        PageNumberSchedulerPolicy(
            mode=PageNumberSchedulerMode.HYBRID_AUDITED,
            audit_interval_eligible_samples=4,
        )
    )

    decisions = [
        scheduler.observe(
            eligible=True,
            visual_match_kind=IdentityMatchKind.VISUAL_DUPLICATE,
            visual_stable_count=0,
        )
        for _ in range(8)
    ]

    assert [index for index, item in enumerate(decisions, start=1) if item.requested] == [4, 8]
    assert all(
        item.reason is PageNumberRequestReason.PERIODIC_AUDIT
        for item in decisions
        if item.requested
    )
    assert scheduler.diagnostics.audit_requests == 2
    assert scheduler.diagnostics.requested_spreads == 2
    assert scheduler.diagnostics.skipped_spreads == 6


def test_hard_rejection_resets_burst_continuity() -> None:
    scheduler = PageNumberVerificationScheduler(
        PageNumberSchedulerPolicy(mode=PageNumberSchedulerMode.VISUAL_TRIGGERED)
    )
    first = scheduler.observe(
        eligible=True,
        visual_match_kind=IdentityMatchKind.NEW_SPREAD,
        visual_stable_count=1,
    )
    scheduler.observe(eligible=False, visual_match_kind=None, visual_stable_count=0)
    restarted = scheduler.observe(
        eligible=True,
        visual_match_kind=IdentityMatchKind.NEW_SPREAD,
        visual_stable_count=1,
    )

    assert first.burst_sample_count == 1
    assert restarted.burst_sample_count == 1
    assert scheduler.diagnostics.verification_bursts == 2


def test_hard_rejection_clears_burst_timeout_latch() -> None:
    scheduler = PageNumberVerificationScheduler(
        PageNumberSchedulerPolicy(
            mode=PageNumberSchedulerMode.VISUAL_TRIGGERED,
            burst_max_eligible_samples=1,
        )
    )
    scheduler.observe(
        eligible=True,
        visual_match_kind=IdentityMatchKind.NEW_SPREAD,
        visual_stable_count=1,
    )
    timed_out = scheduler.observe(
        eligible=True,
        visual_match_kind=IdentityMatchKind.NEW_SPREAD,
        visual_stable_count=2,
    )
    scheduler.observe(eligible=False, visual_match_kind=None, visual_stable_count=0)
    restarted = scheduler.observe(
        eligible=True,
        visual_match_kind=IdentityMatchKind.NEW_SPREAD,
        visual_stable_count=1,
    )

    assert timed_out.reason is PageNumberRequestReason.BURST_TIMEOUT
    assert restarted.requested is True
    assert restarted.reason is PageNumberRequestReason.VISUAL_CHANGE_BURST
