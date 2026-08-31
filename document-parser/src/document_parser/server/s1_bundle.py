"""Validation of server-owned Scanner V2 spread bundles."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from document_parser.server.s0_domain import S0ConflictError, S0ValidationError
from document_parser.server.s1_domain import S1Config, VerifiedSpreadInput


@dataclass(frozen=True, slots=True)
class ValidatedPage:
    side: str
    image_relative_path: str
    image_sha256: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ValidatedBundle:
    root: Path
    relative_root: str
    manifest: dict[str, Any]
    left: ValidatedPage
    right: ValidatedPage


class ScannerBundleValidator:
    def __init__(self, config: S1Config) -> None:
        self.config = config
        self.config.received_root.mkdir(parents=True, exist_ok=True)

    def validate(self, spread: VerifiedSpreadInput) -> ValidatedBundle:
        relative = _safe_relative_value(spread.bundle_storage_key)
        root = (self.config.received_root / relative).resolve()
        received_root = self.config.received_root.resolve()
        if root != received_root and received_root not in root.parents:
            raise S0ValidationError("BUNDLE_PATH_INVALID", "bundle key escapes receive root")
        if not root.is_dir() or root.is_symlink():
            raise S0ValidationError("BUNDLE_NOT_FOUND", "server-owned bundle directory is missing")
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise S0ValidationError("BUNDLE_MANIFEST_MISSING", "bundle manifest.json is missing")
        if _sha256_file(manifest_path) != spread.manifest_sha256:
            raise S0ConflictError("BUNDLE_MANIFEST_HASH_MISMATCH", "bundle manifest hash differs")
        if manifest_path.stat().st_size > 4 * 1024 * 1024:
            raise S0ValidationError("BUNDLE_MANIFEST_TOO_LARGE", "bundle manifest exceeds 4 MiB")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise S0ValidationError("BUNDLE_MANIFEST_INVALID", "bundle manifest is not valid JSON") from exc
        if not isinstance(manifest, dict) or manifest.get("schema_version") != "2.0":
            raise S0ValidationError("BUNDLE_SCHEMA_UNSUPPORTED", "Scanner bundle schema must be 2.0")
        expected = {
            "artifact_id": spread.artifact_id,
            "session_id": spread.scan_session_id,
            "spread_id": spread.spread_id,
            "source_frame_id": spread.source_frame_id,
        }
        for field, value in expected.items():
            if manifest.get(field) != value:
                raise S0ConflictError(
                    "BUNDLE_IDENTITY_MISMATCH",
                    f"manifest {field} does not match accepted spread",
                    {"field": field},
                )
        readiness = manifest.get("local_readiness")
        if not isinstance(readiness, dict) or readiness.get("ready") is not True:
            raise S0ValidationError("BUNDLE_NOT_LOCALLY_READY", "bundle local readiness is not true")
        if readiness.get("requires_both_pages") is not True:
            raise S0ValidationError("BUNDLE_ATOMICITY_INVALID", "bundle must require both pages")
        records = manifest.get("files")
        if not isinstance(records, list) or not records:
            raise S0ValidationError("BUNDLE_FILES_INVALID", "bundle files list is missing")
        if len(records) > self.config.max_bundle_files:
            raise S0ValidationError("BUNDLE_FILE_LIMIT", "bundle contains too many files")
        indexed: dict[str, dict[str, Any]] = {}
        total = 0
        for record in records:
            if not isinstance(record, dict):
                raise S0ValidationError("BUNDLE_FILE_RECORD_INVALID", "bundle file record is invalid")
            path_value = record.get("path")
            relative_path = _safe_relative_value(path_value)
            normalized = relative_path.as_posix()
            if normalized in indexed:
                raise S0ValidationError("BUNDLE_DUPLICATE_PATH", "bundle contains duplicate file paths")
            path = _confined_file(root, relative_path)
            size = path.stat().st_size
            if record.get("size_bytes") != size or record.get("sha256") != _sha256_file(path):
                raise S0ConflictError(
                    "BUNDLE_FILE_HASH_MISMATCH",
                    "bundle file size or hash differs from manifest",
                    {"path": normalized},
                )
            total += size
            if total > self.config.max_bundle_bytes:
                raise S0ValidationError("BUNDLE_BYTE_LIMIT", "bundle exceeds configured byte limit")
            indexed[normalized] = record
        actual: set[str] = set()
        for path in root.rglob("*"):
            if path.is_symlink():
                raise S0ValidationError("BUNDLE_SYMLINK_REJECTED", "bundle symlinks are not allowed")
            if path.is_file() and path != manifest_path:
                actual.add(path.relative_to(root).as_posix())
        if actual != set(indexed):
            raise S0ValidationError(
                "BUNDLE_UNLISTED_FILE",
                "bundle file listing does not exactly match stored files",
                {"unlisted": sorted(actual - set(indexed)), "missing": sorted(set(indexed) - actual)},
            )
        pages = manifest.get("pages")
        if not isinstance(pages, dict) or set(pages) != {"left", "right"}:
            raise S0ValidationError("BUNDLE_PAGES_INVALID", "bundle must contain left and right pages")
        left = self._page(root, relative, indexed, pages["left"], "left", spread.source_frame_id)
        right = self._page(root, relative, indexed, pages["right"], "right", spread.source_frame_id)
        return ValidatedBundle(root, relative.as_posix(), manifest, left, right)

    def _page(
        self,
        root: Path,
        bundle_relative: Path,
        indexed: dict[str, dict[str, Any]],
        page: Any,
        side: str,
        source_frame_id: str,
    ) -> ValidatedPage:
        if not isinstance(page, dict) or page.get("side") != side:
            raise S0ValidationError("BUNDLE_SIDE_INVALID", f"{side} page identity is invalid")
        files = page.get("files")
        if not isinstance(files, dict) or not isinstance(files.get("uvdoc"), dict):
            raise S0ValidationError("BUNDLE_UVDOC_MISSING", f"{side} UVDoc record is missing")
        uvdoc = files["uvdoc"]
        relative = _safe_relative_value(uvdoc.get("path"))
        normalized = relative.as_posix()
        indexed_record = indexed.get(normalized)
        if indexed_record is None or indexed_record.get("sha256") != uvdoc.get("sha256"):
            raise S0ConflictError("BUNDLE_UVDOC_RECORD_MISMATCH", f"{side} UVDoc record is inconsistent")
        path = _confined_file(root, relative)
        try:
            with Image.open(path) as image:
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise S0ValidationError("BUNDLE_UVDOC_DECODE_FAILED", f"{side} UVDoc image cannot decode") from exc
        if width < 1 or height < 1 or width > self.config.max_image_dimension or height > self.config.max_image_dimension:
            raise S0ValidationError("BUNDLE_IMAGE_DIMENSION_LIMIT", f"{side} UVDoc dimensions are invalid")
        if uvdoc.get("width") != width or uvdoc.get("height") != height:
            raise S0ConflictError("BUNDLE_UVDOC_DIMENSION_MISMATCH", f"{side} UVDoc dimensions differ")
        if page.get("source_frame_id", source_frame_id) != source_frame_id:
            raise S0ConflictError("BUNDLE_SOURCE_MISMATCH", f"{side} source frame differs")
        return ValidatedPage(
            side=side,
            image_relative_path=(bundle_relative / relative).as_posix(),
            image_sha256=str(uvdoc["sha256"]),
            width=width,
            height=height,
        )


class LocalBundleIngestHarness:
    """Copies a local fixture into server-owned receive storage for S1 tests."""

    def __init__(self, config: S1Config) -> None:
        self.config = config
        self.config.received_root.mkdir(parents=True, exist_ok=True)

    def import_bundle(self, source: Path, storage_key: str) -> str:
        relative = _safe_relative_value(storage_key)
        destination = (self.config.received_root / relative).resolve()
        root = self.config.received_root.resolve()
        if destination != root and root not in destination.parents:
            raise ValueError("storage key escapes receive root")
        if destination.exists():
            raise FileExistsError(destination)
        temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, temporary)
        os.replace(temporary, destination)
        return relative.as_posix()


def _safe_relative_value(value: Any) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise S0ValidationError("BUNDLE_PATH_INVALID", "bundle path must be a relative POSIX path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise S0ValidationError("BUNDLE_PATH_INVALID", "bundle path is not confined")
    return path


def _confined_file(root: Path, relative: Path) -> Path:
    path = (root / relative).resolve()
    if root != path.parent and root not in path.parents:
        raise S0ValidationError("BUNDLE_PATH_INVALID", "bundle file escapes root")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise S0ValidationError("BUNDLE_SYMLINK_REJECTED", "bundle symlinks are not allowed")
    if not path.is_file():
        raise S0ValidationError("BUNDLE_FILE_MISSING", "bundle file is missing")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
