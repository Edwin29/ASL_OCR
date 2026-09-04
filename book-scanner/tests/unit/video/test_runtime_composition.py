from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from book_scanner.video.config import VideoScannerConfig
from book_scanner.video.runtime_composition import (
    LocalBookScannerEngineFactory,
    LocalScannerRuntimeConfig,
    _effective_scanner_config,
)
from book_scanner.video.camera_host import AndroidUvcCameraSource
from book_scanner.video.operator_preview import ThreadedPreviewCameraSource
from book_scanner.video.sources import HttpSnapshotCameraSource


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


def test_runtime_applies_collection_timeout_to_physical_profile() -> None:
    effective = _effective_scanner_config(
        _runtime(profile="pc_camera", timeout=8_000)
    )

    assert effective.opaque_footer_identity.max_collection_ms == 8_000
    assert effective.opaque_footer_identity.query_sample_count == 5


def test_runtime_composes_android_uvc_source_without_replay_authority() -> None:
    runtime = LocalScannerRuntimeConfig(
        profile="android_uvc",
        staging_root=Path("staging"),
        ready_root=Path("ready"),
        uvdoc_runtime_path=Path("uvdoc"),
        uvdoc_checkpoint_path=Path("uvdoc.pth"),
        uvdoc_device="cpu",
        m1_model_dir=Path("paddle"),
        m1_model_manifest=Path("paddle.json"),
        camera_selector="Android Webcam",
        camera_backend="dshow",
        camera_fallback_index=1,
        camera_width=3840,
        camera_height=2160,
        camera_fps=30.0,
        camera_fourcc="MJPG",
        camera_rotation=90,
        camera_mirror=True,
        camera_crop_normalized=(0.0, 0.25, 1.0, 0.75),
    )
    factory = object.__new__(LocalBookScannerEngineFactory)
    factory.config = runtime

    source = factory._camera()

    assert isinstance(source, AndroidUvcCameraSource)
    assert source.selector == "Android Webcam"
    assert source.fallback_index == 1
    assert source.rotation == 90
    assert source.mirror
    assert source.crop_normalized == (0.0, 0.25, 1.0, 0.75)


def test_runtime_wraps_physical_camera_only_when_operator_preview_is_enabled() -> None:
    runtime = replace(
        _runtime(profile="pc_camera"),
        operator_preview_enabled=True,
        camera_backend="msmf",
        camera_fourcc="MJPG",
        camera_rotation=90,
        camera_mirror=True,
        camera_crop_normalized=(0.0, 0.25, 1.0, 0.75),
        camera_warmup_frames=5,
        camera_reopen_attempts=2,
    )
    factory = object.__new__(LocalBookScannerEngineFactory)
    factory.config = runtime

    source = factory._camera()

    assert isinstance(source, ThreadedPreviewCameraSource)
    assert source.source.drain_grabs == 0
    assert source.source.backend_api == cv2.CAP_MSMF
    assert source.source.fourcc == "MJPG"
    assert source.source.rotation == 90
    assert source.source.mirror
    assert source.source.crop_normalized == (0.0, 0.25, 1.0, 0.75)
    assert source.source.warmup_frames == 5
    assert source.source.reopen_attempts == 2
    assert "pc_camera:msmf:0" in source.preview.window_name


def test_runtime_composes_android_ip_snapshot_source() -> None:
    runtime = replace(
        _runtime(profile="android_ip_camera"),
        camera_snapshot_url="https://192.168.42.129:4444/video/snapshot?camera=back",
        camera_snapshot_username="scanner",
        camera_snapshot_password_file=Path("phone-password.txt"),
        camera_snapshot_allow_insecure_tls=True,
        camera_snapshot_min_width=3000,
        camera_snapshot_min_height=2000,
        camera_rotation=180,
        camera_snapshot_landscape_rotation=180,
        camera_snapshot_portrait_rotation=270,
    )
    factory = object.__new__(LocalBookScannerEngineFactory)
    factory.config = runtime

    source = factory._camera()

    assert isinstance(source, HttpSnapshotCameraSource)
    assert source.url.endswith("camera=back")
    assert source.username == "scanner"
    assert source.allow_insecure_tls
    assert source.min_width == 3000
    assert source.rotation == 180
    assert source.landscape_rotation == 180
    assert source.portrait_rotation == 270
