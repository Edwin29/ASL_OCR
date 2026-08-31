from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from book_scanner.video import composition
from book_scanner.video.composition import (
    PaddleOpaqueIdentityBackendConfig,
    compose_m1_page_number_provider,
)
from book_scanner.video.config import (
    OpaqueFooterIdentityPolicy,
    OpaqueIdentityStrategy,
    VideoScannerConfig,
)


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _backend(tmp_path: Path) -> PaddleOpaqueIdentityBackendConfig:
    hashes = {}
    for name in ("inference.json", "inference.pdiparams", "inference.yml"):
        content = name.encode("utf-8")
        (tmp_path / name).write_bytes(content)
        hashes[name] = _hash(content)
    return PaddleOpaqueIdentityBackendConfig(tmp_path, hashes, device="cpu")


def test_m1_composition_fails_before_backend_import_when_backend_is_missing() -> None:
    with pytest.raises(ValueError, match="explicit hash-pinned Paddle backend"):
        compose_m1_page_number_provider(VideoScannerConfig(), None)


def test_backend_requires_all_hash_pinned_assets_and_forbids_download(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="all required"):
        PaddleOpaqueIdentityBackendConfig(tmp_path, {"inference.json": "0" * 64})
    with pytest.raises(ValueError, match="download is forbidden"):
        PaddleOpaqueIdentityBackendConfig(
            tmp_path,
            {
                "inference.json": "0" * 64,
                "inference.pdiparams": "0" * 64,
                "inference.yml": "0" * 64,
            },
            allow_runtime_download=True,
        )


def test_composition_constructs_one_explicit_provider(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class FakeRecognizer:
        def __init__(self, model_dir, policy, *, expected_file_hashes, device):
            calls.append((model_dir, policy, dict(expected_file_hashes), device))

    monkeypatch.setattr(composition, "PaddleRoiDigitRecognizer", FakeRecognizer)
    provider = compose_m1_page_number_provider(VideoScannerConfig(), _backend(tmp_path))

    assert provider is not None
    assert len(calls) == 1
    assert calls[0][0] == tmp_path.resolve()
    assert set(calls[0][2]) == {"inference.json", "inference.pdiparams", "inference.yml"}


def test_explicit_legacy_rollback_does_not_require_or_construct_paddle(monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy rollback must not construct Paddle")

    monkeypatch.setattr(composition, "PaddleRoiDigitRecognizer", forbidden)
    config = VideoScannerConfig(
        opaque_footer_identity=OpaqueFooterIdentityPolicy(
            strategy=OpaqueIdentityStrategy.LEGACY_VISUAL
        )
    )
    assert compose_m1_page_number_provider(config, None) is None
