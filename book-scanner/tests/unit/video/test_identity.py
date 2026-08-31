from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from book_scanner.video.config import IdentityPolicy
from book_scanner.video.identity import (
    IdentityFingerprintError,
    IdentityMatchKind,
    InMemoryPageIdentityLedger,
    OpenCVIdentityFingerprinter,
    compare_spread_identities,
)
from book_scanner.video.types import (
    ArtifactId,
    FrameId,
    PageArtifactRef,
    PageSide,
    SpreadArtifactRef,
    SpreadId,
)


def _page(seed: int) -> np.ndarray:
    image = np.full((480, 320, 3), 238, dtype=np.uint8)
    rng = np.random.default_rng(seed)
    for row in range(12):
        y = 35 + row * 32
        length = int(rng.integers(120, 270))
        cv2.line(image, (24, y), (24 + length, y), (25, 25, 25), 3)
    cv2.putText(image, str(seed), (120, 450), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
    return image


def _write_jpeg(path: Path, image: np.ndarray, quality: int = 94) -> str:
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    encoded.tofile(str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(tmp_path: Path, name: str, left_image: np.ndarray, right_image: np.ndarray) -> SpreadArtifactRef:
    root = tmp_path / name
    root.mkdir()
    left_path = root / "left.jpg"
    right_path = root / "right.jpg"
    left_sha = _write_jpeg(left_path, left_image)
    right_sha = _write_jpeg(right_path, right_image)
    source_sha = hashlib.sha256(f"source-{name}".encode()).hexdigest()
    left_crop_sha = hashlib.sha256(f"left-crop-{name}".encode()).hexdigest()
    right_crop_sha = hashlib.sha256(f"right-crop-{name}".encode()).hexdigest()
    manifest = {
        "source": {"sha256": source_sha},
        "pipeline": {
            "version": "seam-conservative+uvdoc-bilinear-v2",
            "extractor": "seam-conservative",
        },
        "pages": {
            "left": {"files": {"crop": {"sha256": left_crop_sha}}},
            "right": {"files": {"crop": {"sha256": right_crop_sha}}},
        },
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    frame_id = FrameId(f"frame-{name}")
    return SpreadArtifactRef(
        ArtifactId(f"artifact-{name}"),
        SpreadId(f"spread-{name}"),
        frame_id,
        PageArtifactRef(PageSide.LEFT, frame_id, str(left_path), left_sha, 320, 480),
        PageArtifactRef(PageSide.RIGHT, frame_id, str(right_path), right_sha, 320, 480),
        str(manifest_path),
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "seam-uvdoc-artifact-v2",
    )


def test_identical_corrected_files_are_exact_duplicate(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path, "a", _page(1), _page(2))
    provider = OpenCVIdentityFingerprinter()
    identity = provider.fingerprint_artifact(artifact)

    comparison = compare_spread_identities(identity, identity, IdentityPolicy())

    assert comparison.kind is IdentityMatchKind.EXACT_DUPLICATE


def test_brightness_translation_and_recompression_are_visual_duplicate(tmp_path: Path) -> None:
    left = _page(1)
    right = _page(2)
    matrix = np.float32([[1, 0, 2], [0, 1, 1]])
    changed_left = cv2.warpAffine(cv2.convertScaleAbs(left, alpha=0.94, beta=12), matrix, (320, 480), borderValue=(238, 238, 238))
    changed_right = cv2.warpAffine(cv2.convertScaleAbs(right, alpha=1.03, beta=-8), matrix, (320, 480), borderValue=(238, 238, 238))
    reference = OpenCVIdentityFingerprinter().fingerprint_artifact(
        _artifact(tmp_path, "reference", left, right)
    )
    candidate = OpenCVIdentityFingerprinter().fingerprint_artifact(
        _artifact(tmp_path, "candidate", changed_left, changed_right)
    )

    comparison = compare_spread_identities(candidate, reference, IdentityPolicy())

    assert comparison.kind is IdentityMatchKind.VISUAL_DUPLICATE


def test_left_right_swap_is_not_duplicate(tmp_path: Path) -> None:
    left = _page(1)
    right = _page(8)
    provider = OpenCVIdentityFingerprinter()
    reference = provider.fingerprint_artifact(_artifact(tmp_path, "reference", left, right))
    swapped = provider.fingerprint_artifact(_artifact(tmp_path, "swapped", right, left))

    assert compare_spread_identities(swapped, reference, IdentityPolicy()).kind is not IdentityMatchKind.VISUAL_DUPLICATE


def test_one_matching_page_is_ambiguous_not_duplicate(tmp_path: Path) -> None:
    provider = OpenCVIdentityFingerprinter()
    reference = provider.fingerprint_artifact(_artifact(tmp_path, "reference", _page(1), _page(2)))
    candidate = provider.fingerprint_artifact(_artifact(tmp_path, "candidate", _page(1), _page(30)))

    comparison = compare_spread_identities(candidate, reference, IdentityPolicy())

    assert comparison.kind is IdentityMatchKind.AMBIGUOUS
    assert comparison.left_agrees is True


def test_version_mismatch_is_explicitly_incompatible(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path, "a", _page(1), _page(2))
    first = OpenCVIdentityFingerprinter(IdentityPolicy(algorithm_version="identity-a")).fingerprint_artifact(artifact)
    second = OpenCVIdentityFingerprinter(IdentityPolicy(algorithm_version="identity-b")).fingerprint_artifact(artifact)

    comparison = compare_spread_identities(first, second, IdentityPolicy())

    assert comparison.kind is IdentityMatchKind.AMBIGUOUS
    assert comparison.compatible is False


def test_decode_failure_is_not_silently_reduced_to_sha_only(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path, "bad", _page(1), _page(2))
    bad_path = Path(artifact.left.image_path)
    bad_path.write_bytes(b"not-an-image")
    bad_sha = hashlib.sha256(b"not-an-image").hexdigest()
    broken = SpreadArtifactRef(
        artifact.artifact_id,
        artifact.spread_id,
        artifact.source_frame_id,
        PageArtifactRef(PageSide.LEFT, artifact.source_frame_id, str(bad_path), bad_sha, 320, 480),
        artifact.right,
        artifact.manifest_path,
        artifact.manifest_sha256,
        artifact.evaluator_version,
    )

    with pytest.raises(IdentityFingerprintError, match="cannot be decoded"):
        OpenCVIdentityFingerprinter().fingerprint_artifact(broken)


def test_ledger_has_one_pending_idempotent_confirm_and_bounded_acceptance(tmp_path: Path) -> None:
    policy = IdentityPolicy(accepted_capacity=2)
    provider = OpenCVIdentityFingerprinter(policy)
    identities = [
        provider.fingerprint_artifact(_artifact(tmp_path, str(index), _page(index), _page(index + 10)))
        for index in range(3)
    ]
    ledger = InMemoryPageIdentityLedger(policy)
    for index, identity in enumerate(identities):
        artifact_id = ArtifactId(f"artifact-{index}")
        ledger.register_pending(identity, artifact_id)
        assert ledger.confirm(artifact_id, f"receipt-{index}") is True
        assert ledger.confirm(artifact_id, f"receipt-{index}") is False

    assert [entry.artifact_id.value for entry in ledger.recent_accepted()] == ["artifact-2", "artifact-1"]
    assert ledger.reject_or_release(ArtifactId("stale")) is False
