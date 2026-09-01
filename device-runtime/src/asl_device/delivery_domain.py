"""Immutable Scanner bundle validation and Server V4 wire values."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .delivery_config import DeviceDeliveryConfig
from .protocols import FatalPortError
from .types import ClientSpreadSequence, DeviceId, ScanSessionId, ScannerArtifactReady


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


@dataclass(frozen=True, slots=True)
class DeliveryFile:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PreparedDelivery:
    scan_session_id: str
    sequence: int
    device_id: str
    artifact_id: str
    spread_id: str
    source_frame_id: str
    manifest_path: str
    manifest_sha256: str
    files: tuple[DeliveryFile, ...]
    total_file_bytes: int
    upload_digest: str
    idempotency_key: str

    @property
    def root(self) -> Path:
        return Path(self.manifest_path).parent

    def metadata_bytes(self) -> bytes:
        return json.dumps(
            {
                "schema_version": 1,
                "device_id": self.device_id,
                "sequence": self.sequence,
                "artifact_id": self.artifact_id,
                "spread_id": self.spread_id,
                "source_frame_id": self.source_frame_id,
                "manifest_sha256": self.manifest_sha256,
                "file_count": len(self.files),
                "total_file_bytes": self.total_file_bytes,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class V4HttpResponse:
    status: int
    body: Mapping[str, Any]
    retry_after_seconds: float | None = None


class V4TransportError(OSError):
    """The request outcome is unknown and must be retried unchanged."""


def prepare_delivery(
    config: DeviceDeliveryConfig,
    device_id: DeviceId,
    scan_session_id: ScanSessionId,
    sequence: ClientSpreadSequence,
    artifact: ScannerArtifactReady,
) -> PreparedDelivery:
    if artifact.scan_session_id != scan_session_id:
        raise FatalPortError("artifact scan session does not match delivery request")
    artifact_component = Path(artifact.artifact_id.value)
    if (
        artifact_component.is_absolute()
        or artifact_component.name != artifact.artifact_id.value
        or artifact.artifact_id.value in {".", ".."}
    ):
        raise FatalPortError("artifact ID is not one safe path component")
    manifest_path = Path(os.path.abspath(artifact.manifest_path))
    root = manifest_path.parent
    expected_root = config.artifact_root / artifact.artifact_id.value
    if root != expected_root or manifest_path != expected_root / "manifest.json":
        raise FatalPortError("artifact manifest is outside the configured immutable artifact root")
    _require_plain_directory(config.artifact_root, root)
    manifest_bytes, manifest = _read_manifest(manifest_path)
    actual_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if actual_manifest_sha != artifact.manifest_sha256:
        raise FatalPortError("artifact manifest SHA-256 differs from Scanner event")
    expected_identity = {
        "schema_version": "2.0",
        "artifact_id": artifact.artifact_id.value,
        "session_id": scan_session_id.value,
        "spread_id": artifact.spread_id,
        "source_frame_id": artifact.source_frame_id,
    }
    for field, expected in expected_identity.items():
        if manifest.get(field) != expected:
            raise FatalPortError(f"artifact manifest identity mismatch: {field}")
    readiness = manifest.get("local_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not True:
        raise FatalPortError("artifact is not locally ready")
    if readiness.get("requires_both_pages") is not True:
        raise FatalPortError("artifact does not require both pages")
    pages = manifest.get("pages")
    if not isinstance(pages, dict) or set(pages) != {"left", "right"}:
        raise FatalPortError("artifact must contain left and right page records")
    files = _inventory(root, manifest.get("files"))
    _validate_pages(pages, files, artifact.source_frame_id)
    prepared = PreparedDelivery(
        scan_session_id=scan_session_id.value,
        sequence=sequence.value,
        device_id=device_id.value,
        artifact_id=artifact.artifact_id.value,
        spread_id=artifact.spread_id,
        source_frame_id=artifact.source_frame_id,
        manifest_path=str(manifest_path),
        manifest_sha256=actual_manifest_sha,
        files=files,
        total_file_bytes=sum(item.size_bytes for item in files),
        upload_digest="",
        idempotency_key="",
    )
    digest = canonical_upload_digest(prepared)
    return replace(prepared, upload_digest=digest, idempotency_key=f"v3b-{digest}")


def verify_prepared(config: DeviceDeliveryConfig, prepared: PreparedDelivery) -> None:
    manifest_path = Path(os.path.abspath(prepared.manifest_path))
    expected_root = config.artifact_root / prepared.artifact_id
    if manifest_path != expected_root / "manifest.json":
        raise FatalPortError("stored artifact manifest path escaped the configured root")
    _require_plain_directory(config.artifact_root, expected_root)
    manifest_bytes, manifest = _read_manifest(manifest_path)
    if hashlib.sha256(manifest_bytes).hexdigest() != prepared.manifest_sha256:
        raise FatalPortError("stored artifact manifest changed after enqueue")
    files = _inventory(expected_root, manifest.get("files"))
    if files != prepared.files:
        raise FatalPortError("stored artifact inventory changed after enqueue")
    if canonical_upload_digest(prepared) != prepared.upload_digest:
        raise FatalPortError("stored upload digest is inconsistent")


def canonical_upload_digest(prepared: PreparedDelivery) -> str:
    payload = {
        "schema_version": 1,
        "scan_session_id": prepared.scan_session_id,
        "device_id": prepared.device_id,
        "sequence": prepared.sequence,
        "artifact_id": prepared.artifact_id,
        "spread_id": prepared.spread_id,
        "source_frame_id": prepared.source_frame_id,
        "manifest_sha256": prepared.manifest_sha256,
        "files": [
            {"path": item.path, "size_bytes": item.size_bytes, "sha256": item.sha256}
            for item in sorted(prepared.files, key=lambda item: item.path)
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def prepared_from_row(row: Mapping[str, Any]) -> PreparedDelivery:
    try:
        inventory = json.loads(str(row["inventory_json"]))
        files = tuple(
            DeliveryFile(str(item["path"]), int(item["size_bytes"]), str(item["sha256"]))
            for item in inventory
        )
        prepared = PreparedDelivery(
            scan_session_id=str(row["scan_session_id"]),
            sequence=int(row["sequence"]),
            device_id=str(row["device_id"]),
            artifact_id=str(row["artifact_id"]),
            spread_id=str(row["spread_id"]),
            source_frame_id=str(row["source_frame_id"]),
            manifest_path=str(row["manifest_path"]),
            manifest_sha256=str(row["manifest_sha256"]),
            files=files,
            total_file_bytes=int(row["total_file_bytes"]),
            upload_digest=str(row["upload_digest"]),
            idempotency_key=str(row["idempotency_key"]),
        )
        if len(files) != int(row["file_count"]) or sum(item.size_bytes for item in files) != prepared.total_file_bytes:
            raise ValueError("outbox file totals are inconsistent")
        if canonical_upload_digest(prepared) != prepared.upload_digest:
            raise ValueError("outbox upload digest is inconsistent")
        if prepared.idempotency_key != f"v3b-{prepared.upload_digest}":
            raise ValueError("outbox idempotency key is inconsistent")
        return prepared
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FatalPortError("outbox row is malformed") from exc


def inventory_json(files: tuple[DeliveryFile, ...]) -> str:
    return json.dumps(
        [
            {"path": item.path, "size_bytes": item.size_bytes, "sha256": item.sha256}
            for item in files
        ],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _read_manifest(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FatalPortError("artifact manifest is not readable UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise FatalPortError("artifact manifest must be a JSON object")
    return raw, value


def _inventory(root: Path, value: object) -> tuple[DeliveryFile, ...]:
    if not isinstance(value, list) or not value:
        raise FatalPortError("artifact manifest files must be a non-empty list")
    result: list[DeliveryFile] = []
    seen: set[str] = set()
    for record in value:
        if not isinstance(record, dict):
            raise FatalPortError("artifact file record must be an object")
        relative = _safe_relative(record.get("path"))
        path_text = relative.as_posix()
        if path_text == "manifest.json" or path_text in seen:
            raise FatalPortError("artifact file path is duplicated or reserved")
        size = record.get("size_bytes")
        digest = record.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise FatalPortError("artifact file size is invalid")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise FatalPortError("artifact file SHA-256 is invalid")
        path = root.joinpath(*relative.parts)
        if _is_link_like(path) or not path.is_file() or path.resolve() != path:
            raise FatalPortError("artifact file is missing or link-backed")
        if path.stat().st_size != size or _sha256_file(path) != digest:
            raise FatalPortError("artifact file size or SHA-256 differs from manifest")
        seen.add(path_text)
        result.append(DeliveryFile(path_text, size, digest))
    entries = tuple(root.rglob("*"))
    if any(_is_link_like(path) for path in entries):
        raise FatalPortError("artifact tree cannot contain links or junctions")
    actual = {
        path.relative_to(root).as_posix()
        for path in entries
        if path.is_file() and path.name != "manifest.json"
    }
    if actual != seen:
        raise FatalPortError("artifact filesystem inventory differs from manifest")
    return tuple(result)


def _safe_relative(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or _SAFE_PATH_RE.fullmatch(value) is None or "\\" in value:
        raise FatalPortError("artifact file path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise FatalPortError("artifact file path is not confined")
    return path


def _validate_pages(
    pages: Mapping[str, Any],
    files: tuple[DeliveryFile, ...],
    source_frame_id: str,
) -> None:
    indexed = {item.path: item for item in files}
    for side in ("left", "right"):
        page = pages.get(side)
        if not isinstance(page, dict) or page.get("side") != side:
            raise FatalPortError(f"artifact {side} page identity is invalid")
        if page.get("source_frame_id", source_frame_id) != source_frame_id:
            raise FatalPortError(f"artifact {side} source frame is inconsistent")
        page_files = page.get("files")
        uvdoc = page_files.get("uvdoc") if isinstance(page_files, dict) else None
        if not isinstance(uvdoc, dict):
            raise FatalPortError(f"artifact {side} UVDoc record is missing")
        path = uvdoc.get("path")
        item = indexed.get(path) if isinstance(path, str) else None
        if item is None or uvdoc.get("size_bytes") != item.size_bytes or uvdoc.get("sha256") != item.sha256:
            raise FatalPortError(f"artifact {side} UVDoc record differs from inventory")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (uvdoc.get("width"), uvdoc.get("height"))
        ):
            raise FatalPortError(f"artifact {side} UVDoc dimensions are invalid")


def _require_plain_directory(root: Path, candidate: Path) -> None:
    if (
        candidate.parent != root.resolve()
        or _is_link_like(candidate)
        or not candidate.is_dir()
        or candidate.resolve() != candidate
    ):
        raise FatalPortError("artifact directory is missing or not directly owned by artifact_root")


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction is not None and is_junction(path))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FatalPortError("artifact file cannot be read") from exc
    return digest.hexdigest()
