"""Atomic promotion of private prepared directories into ready artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import cv2
import numpy as np

from .types import (
    PageArtifactRef,
    PreparedPageArtifact,
    PreparedSpreadArtifact,
    ProcessingJobId,
    SpreadArtifactRef,
)


class ArtifactStoreError(RuntimeError):
    pass


class ArtifactCollisionError(ArtifactStoreError):
    pass


class ArtifactCommitError(ArtifactStoreError):
    pass


class FilesystemArtifactStore:
    """Commit verified staging directories without overwriting ready data."""

    def __init__(self, staging_root: Path, final_root: Path):
        self.staging_root = Path(staging_root).resolve()
        self.final_root = Path(final_root).resolve()
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.final_root.mkdir(parents=True, exist_ok=True)
        if not _same_filesystem(self.staging_root, self.final_root):
            raise ArtifactCommitError("staging_root and final_root must be on the same filesystem")

    def commit(self, prepared: PreparedSpreadArtifact) -> SpreadArtifactRef:
        staging = Path(prepared.staging_path).resolve()
        _require_child(self.staging_root, staging, "staging_path")
        expected_staging = (self.staging_root / prepared.job_id.value).resolve()
        if staging != expected_staging:
            raise ArtifactCommitError(
                f"staging path must be owned by processing job {prepared.job_id}: {staging}"
            )
        _require_path_component(prepared.artifact_id.value, "artifact_id")
        final = (self.final_root / prepared.artifact_id.value).resolve()
        _require_child(self.final_root, final, "final artifact path")
        lock_path = self.final_root / f".{prepared.artifact_id.value}.commit.lock"
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ArtifactCommitError(
                f"artifact commit is already in progress: {prepared.artifact_id}"
            ) from exc
        try:
            if final.exists():
                return self._existing_or_collision(prepared, final)
            if not staging.is_dir():
                raise ArtifactCommitError(f"staging directory does not exist: {staging}")
            self._verify_prepared(prepared, staging)
            try:
                os.rename(staging, final)
            except FileExistsError:
                return self._existing_or_collision(prepared, final)
            except OSError as exc:
                raise ArtifactCommitError(f"atomic directory rename failed: {exc}") from exc
            return _artifact_ref(prepared, final)
        finally:
            os.close(lock_fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def discard(self, prepared: PreparedSpreadArtifact) -> None:
        staging = Path(prepared.staging_path).resolve()
        _require_child(self.staging_root, staging, "staging_path")
        expected_staging = (self.staging_root / prepared.job_id.value).resolve()
        if staging != expected_staging:
            raise ArtifactCommitError(
                f"staging path must be owned by processing job {prepared.job_id}: {staging}"
            )
        self.discard_job(prepared.job_id)

    def discard_job(self, job_id: ProcessingJobId) -> None:
        _require_path_component(job_id.value, "processing_job_id")
        staging = (self.staging_root / job_id.value).resolve()
        _require_child(self.staging_root, staging, "job staging path")
        if staging.exists():
            if not staging.is_dir():
                raise ArtifactCommitError(f"staging path is not a directory: {staging}")
            shutil.rmtree(staging)

    def _existing_or_collision(
        self,
        prepared: PreparedSpreadArtifact,
        final: Path,
    ) -> SpreadArtifactRef:
        if not final.is_dir():
            raise ArtifactCollisionError(f"final artifact path is not a directory: {final}")
        try:
            self._verify_prepared(prepared, final)
        except ArtifactCommitError as exc:
            raise ArtifactCollisionError(
                f"artifact ID already exists with different or corrupt content: {prepared.artifact_id}"
            ) from exc
        self.discard(prepared)
        return _artifact_ref(prepared, final)

    @staticmethod
    def _verify_prepared(prepared: PreparedSpreadArtifact, root: Path) -> None:
        expected = (
            (prepared.manifest_relative_path, prepared.manifest_sha256),
            (prepared.left.image_relative_path, prepared.left.sha256),
            (prepared.right.image_relative_path, prepared.right.sha256),
        )
        for relative, expected_hash in expected:
            path = _safe_relative(root, relative)
            if not path.is_file():
                raise ArtifactCommitError(f"prepared artifact file is missing: {path}")
            actual_hash = _sha256_file(path)
            if actual_hash != expected_hash:
                raise ArtifactCommitError(
                    f"prepared artifact hash mismatch for {relative}: {actual_hash} != {expected_hash}"
                )
        manifest_path = _safe_relative(root, prepared.manifest_relative_path)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ArtifactCommitError(f"manifest is not valid UTF-8 JSON: {manifest_path}") from exc
        expected_lineage = {
            "artifact_id": prepared.artifact_id.value,
            "session_id": prepared.session_id,
            "processing_job_id": prepared.job_id.value,
            "spread_id": prepared.spread_id.value,
            "source_frame_id": prepared.source_frame_id.value,
        }
        for key, expected_value in expected_lineage.items():
            if manifest.get(key) != expected_value:
                raise ArtifactCommitError(
                    f"manifest lineage mismatch for {key}: {manifest.get(key)!r} != {expected_value!r}"
                )
        files = manifest.get("files")
        if files is not None:
            if not isinstance(files, list) or not files:
                raise ArtifactCommitError("manifest files must be a non-empty list")
            listed_paths: set[str] = set()
            for record in files:
                if not isinstance(record, dict):
                    raise ArtifactCommitError("manifest file record must be an object")
                relative = record.get("path")
                expected_hash = record.get("sha256")
                if not isinstance(relative, str) or not isinstance(expected_hash, str):
                    raise ArtifactCommitError("manifest file record needs path and sha256")
                if relative in listed_paths:
                    raise ArtifactCommitError(f"manifest file path is duplicated: {relative}")
                listed_paths.add(relative)
                path = _safe_relative(root, relative)
                if not path.is_file() or _sha256_file(path) != expected_hash:
                    raise ArtifactCommitError(f"manifest file is missing or corrupt: {relative}")
                expected_size = record.get("size_bytes")
                if isinstance(expected_size, int) and path.stat().st_size != expected_size:
                    raise ArtifactCommitError(f"manifest file size mismatch: {relative}")
                if str(record.get("mime_type", "")).startswith("image/"):
                    decoded = cv2.imdecode(
                        np.fromfile(str(path), dtype=np.uint8),
                        cv2.IMREAD_UNCHANGED,
                    )
                    if decoded is None:
                        raise ArtifactCommitError(f"manifest image cannot be decoded: {relative}")
                    if (
                        record.get("width") != decoded.shape[1]
                        or record.get("height") != decoded.shape[0]
                    ):
                        raise ArtifactCommitError(f"manifest image dimensions mismatch: {relative}")
            required = {
                prepared.left.image_relative_path,
                prepared.right.image_relative_path,
            }
            if not required.issubset(listed_paths):
                raise ArtifactCommitError("manifest files omit a prepared page image")


def _artifact_ref(prepared: PreparedSpreadArtifact, root: Path) -> SpreadArtifactRef:
    return SpreadArtifactRef(
        artifact_id=prepared.artifact_id,
        spread_id=prepared.spread_id,
        source_frame_id=prepared.source_frame_id,
        left=_page_ref(prepared.left, root),
        right=_page_ref(prepared.right, root),
        manifest_path=str(_safe_relative(root, prepared.manifest_relative_path)),
        manifest_sha256=prepared.manifest_sha256,
        evaluator_version=prepared.evaluator_version,
    )


def _page_ref(page: PreparedPageArtifact, root: Path) -> PageArtifactRef:
    return PageArtifactRef(
        side=page.side,
        source_frame_id=page.source_frame_id,
        image_path=str(_safe_relative(root, page.image_relative_path)),
        sha256=page.sha256,
        width=page.width,
        height=page.height,
    )


def _safe_relative(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    _require_child(root, candidate, "artifact relative path")
    return candidate


def _require_child(root: Path, candidate: Path, name: str) -> None:
    if candidate == root or root not in candidate.parents:
        raise ArtifactCommitError(f"{name} must be a child of {root}: {candidate}")


def _require_path_component(value: str, name: str) -> None:
    path = Path(value)
    if path.is_absolute() or path.name != value or value in {".", ".."}:
        raise ArtifactCommitError(f"{name} must be one safe path component: {value!r}")


def _same_filesystem(left: Path, right: Path) -> bool:
    if os.name == "nt":
        return left.drive.casefold() == right.drive.casefold()
    return left.stat().st_dev == right.stat().st_dev


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
