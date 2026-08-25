from __future__ import annotations

import hashlib
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np
import pytest

from book_scanner.correct import pipeline as pipeline_module
from book_scanner.correct.pipeline import correct_and_save
from book_scanner.correct.types import Corners


@contextmanager
def _tmp_dir():
    # Deliberately not pytest's tmp_path fixture: it shares one numbered
    # base dir per pytest session under the system temp root, and on at
    # least one dev machine that base dir had stale ACLs from a prior run
    # that blocked every test using it. tempfile.TemporaryDirectory() makes
    # its own directory with no shared state, so it isn't exposed to that.
    with tempfile.TemporaryDirectory(prefix="book_scanner_test_") as d:
        yield Path(d)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_source_image(path: Path) -> None:
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(frame, (20, 20), (280, 180), (255, 255, 255), -1)
    cv2.imwrite(str(path), frame)


CORNERS = Corners(
    top_left=(20.0, 20.0),
    top_right=(280.0, 20.0),
    bottom_right=(280.0, 180.0),
    bottom_left=(20.0, 180.0),
)


def test_original_file_is_never_modified():
    with _tmp_dir() as tmp_path:
        original = tmp_path / "source.png"
        _make_source_image(original)
        before = _sha256(original)

        correct_and_save(original, CORNERS, tmp_path / "out")

        assert _sha256(original) == before


def test_corrected_and_metadata_are_written_with_correct_hashes():
    with _tmp_dir() as tmp_path:
        original = tmp_path / "source.png"
        _make_source_image(original)

        metadata = correct_and_save(original, CORNERS, tmp_path / "out", capture_id="test123")

        corrected_path = Path(metadata.corrected_path)
        metadata_path = corrected_path.with_name("test123.metadata.json")

        assert corrected_path.exists()
        assert metadata_path.exists()
        assert metadata.original_sha256 == _sha256(original)
        assert metadata.corrected_sha256 == _sha256(corrected_path)

        on_disk = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert on_disk["capture_id"] == "test123"
        assert on_disk["original_sha256"] == metadata.original_sha256
        assert on_disk["corrected_sha256"] == metadata.corrected_sha256


def test_capture_id_defaults_to_unique_values():
    with _tmp_dir() as tmp_path:
        original = tmp_path / "source.png"
        _make_source_image(original)

        first = correct_and_save(original, CORNERS, tmp_path / "out")
        second = correct_and_save(original, CORNERS, tmp_path / "out")

        assert first.capture_id != second.capture_id


def test_failed_write_leaves_no_partial_output(monkeypatch):
    with _tmp_dir() as tmp_path:
        original = tmp_path / "source.png"
        _make_source_image(original)
        out_dir = tmp_path / "out"

        def _boom(*args, **kwargs):
            raise OSError("simulated disk failure")

        monkeypatch.setattr(pipeline_module.os, "replace", _boom)

        with pytest.raises(OSError):
            correct_and_save(original, CORNERS, out_dir, capture_id="willfail")

        if out_dir.exists():
            leftover = list(out_dir.iterdir())
            assert leftover == [], f"partial/temp files left behind: {leftover}"
