from __future__ import annotations

from book_scanner.video.config import GuidancePolicy
from book_scanner.video.guidance import GuidanceArbiter
from book_scanner.video.types import ReadinessReason


def test_guidance_requires_stable_reason_and_cools_down_repeats() -> None:
    arbiter = GuidanceArbiter(
        GuidancePolicy(
            reason_hold_samples=3,
            reason_hold_ms=1000,
            repeat_cooldown_ms=5000,
        )
    )

    assert arbiter.observe(ReadinessReason.PAGE_NOT_FOUND, 10.0) is None
    assert arbiter.observe(ReadinessReason.PAGE_NOT_FOUND, 10.5) is None
    first = arbiter.observe(ReadinessReason.PAGE_NOT_FOUND, 11.0)
    assert first is not None
    assert first.stable_for_samples == 3
    assert first.stable_for_ms == 1000

    assert arbiter.observe(ReadinessReason.PAGE_NOT_FOUND, 12.0) is None
    repeated = arbiter.observe(ReadinessReason.PAGE_NOT_FOUND, 16.0)
    assert repeated is not None
    assert repeated.reason is ReadinessReason.PAGE_NOT_FOUND


def test_guidance_reason_change_must_stabilize_before_replacing_audio() -> None:
    arbiter = GuidanceArbiter(
        GuidancePolicy(
            reason_hold_samples=2,
            reason_hold_ms=500,
            repeat_cooldown_ms=5000,
        )
    )
    assert arbiter.observe(ReadinessReason.PAGE_NOT_FOUND, 1.0) is None
    assert arbiter.observe(ReadinessReason.PAGE_NOT_FOUND, 1.5) is not None

    assert arbiter.observe(ReadinessReason.CONTENT_OCCLUDED, 2.0) is None
    changed = arbiter.observe(ReadinessReason.CONTENT_OCCLUDED, 2.5)
    assert changed is not None
    assert changed.reason is ReadinessReason.CONTENT_OCCLUDED


def test_ready_observation_resets_pending_reason_but_keeps_repeat_history() -> None:
    arbiter = GuidanceArbiter(
        GuidancePolicy(
            reason_hold_samples=1,
            reason_hold_ms=0,
            repeat_cooldown_ms=5000,
        )
    )
    assert arbiter.observe(ReadinessReason.PAGE_MOVING, 1.0) is not None
    assert arbiter.observe(None, 2.0) is None
    assert arbiter.observe(ReadinessReason.PAGE_MOVING, 3.0) is None
    assert arbiter.observe(ReadinessReason.PAGE_MOVING, 6.0) is not None
