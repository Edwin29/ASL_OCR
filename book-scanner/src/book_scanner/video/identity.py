"""Versioned, lightweight page identity and bounded in-memory ledger."""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping

import cv2
import numpy as np

from .config import IdentityPolicy
from .types import ArtifactId, PageArtifactRef, PageSide, SpreadArtifactRef

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PHASH_RE = re.compile(r"^[0-9a-f]{16}$")


class IdentityFingerprintError(RuntimeError):
    """A required identity input was missing, corrupt, or incompatible."""


class IdentityMatchKind(str, Enum):
    EXACT_DUPLICATE = "exact_duplicate"
    VISUAL_DUPLICATE = "visual_duplicate"
    AMBIGUOUS = "ambiguous"
    NEW_SPREAD = "new_spread"


class LedgerEntryStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"


@dataclass(frozen=True, slots=True)
class VisualFingerprint:
    algorithm_version: str
    perceptual_hash: str
    horizontal_projection: tuple[int, ...]
    vertical_projection: tuple[int, ...]
    normalized_width: int
    normalized_height: int
    orb_descriptors: tuple[bytes, ...] = ()

    def __post_init__(self) -> None:
        if not self.algorithm_version.strip():
            raise ValueError("algorithm_version must be non-empty")
        if not _PHASH_RE.fullmatch(self.perceptual_hash):
            raise ValueError("perceptual_hash must be 16 lowercase hex characters")
        if self.normalized_width <= 0 or self.normalized_height <= 0:
            raise ValueError("normalized dimensions must be positive")
        if not self.horizontal_projection or not self.vertical_projection:
            raise ValueError("projection fingerprints must be non-empty")
        if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255 for value in self.horizontal_projection + self.vertical_projection):
            raise ValueError("projection values must be integers in [0, 255]")
        if any(not isinstance(item, bytes) or len(item) != 32 for item in self.orb_descriptors):
            raise ValueError("ORB descriptors must be 32-byte values")


@dataclass(frozen=True, slots=True)
class PageIdentity:
    side: PageSide
    corrected_sha256: str
    conservative_crop_sha256: str
    source_frame_sha256: str
    output_width: int
    output_height: int
    extractor_version: str
    correction_version: str
    visual: VisualFingerprint

    def __post_init__(self) -> None:
        if not isinstance(self.side, PageSide):
            raise TypeError("side must be PageSide")
        for name in ("corrected_sha256", "conservative_crop_sha256", "source_frame_sha256"):
            if not _SHA256_RE.fullmatch(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256")
        if self.output_width <= 0 or self.output_height <= 0:
            raise ValueError("output dimensions must be positive")
        if not self.extractor_version.strip() or not self.correction_version.strip():
            raise ValueError("extractor and correction versions must be non-empty")
        if not isinstance(self.visual, VisualFingerprint):
            raise TypeError("visual must be VisualFingerprint")


@dataclass(frozen=True, slots=True)
class SpreadVisualFingerprint:
    algorithm_version: str
    left: VisualFingerprint
    right: VisualFingerprint

    def __post_init__(self) -> None:
        if not self.algorithm_version.strip():
            raise ValueError("algorithm_version must be non-empty")
        if self.left.algorithm_version != self.algorithm_version or self.right.algorithm_version != self.algorithm_version:
            raise ValueError("page visual versions must match spread version")


@dataclass(frozen=True, slots=True)
class SpreadIdentity:
    algorithm_version: str
    source_frame_sha256: str
    artifact_manifest_sha256: str
    left: PageIdentity
    right: PageIdentity

    def __post_init__(self) -> None:
        if not self.algorithm_version.strip():
            raise ValueError("algorithm_version must be non-empty")
        if not _SHA256_RE.fullmatch(self.source_frame_sha256):
            raise ValueError("source_frame_sha256 must be a lowercase SHA-256")
        if not _SHA256_RE.fullmatch(self.artifact_manifest_sha256):
            raise ValueError("artifact_manifest_sha256 must be a lowercase SHA-256")
        if self.left.side is not PageSide.LEFT or self.right.side is not PageSide.RIGHT:
            raise ValueError("spread identity must preserve left/right order")
        if self.left.visual.algorithm_version != self.algorithm_version or self.right.visual.algorithm_version != self.algorithm_version:
            raise ValueError("page fingerprint versions must match spread version")

    @property
    def visual(self) -> SpreadVisualFingerprint:
        return SpreadVisualFingerprint(self.algorithm_version, self.left.visual, self.right.visual)


@dataclass(frozen=True, slots=True)
class IdentityComparison:
    kind: IdentityMatchKind
    left_hamming: int | None
    right_hamming: int | None
    left_projection_mae: float | None
    right_projection_mae: float | None
    left_agrees: bool
    right_agrees: bool
    compatible: bool = True
    left_feature_match: float | None = None
    right_feature_match: float | None = None


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    identity: SpreadIdentity
    artifact_id: ArtifactId
    status: LedgerEntryStatus
    receipt_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, SpreadIdentity):
            raise TypeError("identity must be SpreadIdentity")
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be ArtifactId")
        if not isinstance(self.status, LedgerEntryStatus):
            raise TypeError("status must be LedgerEntryStatus")
        if self.status is LedgerEntryStatus.ACCEPTED and (not isinstance(self.receipt_id, str) or not self.receipt_id.strip()):
            raise ValueError("accepted ledger entry requires receipt_id")
        if self.status is LedgerEntryStatus.PENDING and self.receipt_id is not None:
            raise ValueError("pending ledger entry cannot have receipt_id")


