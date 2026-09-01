from __future__ import annotations

from pathlib import Path

import pytest

from book_scanner.video.config import VideoScannerConfig
from book_scanner.video.runtime_composition import (
    LocalScannerRuntimeConfig,
    _effective_scanner_config,
)


def _runtime(
    *,
    profile: str = "replay",
    timeout: int | None = None,
) -> LocalScannerRuntimeConfig:
    return LocalScannerRuntimeConfig(
        profile=profile,
        staging_root=Path("staging"),
        ready_root=Path("ready"),
        uvdoc_runtime_path=Path("uvdoc"),
        uvdoc_checkpoint_path=Path("uvdoc.pth"),
        uvdoc_device="cpu",
        m1_model_dir=Path("paddle"),
        m1_model_manifest=Path("paddle.json"),
        replay_path=Path("replay.mp4") if profile == "replay" else None,
        opaque_identity_max_collection_ms=timeout,
    )


def test_runtime_keeps_default_opaque_identity_policy_without_override() -> None:
    original = VideoScannerConfig()

    effective = _effective_scanner_config(_runtime(), original)

    assert effective is original
    assert effective.opaque_footer_identity.max_collection_ms == 1500
    assert effective.opaque_footer_identity.query_sample_count == 5
    assert effective.opaque_footer_identity.reference_bank_size == 5


def test_runtime_replaces_only_replay_collection_timeout() -> None:
    original = VideoScannerConfig()

    effective = _effective_scanner_config(_runtime(timeout=30_000), original)

    assert effective is not original
    assert effective.candidate == original.candidate
    assert effective.identity == original.identity
    assert effective.opaque_footer_identity.max_collection_ms == 30_000
    assert effective.opaque_footer_identity.query_sample_count == 5
    assert effective.opaque_footer_identity.reference_bank_size == 5
    assert effective.opaque_footer_identity.k_same == 1
    assert effective.opaque_footer_identity.k_different == 0


@pytest.mark.parametrize("timeout", [True, 0, -1, 60_001])
def test_runtime_rejects_invalid_replay_collection_timeout(timeout: int) -> None:
    with pytest.raises(ValueError, match="opaque_identity_max_collection_ms"):
        _effective_scanner_config(_runtime(timeout=timeout))


def test_runtime_rejects_replay_override_for_physical_profile() -> None:
    with pytest.raises(ValueError, match="allowed only for replay"):
        _effective_scanner_config(_runtime(profile="pc_camera", timeout=30_000))
