"""Concrete local-host factory for scan-session-scoped SampledFrameEngine instances."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from book_scanner.correct.uvdoc_adapter import UVDocConfig

from .artifacts import FilesystemArtifactStore
from .candidate import OpenCVCandidateAnalyzer
from .composition import PaddleOpaqueIdentityBackendConfig, compose_m1_page_number_provider
from .config import VideoScannerConfig
from .engine import SampledFrameEngine
from .sources import ImageSequenceCameraSource, OpenCVCameraSource, VideoFileCameraSource
from .spread_preparer import SeamUVDocPreparerConfig, SeamUVDocSpreadPreparer


@dataclass(frozen=True, slots=True)
class LocalScannerRuntimeConfig:
    profile: str
    staging_root: Path
    ready_root: Path
    uvdoc_runtime_path: Path
    uvdoc_checkpoint_path: Path
    uvdoc_device: str
    m1_model_dir: Path
    m1_model_manifest: Path
    replay_path: Path | None = None
    image_paths: tuple[Path, ...] = ()
    camera_index: int = 0
    camera_width: int | None = None
    camera_height: int | None = None
    camera_fps: float | None = None
    sample_interval_ms: int = 500


class LocalBookScannerEngineFactory:
    """Reuse heavy model adapters while creating a fresh engine and camera per scan."""

    def __init__(
        self,
        config: LocalScannerRuntimeConfig,
        *,
        scanner_config: VideoScannerConfig | None = None,
    ) -> None:
        self.config = config
        self.scanner_config = scanner_config or VideoScannerConfig()
        self._validate_assets()
        self._artifact_store = FilesystemArtifactStore(config.staging_root, config.ready_root)
        self._preparer = SeamUVDocSpreadPreparer(
            SeamUVDocPreparerConfig(config.staging_root),
            UVDocConfig(
                runtime_path=config.uvdoc_runtime_path,
                checkpoint_path=config.uvdoc_checkpoint_path,
                device=config.uvdoc_device,
            ),
        )
        self._page_number_provider = compose_m1_page_number_provider(
            self.scanner_config,
            PaddleOpaqueIdentityBackendConfig(
                model_dir=config.m1_model_dir,
                expected_file_hashes=_model_hashes(config.m1_model_manifest),
            ),
        )

    def create(self, *, session_id: str, datapack_id: str) -> SampledFrameEngine:
        camera = self._camera()
        config = self.scanner_config
        return SampledFrameEngine(
            camera,
            OpenCVCandidateAnalyzer(config.candidate),
            self._preparer,
            self._artifact_store,
            session_id=session_id,
            policy=config.candidate,
            identity_policy=config.identity,
            page_change_policy=config.page_change,
            page_number_policy=config.page_number,
            page_number_scheduler_policy=config.page_number_scheduler,
            page_number_provider=self._page_number_provider,
            opaque_identity_policy=config.opaque_footer_identity,
            data_pack_id=datapack_id,
        )

    def _camera(self):
        if self.config.profile == "replay":
            assert self.config.replay_path is not None
            return VideoFileCameraSource(
                self.config.replay_path,
                sample_interval_ms=self.config.sample_interval_ms,
            )
        if self.config.profile == "image_sequence":
            return ImageSequenceCameraSource(self.config.image_paths)
        if self.config.profile == "pc_camera":
            return OpenCVCameraSource(
                self.config.camera_index,
                width=self.config.camera_width,
                height=self.config.camera_height,
                fps=self.config.camera_fps,
            )
        raise ValueError(f"unsupported scanner profile: {self.config.profile}")

    def _validate_assets(self) -> None:
        if self.config.profile == "replay" and (
            self.config.replay_path is None or not self.config.replay_path.is_file()
        ):
            raise ValueError("configured Scanner replay file does not exist")
        if self.config.profile == "image_sequence" and (
            not self.config.image_paths or any(not path.is_file() for path in self.config.image_paths)
        ):
            raise ValueError("configured Scanner image sequence is incomplete")
        if not self.config.uvdoc_runtime_path.is_dir():
            raise ValueError("configured UVDoc runtime directory does not exist")
        if not self.config.uvdoc_checkpoint_path.is_file():
            raise ValueError("configured UVDoc checkpoint does not exist")
        if not self.config.m1_model_dir.is_dir():
            raise ValueError("configured M1 model directory does not exist")
        if not self.config.m1_model_manifest.is_file():
            raise ValueError("configured M1 model manifest does not exist")


def _model_hashes(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("M1 model manifest is not readable JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("M1 model manifest schema_version must be 1")
    if payload.get("runtime_download_allowed") is not False:
        raise ValueError("M1 model manifest must forbid runtime downloads")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("M1 model manifest files are missing")
    hashes: dict[str, str] = {}
    for name, digest in files.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            raise ValueError("M1 model manifest file hashes are invalid")
        hashes[name] = digest
    return hashes