@dataclass(frozen=True, slots=True)
class LedgerMatch:
    comparison: IdentityComparison
    entry: LedgerEntry | None = None


class OpenCVIdentityFingerprinter:
    """Fingerprint committed V2 artifacts and cheap masked preview pairs."""

    def __init__(self, policy: IdentityPolicy = IdentityPolicy()) -> None:
        self.policy = policy

    def fingerprint_artifact(self, artifact: SpreadArtifactRef) -> SpreadIdentity:
        manifest_path = Path(artifact.manifest_path)
        if _sha256_file(manifest_path) != artifact.manifest_sha256:
            raise IdentityFingerprintError("artifact manifest hash mismatch")
        manifest = _read_manifest(manifest_path)
        source_sha = _nested_sha(manifest, "source", "sha256")
        pipeline = _mapping(manifest, "pipeline")
        correction_version = _required_text(pipeline, "version")
        extractor_version = _required_text(pipeline, "extractor")
        pages = _mapping(manifest, "pages")
        left = self._page_identity(artifact.left, pages, source_sha, extractor_version, correction_version)
        right = self._page_identity(artifact.right, pages, source_sha, extractor_version, correction_version)
        return SpreadIdentity(
            algorithm_version=self.policy.algorithm_version,
            source_frame_sha256=source_sha,
            artifact_manifest_sha256=artifact.manifest_sha256,
            left=left,
            right=right,
        )

    def fingerprint_preview(
        self,
        gray_preview: object,
        mask_preview: object,
        seam_fraction: float | None,
    ) -> SpreadVisualFingerprint:
        if not isinstance(gray_preview, np.ndarray) or gray_preview.ndim != 2 or gray_preview.size == 0:
            raise IdentityFingerprintError("preview grayscale image is invalid")
        if not isinstance(mask_preview, np.ndarray) or mask_preview.shape != gray_preview.shape:
            raise IdentityFingerprintError("preview mask is invalid")
        height, width = gray_preview.shape
        seam = 0.5 if seam_fraction is None else float(seam_fraction)
        if not 0.2 <= seam <= 0.8:
            raise IdentityFingerprintError("preview seam is outside the fixed spread region")
        split = min(width - 1, max(1, round(width * seam)))
        left = _masked_side(gray_preview[:, :split], mask_preview[:, :split], "left")
        right = _masked_side(gray_preview[:, split:], mask_preview[:, split:], "right")
        return SpreadVisualFingerprint(
            self.policy.algorithm_version,
            _visual_fingerprint(left, self.policy),
            _visual_fingerprint(right, self.policy),
        )

    def _page_identity(
        self,
        page: PageArtifactRef,
        pages: Mapping[str, object],
        source_sha: str,
        extractor_version: str,
        correction_version: str,
    ) -> PageIdentity:
        image_path = Path(page.image_path)
        actual_sha = _sha256_file(image_path)
        if actual_sha != page.sha256:
            raise IdentityFingerprintError(f"{page.side.value} corrected page hash mismatch")
        image = _decode_image(image_path)
        if image.shape[1] != page.width or image.shape[0] != page.height:
            raise IdentityFingerprintError(f"{page.side.value} corrected page dimensions mismatch")
        page_manifest = _mapping(pages, page.side.value)
        files = _mapping(page_manifest, "files")
        crop_sha = _nested_sha(files, "crop", "sha256")
        return PageIdentity(
            side=page.side,
            corrected_sha256=page.sha256,
            conservative_crop_sha256=crop_sha,
            source_frame_sha256=source_sha,
            output_width=page.width,
            output_height=page.height,
            extractor_version=extractor_version,
            correction_version=correction_version,
            visual=_visual_fingerprint(image, self.policy),
        )


