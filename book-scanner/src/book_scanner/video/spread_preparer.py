"""V2 seam-conservative + UVDoc preparation of an immutable spread bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Mapping

import cv2
import numpy as np

from book_scanner.correct.unwarper import PageUnwarper, UnwarpFailureReason, UnwarpResult
from book_scanner.correct.uvdoc_adapter import UVDocAdapter, UVDocConfig
from book_scanner.detect.spread_extraction import (
    ExtractedPage,
    SeamConservativeSpreadExtractor,
    SpreadExtractionConfig,
    SpreadExtractionResult,
    SpreadExtractor,
)

from .protocols import FrameSample
from .types import (
    ArtifactId,
    PageSide,
    PreparationDecision,
    PreparationState,
    PreparedPageArtifact,
    PreparedSpreadArtifact,
    ProcessingJobId,
    ReadinessReason,
    SpreadId,
)

V2_BUNDLE_SCHEMA_VERSION = "2.0"


@dataclass(frozen=True)
class SeamUVDocPreparerConfig:
    staging_root: Path
    extraction: SpreadExtractionConfig = field(default_factory=SpreadExtractionConfig)
    evaluator_version: str = "seam-uvdoc-artifact-v2"
    pipeline_version: str = "seam-conservative+uvdoc-bilinear-v2"
    jpeg_quality: int = 95
    min_page_width_px: int = 256
    min_page_height_px: int = 256
    min_aspect_ratio: float = 0.25
    max_aspect_ratio: float = 2.0
    reject_outer_frame_contacts: bool = False

    def __post_init__(self) -> None:
        if not str(self.evaluator_version).strip() or not str(self.pipeline_version).strip():
            raise ValueError("pipeline/evaluator versions must be non-empty")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be in [1, 100]")
        if self.min_page_width_px < 1 or self.min_page_height_px < 1:
            raise ValueError("minimum page dimensions must be positive")
        if not 0 < self.min_aspect_ratio < self.max_aspect_ratio:
            raise ValueError("aspect ratio bounds must be positive and ordered")


class SeamUVDocSpreadPreparer:
    """Prepare both page images or return no publishable artifact at all.

    One instance owns one lazy UVDoc adapter, so both pages and subsequent
    frames reuse the loaded checkpoint.  A failed side never falls back to an
    uncorrected image.
    """

    def __init__(
        self,
        config: SeamUVDocPreparerConfig,
        uvdoc_config: UVDocConfig | None = None,
        *,
        extractor: SpreadExtractor | None = None,
        unwarper: PageUnwarper | None = None,
    ):
        if (uvdoc_config is None) == (unwarper is None):
            raise ValueError("supply exactly one of uvdoc_config or unwarper")
        self.config = config
        self.staging_root = Path(config.staging_root).resolve()
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.extractor = extractor or SeamConservativeSpreadExtractor(config.extraction)
        self.unwarper = unwarper or UVDocAdapter(uvdoc_config)  # type: ignore[arg-type]
        self._runtime_metadata = _unwarper_runtime_metadata(self.unwarper)

    def prepare(
        self,
        frame: FrameSample[np.ndarray],
        spread_id: SpreadId,
        job_id: ProcessingJobId,
        session_id: str,
    ) -> PreparationDecision:
        started = time.perf_counter()
        if not str(session_id).strip():
            raise ValueError("session_id must be non-empty")
        if not _safe_component(job_id.value):
            return self._decision(
                PreparationState.FATAL,
                frame,
                spread_id,
                job_id,
                ReadinessReason.ARTIFACT_COLLISION,
                started,
                {"failure_stage": "staging", "message": "unsafe processing job ID"},
            )

        staging = (self.staging_root / job_id.value).resolve()
        if staging.parent != self.staging_root or staging.exists():
            return self._decision(
                PreparationState.FATAL,
                frame,
                spread_id,
                job_id,
                ReadinessReason.ARTIFACT_COLLISION,
                started,
                {"failure_stage": "staging", "message": "job staging path already exists"},
            )

        try:
            extraction = self.extractor.extract(frame.payload)
        except Exception as exc:
            return self._decision(
                PreparationState.RETRY_LOCAL,
                frame,
                spread_id,
                job_id,
                ReadinessReason.SEAM_FAILED,
                started,
                {"failure_stage": "extraction", "message": f"{type(exc).__name__}: {exc}"},
            )
        if not extraction.success or extraction.left is None or extraction.right is None:
            reason = _extraction_reason(extraction.reason)
            return self._decision(
                PreparationState.RETRY_LOCAL,
                frame,
                spread_id,
                job_id,
                reason,
                started,
                {
                    "failure_stage": "extraction",
                    "extraction_reason": extraction.reason,
                },
            )

        left_result = self.unwarper.unwarp(extraction.left.crop)
        if not _valid_unwarp(left_result):
            return self._unwarp_failure(
                frame, spread_id, job_id, started, PageSide.LEFT, left_result
            )
        right_result = self.unwarper.unwarp(extraction.right.crop)
        if not _valid_unwarp(right_result):
            return self._unwarp_failure(
                frame, spread_id, job_id, started, PageSide.RIGHT, right_result
            )

        assert left_result.image is not None and right_result.image is not None
        readiness = {
            PageSide.LEFT: self._page_readiness(extraction.left, left_result.image),
            PageSide.RIGHT: self._page_readiness(extraction.right, right_result.image),
        }
        hard_reasons = tuple(
            reason
            for side in (PageSide.LEFT, PageSide.RIGHT)
            for reason in readiness[side]["reasons"]
        )
        if hard_reasons:
            return self._decision(
                PreparationState.RETRY_LOCAL,
                frame,
                spread_id,
                job_id,
                hard_reasons[0],
                started,
                {
                    "failure_stage": "local_readiness",
                    "left_ready": not readiness[PageSide.LEFT]["reasons"],
                    "right_ready": not readiness[PageSide.RIGHT]["reasons"],
                },
            )

        try:
            staging.mkdir(parents=False, exist_ok=False)
            prepared = self._write_bundle(
                staging,
                frame,
                spread_id,
                job_id,
                session_id,
                extraction,
                {PageSide.LEFT: left_result, PageSide.RIGHT: right_result},
                readiness,
            )
        except FileExistsError:
            return self._decision(
                PreparationState.FATAL,
                frame,
                spread_id,
                job_id,
                ReadinessReason.ARTIFACT_COLLISION,
                started,
                {"failure_stage": "staging", "message": "job staging path raced"},
            )
        except Exception as exc:
            _remove_staging(staging)
            return self._decision(
                PreparationState.FATAL,
                frame,
                spread_id,
                job_id,
                ReadinessReason.ARTIFACT_COMMIT_FAILED,
                started,
                {"failure_stage": "bundle_write", "message": f"{type(exc).__name__}: {exc}"},
            )

        return PreparationDecision(
            state=PreparationState.PREPARED,
            evaluator_version=self.config.evaluator_version,
            job_id=job_id,
            source_frame_id=frame.frame_id,
            spread_id=spread_id,
            prepared=prepared,
            metrics={
                "processing_ms": round((time.perf_counter() - started) * 1000.0, 3),
                "seam_confidence": extraction.seam.confidence if extraction.seam else None,
                "uvdoc_load_count": _unwarper_load_count(self.unwarper),
                "left_uvdoc_ms": round(left_result.processing_ms, 3),
                "right_uvdoc_ms": round(right_result.processing_ms, 3),
            },
        )

    def _unwarp_failure(
        self,
        frame: FrameSample[np.ndarray],
        spread_id: SpreadId,
        job_id: ProcessingJobId,
        started: float,
        side: PageSide,
        result: UnwarpResult,
    ) -> PreparationDecision:
        state, reason = _map_unwarp_failure(result.reason)
        return self._decision(
            state,
            frame,
            spread_id,
            job_id,
            reason,
            started,
            {
                "failure_stage": "uvdoc",
                "failed_side": side.value,
                "uvdoc_reason": result.reason.value if result.reason else "invalid_success_contract",
                "uvdoc_device": result.device,
                "uvdoc_processing_ms": round(result.processing_ms, 3),
            },
        )

    def _decision(
        self,
        state: PreparationState,
        frame: FrameSample[np.ndarray],
        spread_id: SpreadId,
        job_id: ProcessingJobId,
        reason: ReadinessReason,
        started: float,
        metrics: Mapping[str, object],
    ) -> PreparationDecision:
        scalar_metrics = {
            key: value
            for key, value in metrics.items()
            if value is None or isinstance(value, (str, int, float, bool))
        }
        scalar_metrics["processing_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return PreparationDecision(
            state=state,
            evaluator_version=self.config.evaluator_version,
            job_id=job_id,
            source_frame_id=frame.frame_id,
            spread_id=spread_id,
            reasons=(reason,),
            metrics=scalar_metrics,
        )

    def _page_readiness(self, page: ExtractedPage, uvdoc_image: np.ndarray) -> dict[str, object]:
        height, width = uvdoc_image.shape[:2]
        aspect = width / max(1, height)
        reasons: list[ReadinessReason] = []
        if width < self.config.min_page_width_px or height < self.config.min_page_height_px:
            reasons.append(ReadinessReason.INSUFFICIENT_RESOLUTION)
        if not self.config.min_aspect_ratio <= aspect <= self.config.max_aspect_ratio:
            reasons.append(ReadinessReason.WARP_ARTIFACT)
        outer_contacts = [
            key for key in ("top", "bottom", "outer") if page.edge_contacts.get(key, False)
        ]
        if outer_contacts and self.config.reject_outer_frame_contacts:
            reasons.append(ReadinessReason.OUT_OF_FRAME)
        return {
            "ready": not reasons,
            "reasons": tuple(reasons),
            "uvdoc_size": [width, height],
            "aspect_ratio": aspect,
            "outer_frame_contact_warnings": outer_contacts,
            "outer_contacts_are_hard_gate": self.config.reject_outer_frame_contacts,
        }

    def _write_bundle(
        self,
        staging: Path,
        frame: FrameSample[np.ndarray],
        spread_id: SpreadId,
        job_id: ProcessingJobId,
        session_id: str,
        extraction: SpreadExtractionResult,
        unwarps: Mapping[PageSide, UnwarpResult],
        readiness: Mapping[PageSide, Mapping[str, object]],
    ) -> PreparedSpreadArtifact:
        files: list[dict[str, object]] = []
        source_record = _write_image(
            staging, "source_frame.jpg", frame.payload, ".jpg", self.config.jpeg_quality
        )
        files.append(source_record)
        page_records: dict[str, dict[str, object]] = {}
        prepared_pages: dict[PageSide, PreparedPageArtifact] = {}
        for side, extracted in (
            (PageSide.LEFT, extraction.left),
            (PageSide.RIGHT, extraction.right),
        ):
            assert extracted is not None
            unwarp = unwarps[side]
            assert unwarp.image is not None
            directory = staging / side.value
            directory.mkdir()
            mask_record = _write_image(staging, f"{side.value}/mask.png", extracted.crop_mask, ".png")
            crop_record = _write_image(
                staging,
                f"{side.value}/crop.jpg",
                extracted.crop,
                ".jpg",
                self.config.jpeg_quality,
            )
            uvdoc_record = _write_image(
                staging,
                f"{side.value}/uvdoc.jpg",
                unwarp.image,
                ".jpg",
                self.config.jpeg_quality,
            )
            side_diagnostics = {
                "side": side.value,
                "bbox_full": list(extracted.bbox_full),
                "padding_px": list(extracted.padding_px),
                "detector_bbox_full": list(extracted.detector_bbox_full),
                "detector_confidence": extracted.detector_confidence,
                "edge_contacts": dict(extracted.edge_contacts),
                "extraction": dict(extracted.diagnostics),
                "uvdoc": _unwarp_result_payload(unwarp),
                "local_readiness": readiness[side],
            }
            diagnostics_record = _write_json(
                staging, f"{side.value}/diagnostics.json", side_diagnostics
            )
            files.extend((mask_record, crop_record, uvdoc_record, diagnostics_record))
            page_records[side.value] = {
                **side_diagnostics,
                "files": {
                    "mask": mask_record,
                    "crop": crop_record,
                    "uvdoc": uvdoc_record,
                    "diagnostics": diagnostics_record,
                },
            }
            prepared_pages[side] = PreparedPageArtifact(
                side=side,
                source_frame_id=frame.frame_id,
                image_relative_path=str(uvdoc_record["path"]),
                sha256=str(uvdoc_record["sha256"]),
                width=int(uvdoc_record["width"]),
                height=int(uvdoc_record["height"]),
            )

        artifact_id = ArtifactId(_artifact_id(session_id, spread_id, frame.frame_id.value))
        prepared_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "schema_version": V2_BUNDLE_SCHEMA_VERSION,
            "artifact_id": artifact_id.value,
            "session_id": session_id,
            "processing_job_id": job_id.value,
            "spread_id": spread_id.value,
            "source_frame_id": frame.frame_id.value,
            "captured_at_monotonic": frame.captured_at_monotonic,
            "prepared_at_utc": prepared_at,
            "atomic_commit": {
                "eligible_at_utc": prepared_at,
                "operation": "same-filesystem directory rename",
                "exact_rename_timestamp_recorded": False,
                "note": "The immutable manifest is frozen before atomic promotion.",
            },
            "pipeline": {
                "version": self.config.pipeline_version,
                "evaluator_version": self.config.evaluator_version,
                "extractor": self.extractor.name,
                "extraction_config": self.config.extraction,
                "sampling_mode": self._runtime_metadata.get("sampling_mode", "unknown"),
                "silent_uncorrected_fallback": False,
            },
            "source": source_record,
            "seam": {
                "method": extraction.seam.method if extraction.seam else None,
                "confidence": extraction.seam.confidence if extraction.seam else None,
                "fallback_used": extraction.seam.fallback_used if extraction.seam else None,
                "uncertainty_band_px": extraction.seam.uncertainty_band_px if extraction.seam else None,
                "points_full": extraction.seam.points_full if extraction.seam else (),
                "diagnostics": extraction.seam.diagnostics if extraction.seam else {},
            },
            "ownership": extraction.ownership_diagnostics or {},
            "extraction_diagnostics": extraction.diagnostics,
            "uvdoc_runtime": {
                **self._runtime_metadata,
                "load_count": _unwarper_load_count(self.unwarper),
            },
            "pages": page_records,
            "files": files,
            "local_readiness": {
                "ready": True,
                "requires_both_pages": True,
                "left": readiness[PageSide.LEFT],
                "right": readiness[PageSide.RIGHT],
            },
        }
        manifest_record = _write_json(staging, "manifest.json", manifest)
        return PreparedSpreadArtifact(
            artifact_id=artifact_id,
            session_id=session_id,
            job_id=job_id,
            spread_id=spread_id,
            source_frame_id=frame.frame_id,
            staging_path=str(staging),
            manifest_relative_path="manifest.json",
            manifest_sha256=str(manifest_record["sha256"]),
            left=prepared_pages[PageSide.LEFT],
            right=prepared_pages[PageSide.RIGHT],
            evaluator_version=self.config.evaluator_version,
        )


def _extraction_reason(reason: str | None) -> ReadinessReason:
    if reason in {"INVALID_FRAME"}:
        return ReadinessReason.FRAME_DECODE_FAILED
    if reason in {"PAGE_NOT_FOUND", "NO_PAGE"}:
        return ReadinessReason.PAGE_NOT_FOUND
    return ReadinessReason.SEAM_FAILED


def _map_unwarp_failure(
    reason: UnwarpFailureReason | None,
) -> tuple[PreparationState, ReadinessReason]:
    if reason in {UnwarpFailureReason.MODEL_NOT_FOUND, UnwarpFailureReason.MODEL_LOAD_FAILED}:
        return PreparationState.FATAL, ReadinessReason.UVDOC_CONFIGURATION_FAILED
    if reason is UnwarpFailureReason.INVALID_OUTPUT:
        return PreparationState.RETRY_LOCAL, ReadinessReason.UVDOC_INVALID_OUTPUT
    return PreparationState.RETRY_LOCAL, ReadinessReason.UVDOC_FAILED


def _valid_unwarp(result: UnwarpResult) -> bool:
    return bool(
        result.success
        and isinstance(result.image, np.ndarray)
        and result.image.ndim == 3
        and result.image.shape[2] == 3
        and result.image.dtype == np.uint8
        and result.image.size > 0
        and result.reason is None
    )


def _unwarp_result_payload(result: UnwarpResult) -> dict[str, object]:
    return {
        "success": result.success,
        "adapter_name": result.adapter_name,
        "device": result.device,
        "processing_ms": result.processing_ms,
        "input_size": list(result.input_size),
        "output_size": list(result.output_size) if result.output_size else None,
        "reason": result.reason.value if result.reason else None,
        "diagnostics": dict(result.diagnostics),
    }


def _unwarper_runtime_metadata(unwarper: PageUnwarper) -> dict[str, object]:
    config = getattr(unwarper, "config", None)
    runtime = Path(config.runtime_path).resolve() if config is not None and hasattr(config, "runtime_path") else None
    checkpoint = Path(config.checkpoint_path).resolve() if config is not None and hasattr(config, "checkpoint_path") else None
    model_path = runtime / "model.py" if runtime is not None else None
    return {
        "adapter": getattr(unwarper, "name", type(unwarper).__name__),
        "runtime_path": str(runtime) if runtime is not None else None,
        "runtime_model_sha256": _sha256_file(model_path) if model_path and model_path.is_file() else None,
        "checkpoint_path": str(checkpoint) if checkpoint is not None else None,
        "checkpoint_sha256": _sha256_file(checkpoint) if checkpoint and checkpoint.is_file() else None,
        "configured_device": getattr(config, "device", None),
        "sampling_mode": getattr(config, "sampling_mode", None),
        "model_input_size": list(getattr(config, "model_input_size", ())) if config is not None else None,
    }


def _unwarper_load_count(unwarper: PageUnwarper) -> int | None:
    value = getattr(unwarper, "load_count", None)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _write_image(
    root: Path,
    relative: str,
    image: np.ndarray,
    extension: str,
    jpeg_quality: int = 95,
) -> dict[str, object]:
    if not isinstance(image, np.ndarray) or image.size == 0 or image.dtype != np.uint8:
        raise ValueError(f"cannot encode invalid image: {relative}")
    params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality] if extension == ".jpg" else []
    success, encoded = cv2.imencode(extension, image, params)
    if not success:
        raise OSError(f"OpenCV failed to encode {relative}")
    payload = encoded.tobytes()
    mode = cv2.IMREAD_GRAYSCALE if image.ndim == 2 else cv2.IMREAD_COLOR
    decoded = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), mode)
    if decoded is None or decoded.shape[:2] != image.shape[:2]:
        raise OSError(f"encoded image did not decode with matching dimensions: {relative}")
    path = _safe_relative(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    height, width = image.shape[:2]
    return {
        "path": relative.replace("\\", "/"),
        "sha256": _sha256_bytes(payload),
        "size_bytes": len(payload),
        "width": int(width),
        "height": int(height),
        "mime_type": "image/jpeg" if extension == ".jpg" else "image/png",
    }


def _write_json(root: Path, relative: str, payload: Mapping[str, object]) -> dict[str, object]:
    content = (
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path = _safe_relative(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "path": relative.replace("\\", "/"),
        "sha256": _sha256_bytes(content),
        "size_bytes": len(content),
        "mime_type": "application/json",
    }


def _safe_relative(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if root != path.parent and root not in path.parents:
        raise ValueError(f"artifact path escapes staging root: {relative}")
    return path


def _safe_component(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and path.name == value and value not in {".", ".."}


def _artifact_id(session_id: str, spread_id: SpreadId, frame_id: str) -> str:
    digest = hashlib.sha256(
        f"{session_id}\0{spread_id.value}\0{frame_id}".encode("utf-8")
    ).hexdigest()[:32]
    return f"spread-{digest}"


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_staging(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    raise TypeError(f"value is not JSON serializable: {type(value).__name__}")
