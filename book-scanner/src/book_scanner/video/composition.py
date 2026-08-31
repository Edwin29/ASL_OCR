"""Explicit PC composition for the offline M1 Paddle recognizer.

The pure identity tracker never imports Paddle.  This boundary verifies that
the caller supplied a complete, hash-pinned local model before constructing
the optional recognition backend; it never downloads or switches models.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .config import OpaqueIdentityStrategy, VideoScannerConfig
from .page_number_provider import OpenCVBottomRoiPageNumberProvider
from .page_number_recognizer import PaddleRoiDigitRecognizer


_REQUIRED_PADDLE_ASSETS = frozenset(
    {"inference.json", "inference.pdiparams", "inference.yml"}
)


@dataclass(frozen=True, slots=True)
class PaddleOpaqueIdentityBackendConfig:
    model_dir: str | Path
    expected_file_hashes: Mapping[str, str]
    device: str | None = None
    allow_runtime_download: bool = False

    def __post_init__(self) -> None:
        root = Path(self.model_dir).resolve()
        hashes = dict(self.expected_file_hashes)
        if self.allow_runtime_download:
            raise ValueError("runtime model download is forbidden")
        if not _REQUIRED_PADDLE_ASSETS.issubset(hashes):
            raise ValueError("all required Paddle model assets must be hash-pinned")
        for name, digest in hashes.items():
            relative = Path(name)
            if not name.strip() or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("model asset names must remain inside model_dir")
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError("model asset hashes must be lowercase SHA-256")
        if self.device is not None and not self.device.strip():
            raise ValueError("device must be non-empty when provided")
        object.__setattr__(self, "model_dir", root)
        object.__setattr__(self, "expected_file_hashes", MappingProxyType(hashes))


def compose_m1_page_number_provider(
    scanner_config: VideoScannerConfig,
    backend: PaddleOpaqueIdentityBackendConfig | None,
) -> OpenCVBottomRoiPageNumberProvider | None:
    """Return the explicit M1 provider, or ``None`` for legacy rollback mode."""

    strategy = scanner_config.opaque_footer_identity.strategy
    if strategy is OpaqueIdentityStrategy.LEGACY_VISUAL:
        return None
    if backend is None:
        raise ValueError("M1 default requires an explicit hash-pinned Paddle backend")
    recognizer = PaddleRoiDigitRecognizer(
        backend.model_dir,
        scanner_config.page_number,
        expected_file_hashes=backend.expected_file_hashes,
        device=backend.device,
    )
    return OpenCVBottomRoiPageNumberProvider(scanner_config.page_number, recognizer)