class InMemoryPageIdentityLedger:
    """One pending spread plus a bounded ring of recently accepted identities."""

    def __init__(self, policy: IdentityPolicy = IdentityPolicy()) -> None:
        self.policy = policy
        self._pending: LedgerEntry | None = None
        self._accepted: deque[LedgerEntry] = deque(maxlen=policy.accepted_capacity)

    @property
    def pending(self) -> LedgerEntry | None:
        return self._pending

    def register_pending(self, identity: SpreadIdentity, artifact_id: ArtifactId) -> LedgerEntry:
        if self._pending is not None:
            if self._pending.artifact_id == artifact_id and self._pending.identity == identity:
                return self._pending
            raise RuntimeError("only one pending spread is allowed")
        self._pending = LedgerEntry(identity, artifact_id, LedgerEntryStatus.PENDING)
        return self._pending

    def find_match(self, identity: SpreadIdentity) -> LedgerMatch:
        entries = (() if self._pending is None else (self._pending,)) + tuple(reversed(self._accepted))
        ambiguous: LedgerMatch | None = None
        visual: LedgerMatch | None = None
        for entry in entries:
            comparison = compare_spread_identities(identity, entry.identity, self.policy)
            match = LedgerMatch(comparison, entry)
            if comparison.kind is IdentityMatchKind.EXACT_DUPLICATE:
                return match
            if comparison.kind is IdentityMatchKind.VISUAL_DUPLICATE and visual is None:
                visual = match
            elif comparison.kind is IdentityMatchKind.AMBIGUOUS and ambiguous is None:
                ambiguous = match
        if visual is not None:
            return visual
        if ambiguous is not None:
            return ambiguous
        return LedgerMatch(_new_comparison(), None)

    def confirm(self, artifact_id: ArtifactId, receipt_id: str) -> bool:
        if not receipt_id.strip():
            raise ValueError("receipt_id must be non-empty")
        if self._pending is None or self._pending.artifact_id != artifact_id:
            return False
        accepted = LedgerEntry(
            self._pending.identity,
            artifact_id,
            LedgerEntryStatus.ACCEPTED,
            receipt_id,
        )
        self._pending = None
        self._accepted.append(accepted)
        return True

    def reject_or_release(self, artifact_id: ArtifactId) -> bool:
        if self._pending is None or self._pending.artifact_id != artifact_id:
            return False
        self._pending = None
        return True

    def recent_accepted(self) -> tuple[LedgerEntry, ...]:
        return tuple(reversed(self._accepted))


def compare_spread_identities(
    candidate: SpreadIdentity,
    reference: SpreadIdentity,
    policy: IdentityPolicy,
) -> IdentityComparison:
    if candidate.algorithm_version != reference.algorithm_version:
        return _incompatible_comparison()
    if (
        candidate.left.corrected_sha256 == reference.left.corrected_sha256
        and candidate.right.corrected_sha256 == reference.right.corrected_sha256
    ):
        return IdentityComparison(
            IdentityMatchKind.EXACT_DUPLICATE,
            0,
            0,
            0.0,
            0.0,
            True,
            True,
        )
    return compare_visual_spreads(candidate.visual, reference.visual, policy)


