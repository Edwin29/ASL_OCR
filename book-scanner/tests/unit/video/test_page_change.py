from __future__ import annotations

import cv2
import numpy as np

from book_scanner.video.config import IdentityPolicy, PageChangePolicy
from book_scanner.video.identity import OpenCVIdentityFingerprinter
from book_scanner.video.page_change import HysteresisPageChangeGate


def _preview(seed_left: int, seed_right: int):
    gray = np.full((240, 320), 230, dtype=np.uint8)
    for side, seed in ((0, seed_left), (1, seed_right)):
        x0 = side * 160
        rng = np.random.default_rng(seed)
        for row in range(8):
            y = 25 + row * 24
            length = int(rng.integers(55, 125))
            cv2.line(gray, (x0 + 18, y), (x0 + 18 + length, y), 20, 2)
        cv2.putText(gray, str(seed), (x0 + 60, 225), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 3)
    mask = np.full_like(gray, 255)
    return OpenCVIdentityFingerprinter().fingerprint_preview(gray, mask, 0.5)


def test_same_page_never_releases_gate() -> None:
    gate = HysteresisPageChangeGate(policy=PageChangePolicy(stable_sample_count=3))
    baseline = _preview(1, 2)
    gate.arm(baseline)

    decisions = [gate.observe(baseline, eligible=True) for _ in range(5)]

    assert not any(item.changed for item in decisions)
    assert all(item.stable_count == 0 for item in decisions)


def test_new_stable_pair_releases_once_without_motion_evidence() -> None:
    gate = HysteresisPageChangeGate(policy=PageChangePolicy(stable_sample_count=3))
    gate.arm(_preview(1, 2))
    changed = _preview(40, 50)

    decisions = [gate.observe(changed, eligible=True) for _ in range(4)]

    assert [item.changed for item in decisions] == [False, False, True, False]
    assert decisions[2].stable_count == 3
    assert decisions[2].motion_seen is False


def test_motion_or_obstruction_sample_is_not_stable_change_evidence() -> None:
    gate = HysteresisPageChangeGate(policy=PageChangePolicy(stable_sample_count=3))
    gate.arm(_preview(1, 2))
    changed = _preview(40, 50)

    first = gate.observe(changed, eligible=True)
    blocked = gate.observe(None, eligible=False, motion_observed=True)
    after = gate.observe(changed, eligible=True)

    assert first.stable_count == 1
    assert blocked.stable_count == 0
    assert after.stable_count == 1
    assert after.motion_seen is True


def test_one_frame_change_spike_does_not_release_gate() -> None:
    identity_policy = IdentityPolicy()
    gate = HysteresisPageChangeGate(identity_policy, PageChangePolicy(stable_sample_count=3))
    baseline = _preview(1, 2)
    gate.arm(baseline)

    spike = gate.observe(_preview(40, 50), eligible=True)
    settled = gate.observe(baseline, eligible=True)

    assert spike.changed is False and spike.stable_count == 1
    assert settled.changed is False and settled.stable_count == 0
