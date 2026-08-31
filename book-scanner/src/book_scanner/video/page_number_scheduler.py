"""Explicit V3-A.3 scheduling for expensive page-number verification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .config import PageNumberSchedulerMode, PageNumberSchedulerPolicy
from .identity import IdentityMatchKind


class PageNumberRequestReason(str, Enum):
    HARD_GATE_REJECTED = "hard_gate_rejected"
    EVERY_ELIGIBLE = "every_eligible"
    VISUAL_SAME_SKIP = "visual_same_skip"
    VISUAL_NOT_CHANGED_SKIP = "visual_not_changed_skip"
    VISUAL_CHANGE_BURST = "visual_change_burst"
    PERIODIC_AUDIT = "periodic_audit"
    BURST_TIMEOUT = "burst_timeout"


@dataclass(frozen=True, slots=True)
class PageNumberScheduleDecision:
    requested: bool
    reason: PageNumberRequestReason
    burst_active: bool
    burst_sample_count: int
    audit_counter: int


@dataclass(frozen=True, slots=True)
class PageNumberSchedulerDiagnostics:
    sampled_spreads: int
    hard_gate_rejected_spreads: int
    eligible_spreads: int
    visual_same_spreads: int
    visual_changed_spreads: int
    visual_ambiguous_spreads: int
    visual_error_spreads: int
    requested_spreads: int
    skipped_spreads: int
    audit_requests: int
    verification_bursts: int
    burst_timeouts: int


class PageNumberVerificationScheduler:
    """Decide whether an eligible preview merits expensive OCR.

    The default mode preserves the V3-A.1/V3-A.2 behavior.  Visual scheduling
    is opt-in and never converts visual evidence into a page-number result.
    """

    def __init__(
        self,
        policy: PageNumberSchedulerPolicy = PageNumberSchedulerPolicy(),
    ) -> None:
        self.policy = policy
        self._sampled = 0
        self._hard_rejected = 0
        self._eligible = 0
        self._visual_same = 0
        self._visual_changed = 0
        self._visual_ambiguous = 0
        self._visual_error = 0
        self._requested = 0
        self._skipped = 0
        self._audit_requests = 0
        self._verification_bursts = 0
        self._burst_timeouts = 0
        self._audit_counter = 0
        self._burst_sample_count = 0
        self._burst_active = False
        self._timed_out_until_visual_reset = False

    @property
    def diagnostics(self) -> PageNumberSchedulerDiagnostics:
        return PageNumberSchedulerDiagnostics(
            self._sampled,
            self._hard_rejected,
            self._eligible,
            self._visual_same,
            self._visual_changed,
            self._visual_ambiguous,
            self._visual_error,
            self._requested,
            self._skipped,
            self._audit_requests,
            self._verification_bursts,
            self._burst_timeouts,
        )

    def reset(self) -> None:
        """Reset temporal state while preserving session-level counters."""

        self._audit_counter = 0
        self._burst_sample_count = 0
        self._burst_active = False
        self._timed_out_until_visual_reset = False

    def observe(
        self,
        *,
        eligible: bool,
        visual_match_kind: IdentityMatchKind | None,
        visual_stable_count: int,
    ) -> PageNumberScheduleDecision:
        self._sampled += 1
        if not eligible:
            self._hard_rejected += 1
            self._reset_burst()
            self._timed_out_until_visual_reset = False
            self._audit_counter = 0
            return self._decision(False, PageNumberRequestReason.HARD_GATE_REJECTED)

        self._eligible += 1
        self._record_visual(visual_match_kind, visual_stable_count)
        if self.policy.mode is PageNumberSchedulerMode.EVERY_ELIGIBLE:
            return self._decision(True, PageNumberRequestReason.EVERY_ELIGIBLE)

        visual_changed = visual_stable_count > 0 and visual_match_kind in {
            IdentityMatchKind.NEW_SPREAD,
            IdentityMatchKind.AMBIGUOUS,
        }
        if visual_changed:
            self._audit_counter = 0
            if self._timed_out_until_visual_reset:
                return self._decision(False, PageNumberRequestReason.BURST_TIMEOUT)
            if not self._burst_active:
                self._burst_active = True
                self._burst_sample_count = 0
                self._verification_bursts += 1
            if self._burst_sample_count >= self.policy.burst_max_eligible_samples:
                self._burst_active = False
                self._timed_out_until_visual_reset = True
                self._burst_timeouts += 1
                return self._decision(False, PageNumberRequestReason.BURST_TIMEOUT)
            self._burst_sample_count += 1
            return self._decision(True, PageNumberRequestReason.VISUAL_CHANGE_BURST)

        self._reset_burst()
        self._timed_out_until_visual_reset = False
        if self.policy.mode is PageNumberSchedulerMode.HYBRID_AUDITED:
            self._audit_counter += 1
            if self._audit_counter >= self.policy.audit_interval_eligible_samples:
                self._audit_counter = 0
                self._audit_requests += 1
                return self._decision(True, PageNumberRequestReason.PERIODIC_AUDIT)
        reason = (
            PageNumberRequestReason.VISUAL_SAME_SKIP
            if visual_match_kind
            in {IdentityMatchKind.EXACT_DUPLICATE, IdentityMatchKind.VISUAL_DUPLICATE}
            else PageNumberRequestReason.VISUAL_NOT_CHANGED_SKIP
        )
        return self._decision(False, reason)

    def _record_visual(
        self,
        match_kind: IdentityMatchKind | None,
        stable_count: int,
    ) -> None:
        if match_kind in {
            IdentityMatchKind.EXACT_DUPLICATE,
            IdentityMatchKind.VISUAL_DUPLICATE,
        }:
            self._visual_same += 1
        elif stable_count > 0 and match_kind in {
            IdentityMatchKind.NEW_SPREAD,
            IdentityMatchKind.AMBIGUOUS,
        }:
            self._visual_changed += 1
        elif match_kind is IdentityMatchKind.AMBIGUOUS:
            self._visual_ambiguous += 1
        elif match_kind is None:
            self._visual_error += 1
        else:
            self._visual_ambiguous += 1

    def _decision(
        self,
        requested: bool,
        reason: PageNumberRequestReason,
    ) -> PageNumberScheduleDecision:
        if requested:
            self._requested += 1
        else:
            self._skipped += 1
        return PageNumberScheduleDecision(
            requested,
            reason,
            self._burst_active,
            self._burst_sample_count,
            self._audit_counter,
        )

    def _reset_burst(self) -> None:
        self._burst_active = False
        self._burst_sample_count = 0