def compare_visual_spreads(
    candidate: SpreadVisualFingerprint,
    reference: SpreadVisualFingerprint,
    policy: IdentityPolicy,
) -> IdentityComparison:
    if candidate.algorithm_version != reference.algorithm_version:
        return _incompatible_comparison()
    left = _compare_visual(candidate.left, reference.left, policy)
    right = _compare_visual(candidate.right, reference.right, policy)
    metrics = (left[1], right[1], left[2], right[2])
    if left[0] == "same" and right[0] == "same":
        return IdentityComparison(
            IdentityMatchKind.VISUAL_DUPLICATE,
            *metrics,
            True,
            True,
            left_feature_match=left[3],
            right_feature_match=right[3],
        )
    if left[0] == "different" and right[0] == "different":
        return IdentityComparison(
            IdentityMatchKind.NEW_SPREAD,
            *metrics,
            False,
            False,
            left_feature_match=left[3],
            right_feature_match=right[3],
        )
    return IdentityComparison(
        IdentityMatchKind.AMBIGUOUS,
        *metrics,
        left[0] == "same",
        right[0] == "same",
        left_feature_match=left[3],
        right_feature_match=right[3],
    )


def _compare_visual(
    candidate: VisualFingerprint,
    reference: VisualFingerprint,
    policy: IdentityPolicy,
) -> tuple[str, int, float, float]:
    if candidate.algorithm_version != reference.algorithm_version:
        return ("ambiguous", 64, 1.0, 0.0)
    hamming = (int(candidate.perceptual_hash, 16) ^ int(reference.perceptual_hash, 16)).bit_count()
    values_a = candidate.horizontal_projection + candidate.vertical_projection
    values_b = reference.horizontal_projection + reference.vertical_projection
    if len(values_a) != len(values_b):
        return ("ambiguous", hamming, 1.0, 0.0)
    projection_mae = sum(abs(a - b) for a, b in zip(values_a, values_b)) / (255.0 * len(values_a))
    feature_match = _orb_match_fraction(candidate.orb_descriptors, reference.orb_descriptors)
    strict_same = hamming <= policy.visual_hamming_max and projection_mae <= policy.visual_projection_mae_max
    feature_same = (
        feature_match >= policy.visual_feature_match_min
        and hamming <= policy.visual_hamming_relaxed_max
    )
    if strict_same or feature_same:
        return ("same", hamming, projection_mae, feature_match)
    if (
        hamming >= policy.different_hamming_min
        and projection_mae >= policy.different_projection_mae_min
        and feature_match <= policy.different_feature_match_max
    ):
        return ("different", hamming, projection_mae, feature_match)
    return ("ambiguous", hamming, projection_mae, feature_match)


