"""Stabilize and rate-limit physical Scanner guidance."""

from __future__ import annotations

from dataclasses import dataclass

from .config import GuidancePolicy
from .types import ReadinessReason


@dataclass(frozen=True, slots=True)
class GuidanceDecision:
    reason: ReadinessReason
    stable_for_samples: int
    stable_for_ms: int


class GuidanceArbiter:
    """Emit only stable reasons and cool down repeated guidance.

    Scanner observations remain available as diagnostics on every sampled frame;
    this gate only controls user-facing ``guidance_requested`` events.
    """

    def __init__(self, policy: GuidancePolicy = GuidancePolicy()) -> None:
        self.policy = policy
        self._candidate_reason: ReadinessReason | None = None
        self._candidate_since: float | None = None
        self._candidate_samples = 0
        self._last_emitted_reason: ReadinessReason | None = None
        self._last_emitted_at: float | None = None

    def reset(self, *, clear_history: bool = True) -> None:
        self._candidate_reason = None
        self._candidate_since = None
        self._candidate_samples = 0
        if clear_history:
            self._last_emitted_reason = None
            self._last_emitted_at = None

    def observe(
        self,
        reason: ReadinessReason | None,
        observed_at_monotonic: float,
    ) -> GuidanceDecision | None:
        if reason is None:
            self.reset(clear_history=False)
            return None
        if reason is not self._candidate_reason:
            self._candidate_reason = reason
            self._candidate_since = observed_at_monotonic
            self._candidate_samples = 1
        else:
            self._candidate_samples += 1

        assert self._candidate_since is not None
        stable_for_ms = max(
            0,
            round((observed_at_monotonic - self._candidate_since) * 1000),
        )
        if (
            self._candidate_samples < self.policy.reason_hold_samples
            or stable_for_ms < self.policy.reason_hold_ms
        ):
            return None
        if (
            reason is self._last_emitted_reason
            and self._last_emitted_at is not None
            and round((observed_at_monotonic - self._last_emitted_at) * 1000)
            < self.policy.repeat_cooldown_ms
        ):
            return None

        self._last_emitted_reason = reason
        self._last_emitted_at = observed_at_monotonic
        return GuidanceDecision(reason, self._candidate_samples, stable_for_ms)
