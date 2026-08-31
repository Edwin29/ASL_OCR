"""Conservative preview-only page-change hysteresis for V3-A."""

from __future__ import annotations

from dataclasses import dataclass

from .config import IdentityPolicy, PageChangePolicy
from .identity import (
    IdentityComparison,
    IdentityMatchKind,
    SpreadVisualFingerprint,
    compare_visual_spreads,
)


@dataclass(frozen=True, slots=True)
class PageChangeDecision:
    changed: bool
    stable_count: int
    comparison: IdentityComparison | None
    motion_seen: bool
    eligible: bool


class HysteresisPageChangeGate:
    """Require K stable, pair-wide changed previews before releasing capture."""

    def __init__(
        self,
        identity_policy: IdentityPolicy = IdentityPolicy(),
        policy: PageChangePolicy = PageChangePolicy(),
    ) -> None:
        self.identity_policy = identity_policy
        self.policy = policy
        self._baseline: SpreadVisualFingerprint | None = None
        self._candidate: SpreadVisualFingerprint | None = None
        self._stable_count = 0
        self._motion_seen = False
        self._latched = False

    def arm(self, baseline: SpreadVisualFingerprint) -> None:
        if baseline.algorithm_version != self.identity_policy.algorithm_version:
            raise ValueError("page-change baseline fingerprint version mismatch")
        self._baseline = baseline
        self._candidate = None
        self._stable_count = 0
        self._motion_seen = False
        self._latched = False

    def reset(self) -> None:
        self._baseline = None
        self._candidate = None
        self._stable_count = 0
        self._motion_seen = False
        self._latched = False

    def observe(
        self,
        fingerprint: SpreadVisualFingerprint | None,
        *,
        eligible: bool,
        motion_observed: bool = False,
    ) -> PageChangeDecision:
        if self._baseline is None:
            raise RuntimeError("page-change gate is not armed")
        if motion_observed:
            self._motion_seen = True
        if self._latched:
            return PageChangeDecision(False, self._stable_count, None, self._motion_seen, False)
        if not eligible or fingerprint is None:
            self._candidate = None
            self._stable_count = 0
            return PageChangeDecision(False, 0, None, self._motion_seen, False)

        baseline_comparison = compare_visual_spreads(
            fingerprint,
            self._baseline,
            self.identity_policy,
        )
        sufficiently_changed = baseline_comparison.kind is IdentityMatchKind.NEW_SPREAD or (
            baseline_comparison.kind is IdentityMatchKind.AMBIGUOUS
            and baseline_comparison.compatible
            and not baseline_comparison.left_agrees
            and not baseline_comparison.right_agrees
            and baseline_comparison.left_hamming is not None
            and baseline_comparison.right_hamming is not None
            and baseline_comparison.left_projection_mae is not None
            and baseline_comparison.right_projection_mae is not None
            and baseline_comparison.left_hamming >= self.policy.min_pair_hamming
            and baseline_comparison.right_hamming >= self.policy.min_pair_hamming
            and baseline_comparison.left_projection_mae >= self.policy.min_pair_projection_mae
            and baseline_comparison.right_projection_mae >= self.policy.min_pair_projection_mae
        )
        if not sufficiently_changed:
            self._candidate = None
            self._stable_count = 0
            return PageChangeDecision(
                False,
                0,
                baseline_comparison,
                self._motion_seen,
                True,
            )

        if self._candidate is None:
            self._candidate = fingerprint
            self._stable_count = 1
        else:
            consecutive = compare_visual_spreads(
                fingerprint,
                self._candidate,
                self.identity_policy,
            )
            if consecutive.kind is IdentityMatchKind.VISUAL_DUPLICATE:
                self._stable_count += 1
            else:
                self._candidate = fingerprint
                self._stable_count = 1

        changed = self._stable_count >= self.policy.stable_sample_count
        if changed:
            self._latched = True
        return PageChangeDecision(
            changed,
            self._stable_count,
            baseline_comparison,
            self._motion_seen,
            True,
        )