def _visual_fingerprint(image: np.ndarray, policy: IdentityPolicy) -> VisualFingerprint:
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise IdentityFingerprintError("identity image is empty")
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 2:
        gray = image
    else:
        raise IdentityFingerprintError("identity image must be grayscale or BGR")
    content = _content_crop(gray)
    normalized = cv2.resize(
        content,
        (policy.normalized_width, policy.normalized_height),
        interpolation=cv2.INTER_AREA,
    )
    normalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(normalized)
    phash_image = cv2.resize(normalized, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low_frequency = cv2.dct(phash_image)[:8, :8]
    threshold = float(np.median(low_frequency.reshape(-1)[1:]))
    bits = low_frequency >= threshold
    hash_value = 0
    for bit in bits.reshape(-1):
        hash_value = (hash_value << 1) | int(bool(bit))
    _threshold, ink = cv2.threshold(
        normalized,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )
    horizontal = _projection(ink, policy.projection_bins, axis=1)
    vertical = _projection(ink, policy.projection_bins, axis=0)
    feature_scale = min(1.0, policy.orb_max_dimension / max(content.shape[:2]))
    feature_size = (
        max(1, round(content.shape[1] * feature_scale)),
        max(1, round(content.shape[0] * feature_scale)),
    )
    feature_image = cv2.resize(content, feature_size, interpolation=cv2.INTER_AREA)
    feature_image = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(feature_image)
    detector = cv2.ORB_create(
        nfeatures=policy.orb_features,
        edgeThreshold=12,
        fastThreshold=10,
    )
    _keypoints, descriptors = detector.detectAndCompute(feature_image, None)
    frozen_descriptors = (
        tuple(bytes(row) for row in descriptors[: policy.orb_features])
        if descriptors is not None
        else ()
    )
    return VisualFingerprint(
        policy.algorithm_version,
        f"{hash_value:016x}",
        horizontal,
        vertical,
        policy.normalized_width,
        policy.normalized_height,
        frozen_descriptors,
    )


def _orb_match_fraction(candidate: tuple[bytes, ...], reference: tuple[bytes, ...]) -> float:
    if len(candidate) < 2 or len(reference) < 2:
        return 0.0
    left = np.frombuffer(b"".join(candidate), dtype=np.uint8).reshape(-1, 32)
    right = np.frombuffer(b"".join(reference), dtype=np.uint8).reshape(-1, 32)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    def ratio(source: np.ndarray, target: np.ndarray) -> float:
        pairs = matcher.knnMatch(source, target, k=2)
        good = sum(1 for pair in pairs if len(pair) == 2 and pair[0].distance < 0.80 * pair[1].distance)
        return good / max(1, len(source))

    return min(ratio(left, right), ratio(right, left))


def _content_crop(gray: np.ndarray) -> np.ndarray:
    """Reduce camera/UVDoc margin variance without interpreting page text."""

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _threshold, ink = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )
    ys, xs = np.nonzero(ink)
    if len(xs) < max(64, gray.size // 1000):
        return gray
    x0, x1 = np.quantile(xs, (0.005, 0.995)).astype(int)
    y0, y1 = np.quantile(ys, (0.005, 0.995)).astype(int)
    if x1 - x0 < gray.shape[1] * 0.25 or y1 - y0 < gray.shape[0] * 0.25:
        return gray
    pad_x = max(2, round((x1 - x0) * 0.02))
    pad_y = max(2, round((y1 - y0) * 0.02))
    x0 = max(0, x0 - pad_x)
    x1 = min(gray.shape[1] - 1, x1 + pad_x)
    y0 = max(0, y0 - pad_y)
    y1 = min(gray.shape[0] - 1, y1 + pad_y)
    return gray[y0 : y1 + 1, x0 : x1 + 1]


def _projection(image: np.ndarray, bins: int, *, axis: int) -> tuple[int, ...]:
    profile = np.mean(image, axis=axis)
    chunks = np.array_split(profile, bins)
    return tuple(int(round(float(np.mean(chunk)))) for chunk in chunks)


def _masked_side(gray: np.ndarray, mask: np.ndarray, label: str) -> np.ndarray:
    active = mask > 0
    if int(np.count_nonzero(active)) < 64:
        raise IdentityFingerprintError(f"{label} preview page mask is missing")
    ys, xs = np.nonzero(active)
    crop = gray[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1].copy()
    crop_mask = active[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    fill = int(np.median(crop[crop_mask]))
    crop[~crop_mask] = fill
    return crop


def _read_manifest(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IdentityFingerprintError(f"artifact manifest cannot be read: {path}") from exc
    if not isinstance(payload, Mapping):
        raise IdentityFingerprintError("artifact manifest must be an object")
    return payload


def _decode_image(path: Path) -> np.ndarray:
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except (OSError, ValueError, cv2.error) as exc:
        raise IdentityFingerprintError(f"identity image cannot be decoded: {path}") from exc
    if image is None:
        raise IdentityFingerprintError(f"identity image cannot be decoded: {path}")
    return image


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise IdentityFingerprintError(f"identity file cannot be read: {path}") from exc
    return digest.hexdigest()


def _mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise IdentityFingerprintError(f"manifest field {key!r} must be an object")
    return value


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IdentityFingerprintError(f"manifest field {key!r} must be non-empty text")
    return value


def _nested_sha(payload: Mapping[str, object], outer: str, inner: str) -> str:
    value = _required_text(_mapping(payload, outer), inner)
    if not _SHA256_RE.fullmatch(value):
        raise IdentityFingerprintError(f"manifest field {outer}.{inner} must be SHA-256")
    return value


def _new_comparison() -> IdentityComparison:
    return IdentityComparison(IdentityMatchKind.NEW_SPREAD, None, None, None, None, False, False)


def _incompatible_comparison() -> IdentityComparison:
    return IdentityComparison(IdentityMatchKind.AMBIGUOUS, None, None, None, None, False, False, False)
