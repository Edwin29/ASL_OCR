from __future__ import annotations

from pathlib import Path

import pytest

from document_parser.server.experimental_reset import (
    CONFIRMATION_TOKEN,
    ExperimentalResetError,
    reset_experimental_state,
)


def _state(tmp_path: Path) -> Path:
    root = tmp_path / "e0b-production"
    (root / "datapacks" / "revision-1").mkdir(parents=True)
    (root / "datapacks" / "revision-1" / "manifest.json").write_text("{}")
    (root / "jobs").mkdir()
    (root / "jobs" / "job.json").write_text("{}")
    (root / "server.sqlite3").write_bytes(b"sqlite")
    return root


def test_reset_refuses_wrong_confirmation(tmp_path: Path) -> None:
    root = _state(tmp_path)

    with pytest.raises(ExperimentalResetError, match="confirmation"):
        reset_experimental_state(
            root,
            confirmation="yes",
            health_url=None,
        )

    assert (root / "server.sqlite3").is_file()


def test_reset_refuses_running_server(tmp_path: Path) -> None:
    root = _state(tmp_path)

    with pytest.raises(ExperimentalResetError, match="still reachable"):
        reset_experimental_state(
            root,
            confirmation=CONFIRMATION_TOKEN,
            health_url="http://127.0.0.1:8421/api/v1/health",
            health_probe=lambda _url: True,
        )

    assert (root / "server.sqlite3").is_file()


def test_reset_moves_state_to_recoverable_backup_and_recreates_roots(tmp_path: Path) -> None:
    root = _state(tmp_path)

    result = reset_experimental_state(
        root,
        confirmation=CONFIRMATION_TOKEN,
        health_url=None,
    )

    backup = Path(str(result["backup_root"]))
    assert result["status"] == "reset"
    assert result["recoverable"] is True
    assert (backup / "server.sqlite3").read_bytes() == b"sqlite"
    assert (backup / "datapacks" / "revision-1" / "manifest.json").is_file()
    assert (backup / "jobs" / "job.json").is_file()
    assert (root / "datapacks").is_dir()
    assert not any((root / "datapacks").iterdir())
    assert (root / "jobs").is_dir()
    assert not any((root / "jobs").iterdir())
    assert not (root / "server.sqlite3").exists()
