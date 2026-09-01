"""Server V4 immutable upload values, limits, and wire validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from document_parser.server.s0_domain import (
    S0Error,
    S0ValidationError,
    require_id,
    require_positive_int,
    require_sha256,
)
from document_parser.server.s1_domain import S1Config


_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_METADATA_FIELDS = {
    "schema_version",
    "device_id",
    "sequence",
    "artifact_id",
    "spread_id",
    "source_frame_id",
    "manifest_sha256",
    "file_count",
    "total_file_bytes",
}


class V4LengthRequiredError(S0Error):
    def __init__(self) -> None:
        super().__init__(
            "CONTENT_LENGTH_REQUIRED",
            "Content-Length is required for bundle uploads",
            http_status=411,
        )


class V4PayloadTooLargeError(S0Error):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(code, message, http_status=413, details=details)


class V4MediaTypeError(S0Error):
    def __init__(self, message: str) -> None:
        super().__init__("UPLOAD_MEDIA_TYPE_UNSUPPORTED", message, http_status=415)


class V4BundleRejectedError(S0Error):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(code, message, http_status=422, details=details)


class V4CapacityError(S0Error):
    def __init__(self, code: str, message: str, *, http_status: int = 429) -> None:
        super().__init__(code, message, http_status=http_status, retryable=True)


@dataclass(frozen=True, slots=True)
class V4Config:
    staging_root: Path
    received_root: Path
    quarantine_root: Path
    max_manifest_bytes: int = 4 * 1024 * 1024
    max_bundle_files: int = 32
    max_bundle_bytes: int = 128 * 1024 * 1024
    max_image_dimension: int = 16_384
    max_multipart_overhead: int = 1024 * 1024
    max_relative_path_bytes: int = 255
    max_concurrent_upload_writers: int = 1
    max_staging_bytes: int = 512 * 1024 * 1024
    max_received_bytes: int = 8 * 1024 * 1024 * 1024
    upload_lease_seconds: int = 900
    partial_orphan_ttl_seconds: int = 3600
    rejected_quarantine_ttl_seconds: int = 24 * 3600

    def __post_init__(self) -> None:
        numeric = (
            "max_manifest_bytes",
            "max_bundle_files",
            "max_bundle_bytes",
            "max_image_dimension",
            "max_multipart_overhead",
            "max_relative_path_bytes",
            "max_concurrent_upload_writers",
            "max_staging_bytes",
            "max_received_bytes",
            "upload_lease_seconds",
            "partial_orphan_ttl_seconds",
            "rejected_quarantine_ttl_seconds",
        )
        for name in numeric:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be positive")
        for root in (self.staging_root, self.received_root, self.quarantine_root):
            if not isinstance(root, Path):
                raise TypeError("V4 storage roots must be pathlib.Path values")

    @property
    def max_request_bytes(self) -> int:
        return self.max_manifest_bytes + self.max_bundle_bytes + self.max_multipart_overhead

    @classmethod
    def from_s1(cls, config: S1Config) -> "V4Config":
        server_root = config.received_root.parent
        return cls(
            staging_root=server_root / "upload-staging",
            received_root=config.received_root,
            quarantine_root=server_root / "upload-quarantine",
            max_manifest_bytes=4 * 1024 * 1024,
            max_bundle_files=config.max_bundle_files,
            max_bundle_bytes=config.max_bundle_bytes,
            max_image_dimension=config.max_image_dimension,
        )


@dataclass(frozen=True, slots=True)
class UploadMetadata:
    device_id: str
    sequence: int
    artifact_id: str
    spread_id: str
    source_frame_id: str
    manifest_sha256: str
    file_count: int
    total_file_bytes: int

    @classmethod
    def from_json_bytes(cls, value: bytes) -> "UploadMetadata":
        try:
            payload = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise S0ValidationError("UPLOAD_METADATA_INVALID", "metadata must be valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise S0ValidationError("UPLOAD_METADATA_INVALID", "metadata must be a JSON object")
        if set(payload) != _METADATA_FIELDS:
            raise S0ValidationError(
                "UPLOAD_METADATA_FIELDS_INVALID",
                "metadata fields do not match schema version 1",
                {"unknown": sorted(set(payload) - _METADATA_FIELDS), "missing": sorted(_METADATA_FIELDS - set(payload))},
            )
        if payload.get("schema_version") != 1:
            raise S0ValidationError("UPLOAD_SCHEMA_UNSUPPORTED", "upload metadata schema must be 1")
        total = payload.get("total_file_bytes")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise S0ValidationError("INVALID_INTEGER", "total_file_bytes must be a non-negative integer")
        return cls(
            device_id=require_id("device_id", payload.get("device_id")),
            sequence=require_positive_int("sequence", payload.get("sequence")),
            artifact_id=require_id("artifact_id", payload.get("artifact_id")),
            spread_id=require_id("spread_id", payload.get("spread_id")),
            source_frame_id=require_id("source_frame_id", payload.get("source_frame_id")),
            manifest_sha256=require_sha256("manifest_sha256", payload.get("manifest_sha256")),
            file_count=require_positive_int("file_count", payload.get("file_count")),
            total_file_bytes=total,
        )


@dataclass(frozen=True, slots=True)
class FileDeclaration:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PreparedUpload:
    scan_session_id: str
    metadata: UploadMetadata
    manifest: Mapping[str, Any]
    manifest_bytes: bytes
    files: tuple[FileDeclaration, ...]
    upload_digest: str


@dataclass(frozen=True, slots=True)
class V4Result:
    body: dict[str, object]
    http_status: int
    replayed: bool = False


def prepare_upload(
    scan_session_id: str,
    metadata_bytes: bytes,
    manifest_bytes: bytes,
    supplied_digest: str,
    config: V4Config,
) -> PreparedUpload:
    scan_session_id = require_id("scan_session_id", scan_session_id)
    supplied_digest = require_sha256("X-ASL-Upload-Digest", supplied_digest)
    if len(manifest_bytes) > config.max_manifest_bytes:
        raise V4PayloadTooLargeError("BUNDLE_MANIFEST_TOO_LARGE", "bundle manifest exceeds configured limit")
    metadata = UploadMetadata.from_json_bytes(metadata_bytes)
    if hashlib.sha256(manifest_bytes).hexdigest() != metadata.manifest_sha256:
        raise V4BundleRejectedError("BUNDLE_MANIFEST_HASH_MISMATCH", "manifest bytes differ from metadata digest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise S0ValidationError("BUNDLE_MANIFEST_INVALID", "bundle manifest must be valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "2.0":
        raise S0ValidationError("BUNDLE_SCHEMA_UNSUPPORTED", "Scanner bundle schema must be 2.0")
    expected = {
        "artifact_id": metadata.artifact_id,
        "session_id": scan_session_id,
        "spread_id": metadata.spread_id,
        "source_frame_id": metadata.source_frame_id,
    }
    for field, expected_value in expected.items():
        if manifest.get(field) != expected_value:
            raise V4BundleRejectedError(
                "BUNDLE_IDENTITY_MISMATCH",
                f"manifest {field} does not match upload identity",
                {"field": field},
            )
    readiness = manifest.get("local_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not True:
        raise V4BundleRejectedError("BUNDLE_NOT_LOCALLY_READY", "bundle local readiness is not true")
    if readiness.get("requires_both_pages") is not True:
        raise V4BundleRejectedError("BUNDLE_ATOMICITY_INVALID", "bundle must require both pages")
    pages = manifest.get("pages")
    if not isinstance(pages, dict) or set(pages) != {"left", "right"}:
        raise V4BundleRejectedError("BUNDLE_PAGES_INVALID", "bundle must contain left and right pages")
    declarations = _file_declarations(manifest.get("files"), config)
    if len(declarations) != metadata.file_count:
        raise V4BundleRejectedError("BUNDLE_FILE_COUNT_MISMATCH", "metadata file count differs from manifest")
    total = sum(item.size_bytes for item in declarations)
    if total != metadata.total_file_bytes:
        raise V4BundleRejectedError("BUNDLE_BYTE_COUNT_MISMATCH", "metadata byte total differs from manifest")
    _validate_page_records(pages, declarations, metadata.source_frame_id, config.max_image_dimension)
    digest = canonical_upload_digest(scan_session_id, metadata, declarations)
    if digest != supplied_digest:
        raise V4BundleRejectedError("UPLOAD_DIGEST_MISMATCH", "canonical upload digest differs")
    return PreparedUpload(
        scan_session_id=scan_session_id,
        metadata=metadata,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        files=declarations,
        upload_digest=digest,
    )


def canonical_upload_digest(
    scan_session_id: str,
    metadata: UploadMetadata,
    files: tuple[FileDeclaration, ...],
) -> str:
    payload = {
        "schema_version": 1,
        "scan_session_id": scan_session_id,
        "device_id": metadata.device_id,
        "sequence": metadata.sequence,
        "artifact_id": metadata.artifact_id,
        "spread_id": metadata.spread_id,
        "source_frame_id": metadata.source_frame_id,
        "manifest_sha256": metadata.manifest_sha256,
        "files": [
            {"path": item.path, "size_bytes": item.size_bytes, "sha256": item.sha256}
            for item in sorted(files, key=lambda item: item.path)
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def safe_relative_path(value: object, config: V4Config) -> PurePosixPath:
    if not isinstance(value, str) or not value or len(value.encode("ascii", errors="ignore")) != len(value):
        raise S0ValidationError("BUNDLE_PATH_INVALID", "bundle path must be non-empty ASCII")
    if len(value.encode("ascii")) > config.max_relative_path_bytes or _SAFE_PATH_RE.fullmatch(value) is None:
        raise S0ValidationError("BUNDLE_PATH_INVALID", "bundle path contains unsupported characters")
    if "\\" in value:
        raise S0ValidationError("BUNDLE_PATH_INVALID", "bundle path must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise S0ValidationError("BUNDLE_PATH_INVALID", "bundle path is not confined")
    if len(path.parts) > 8:
        raise S0ValidationError("BUNDLE_PATH_INVALID", "bundle path is too deeply nested")
    return path


def _file_declarations(value: object, config: V4Config) -> tuple[FileDeclaration, ...]:
    if not isinstance(value, list) or not value:
        raise S0ValidationError("BUNDLE_FILES_INVALID", "manifest files must be a non-empty list")
    if len(value) > config.max_bundle_files:
        raise V4PayloadTooLargeError("BUNDLE_FILE_LIMIT", "bundle contains too many files")
    result: list[FileDeclaration] = []
    seen: set[str] = set()
    total = 0
    for record in value:
        if not isinstance(record, dict):
            raise S0ValidationError("BUNDLE_FILE_RECORD_INVALID", "bundle file record is invalid")
        path = safe_relative_path(record.get("path"), config).as_posix()
        if path == "manifest.json" or path in seen:
            raise S0ValidationError("BUNDLE_DUPLICATE_PATH", "bundle file path is duplicated or reserved")
        if any(path.startswith(f"{existing}/") or existing.startswith(f"{path}/") for existing in seen):
            raise S0ValidationError(
                "BUNDLE_PATH_CONFLICT",
                "bundle file path conflicts with another file path",
            )
        size = record.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise S0ValidationError("BUNDLE_FILE_RECORD_INVALID", "bundle file size is invalid", {"path": path})
        digest = require_sha256("file sha256", record.get("sha256"))
        total += size
        if total > config.max_bundle_bytes:
            raise V4PayloadTooLargeError("BUNDLE_BYTE_LIMIT", "bundle exceeds configured byte limit")
        seen.add(path)
        result.append(FileDeclaration(path, size, digest))
    return tuple(result)


def _validate_page_records(
    pages: Mapping[str, Any],
    declarations: tuple[FileDeclaration, ...],
    source_frame_id: str,
    max_image_dimension: int,
) -> None:
    indexed = {item.path: item for item in declarations}
    for side in ("left", "right"):
        page = pages.get(side)
        if not isinstance(page, dict) or page.get("side") != side:
            raise V4BundleRejectedError("BUNDLE_SIDE_INVALID", f"{side} page identity is invalid")
        if page.get("source_frame_id", source_frame_id) != source_frame_id:
            raise V4BundleRejectedError("BUNDLE_SOURCE_MISMATCH", f"{side} page source frame differs")
        files = page.get("files")
        uvdoc = files.get("uvdoc") if isinstance(files, dict) else None
        if not isinstance(uvdoc, dict):
            raise V4BundleRejectedError("BUNDLE_UVDOC_MISSING", f"{side} UVDoc record is missing")
        path = uvdoc.get("path")
        declaration = indexed.get(path) if isinstance(path, str) else None
        if declaration is None or uvdoc.get("sha256") != declaration.sha256 or uvdoc.get("size_bytes") != declaration.size_bytes:
            raise V4BundleRejectedError("BUNDLE_UVDOC_RECORD_MISMATCH", f"{side} UVDoc record is inconsistent")
        width = uvdoc.get("width")
        height = uvdoc.get("height")
        if any(
            isinstance(item, bool)
            or not isinstance(item, int)
            or item <= 0
            or item > max_image_dimension
            for item in (width, height)
        ):
            raise V4BundleRejectedError("BUNDLE_UVDOC_DIMENSION_INVALID", f"{side} UVDoc dimensions are invalid")
