from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from book_scanner.video.artifacts import (
    ArtifactCollisionError,
    ArtifactCommitError,
    FilesystemArtifactStore,
)
from book_scanner.video.types import (
    ArtifactId,
    FrameId,
    PageSide,
    PreparedPageArtifact,
    PreparedSpreadArtifact,
    ProcessingJobId,
    SpreadId,
)


def test_atomic_commit_promotes_staging_and_returns_final_paths(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "staging", tmp_path / "ready")
    prepared = _prepared(store.staging_root / "job-1")

    artifact = store.commit(prepared)

    final = store.final_root / "artifact-1"
    assert final.is_dir()
    assert not Path(prepared.staging_path).exists()
    assert Path(artifact.manifest_path) == final / "manifest.json"
    assert Path(artifact.left.image_path).read_bytes() == b"left-image"
    assert artifact.source_frame_id == prepared.source_frame_id


def test_same_id_and_hash_is_idempotent_and_discards_duplicate_staging(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "staging", tmp_path / "ready")
    first = _prepared(store.staging_root / "job-1")
    store.commit(first)
    duplicate = _prepared(store.staging_root / "job-1", job="job-1")

    artifact = store.commit(duplicate)

    assert artifact.artifact_id == ArtifactId("artifact-1")
    assert not Path(duplicate.staging_path).exists()
    assert json.loads((store.final_root / "artifact-1" / "manifest.json").read_text(encoding="utf-8"))["processing_job_id"] == "job-1"


def test_same_id_with_different_hash_is_collision_without_overwrite(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "staging", tmp_path / "ready")
    store.commit(_prepared(store.staging_root / "job-1"))
    conflicting = _prepared(store.staging_root / "job-2", job="job-2")

    with pytest.raises(ArtifactCollisionError):
        store.commit(conflicting)

    assert json.loads((store.final_root / "artifact-1" / "manifest.json").read_text(encoding="utf-8"))["processing_job_id"] == "job-1"
    assert Path(conflicting.staging_path).is_dir()


def test_hash_mismatch_and_path_escape_never_publish(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "staging", tmp_path / "ready")
    prepared = _prepared(store.staging_root / "job-1")
    Path(prepared.staging_path, "left", "uvdoc.jpg").write_bytes(b"tampered")

    with pytest.raises(ArtifactCommitError, match="hash mismatch"):
        store.commit(prepared)
    assert not (store.final_root / "artifact-1").exists()

    escaped = replace(
        _prepared(store.staging_root / "job-2", job="job-2"),
        manifest_relative_path="../outside.json",
    )
    with pytest.raises(ArtifactCommitError, match="child"):
        store.commit(escaped)


def test_discard_removes_only_private_staging_directory(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "staging", tmp_path / "ready")
    prepared = _prepared(store.staging_root / "job-1")
    final_sentinel = store.final_root / "keep.txt"
    final_sentinel.write_text("keep", encoding="utf-8")

    store.discard(prepared)

    assert not Path(prepared.staging_path).exists()
    assert final_sentinel.read_text(encoding="utf-8") == "keep"


def test_existing_commit_lock_prevents_racing_publish(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "staging", tmp_path / "ready")
    prepared = _prepared(store.staging_root / "job-1")
    lock = store.final_root / ".artifact-1.commit.lock"
    lock.write_text("held", encoding="utf-8")

    with pytest.raises(ArtifactCommitError, match="already in progress"):
        store.commit(prepared)

    assert Path(prepared.staging_path).is_dir()
    assert not (store.final_root / "artifact-1").exists()


def _prepared(
    staging: Path,
    *,
    job: str = "job-1",
) -> PreparedSpreadArtifact:
    manifest = json.dumps(
        {
            "artifact_id": "artifact-1",
            "session_id": "session-1",
            "processing_job_id": job,
            "spread_id": "spread-1",
            "source_frame_id": "frame-1",
        },
        sort_keys=True,
    ).encode("utf-8")
    left = b"left-image"
    right = b"right-image"
    (staging / "left").mkdir(parents=True)
    (staging / "right").mkdir(parents=True)
    (staging / "manifest.json").write_bytes(manifest)
    (staging / "left" / "uvdoc.jpg").write_bytes(left)
    (staging / "right" / "uvdoc.jpg").write_bytes(right)
    frame_id = FrameId("frame-1")
    return PreparedSpreadArtifact(
        artifact_id=ArtifactId("artifact-1"),
        session_id="session-1",
        job_id=ProcessingJobId(job),
        spread_id=SpreadId("spread-1"),
        source_frame_id=frame_id,
        staging_path=str(staging),
        manifest_relative_path="manifest.json",
        manifest_sha256=_sha(manifest),
        left=PreparedPageArtifact(
            PageSide.LEFT, frame_id, "left/uvdoc.jpg", _sha(left), 100, 200
        ),
        right=PreparedPageArtifact(
            PageSide.RIGHT, frame_id, "right/uvdoc.jpg", _sha(right), 100, 200
        ),
        evaluator_version="test-v1",
    )


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
