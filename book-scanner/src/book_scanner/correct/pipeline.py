"""Orchestrates roadmap Stage 6 ("페이지 보정 및 스캔 산출물 생성") for one
capture: read the original (never modifying it), warp, write the corrected
output and its metadata -- both via atomic temp-file-then-rename, so a crash
or power loss mid-write can never leave a half-written file mistaken for a
real output (Stage 6 완료 조건: "저장 도중 오류... 완성되지 않은 파일을 정상
산출물로 취급하지 않는다").
"""

from __future__ import annotations

import cv2
import datetime
import hashlib
import json
import os
import uuid
from pathlib import Path

from book_scanner.correct.perspective import warp_to_rectangle
from book_scanner.correct.types import CorrectionMetadata, Corners


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_bytes(final_path: Path, data: bytes) -> None:
    """Write `data` to a temp file in the same directory, then rename into
    place. `os.replace` is atomic on both Windows and POSIX when source and
    destination are on the same volume -- a reader can never observe a
    partially-written file at `final_path`."""
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_name(f".{final_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, final_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def correct_and_save(
    original_path: Path,
    corners: Corners,
    output_dir: Path,
    capture_id: str | None = None,
) -> CorrectionMetadata:
    """Warp `original_path` per `corners` and write `<capture_id>.png` plus
    `<capture_id>.metadata.json` into `output_dir`. Never writes to
    `original_path` itself."""
    original_path = Path(original_path)
    output_dir = Path(output_dir)
    capture_id = capture_id or f"capture_{uuid.uuid4().hex[:12]}"

    original_sha256 = _sha256_file(original_path)

    frame = cv2.imread(str(original_path))
    if frame is None:
        raise FileNotFoundError(f"could not read image: {original_path}")

    corrected = warp_to_rectangle(frame, corners)
    ok, encoded = cv2.imencode(".png", corrected)
    if not ok:
        raise RuntimeError("failed to encode corrected image as PNG")

    corrected_path = output_dir / f"{capture_id}.png"
    _atomic_write_bytes(corrected_path, encoded.tobytes())
    corrected_sha256 = _sha256_file(corrected_path)

    height, width = corrected.shape[:2]
    metadata = CorrectionMetadata(
        capture_id=capture_id,
        original_path=str(original_path),
        original_sha256=original_sha256,
        corrected_path=str(corrected_path),
        corrected_sha256=corrected_sha256,
        corners=corners.as_tuple(),
        output_size=(width, height),
        created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )

    metadata_path = output_dir / f"{capture_id}.metadata.json"
    metadata_bytes = json.dumps(metadata.to_jsonable(), ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write_bytes(metadata_path, metadata_bytes)

    # Re-hash the original after everything else has run: any code path
    # above that accidentally touched original_path would show up here as a
    # hash mismatch, verified rather than merely intended by never opening
    # it for writing.
    if _sha256_file(original_path) != original_sha256:
        raise RuntimeError(f"original file was modified during correction: {original_path}")

    return metadata
