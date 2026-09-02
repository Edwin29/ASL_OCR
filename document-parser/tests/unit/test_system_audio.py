from __future__ import annotations

import json

import pytest

from document_parser.datapack.ingest import ensure_system_pool
from document_parser.datapack.schema import SYSTEM_UI_PROMPTS
from document_parser.server.system_audio import SystemAudioService


class Synthesizer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, text: str):
        self.calls.append(text)
        return (b"\x01\x00" * 160, 16000, 1)


def test_ui_prompts_merge_with_boundary_pool_and_are_restart_idempotent(tmp_path) -> None:
    root = tmp_path / "datapacks"
    first = Synthesizer()
    ensure_system_pool(first, root / "_system", log_fn=lambda _message: None)
    boundary_count = len(first.calls)

    ui = Synthesizer()
    SystemAudioService(root, ui)
    payload = json.loads(
        (root / "_system" / "audio_index.json").read_text(encoding="utf-8")
    )
    texts = {entry["text"] for entry in payload["utterances"].values()}

    assert boundary_count > 0
    assert set(SYSTEM_UI_PROMPTS.values()) <= texts
    assert len(ui.calls) == len(set(SYSTEM_UI_PROMPTS.values()))
    restarted = Synthesizer()
    SystemAudioService(root, restarted)
    assert restarted.calls == []


def test_title_reference_is_device_scoped_and_path_confined(tmp_path) -> None:
    service = SystemAudioService(tmp_path / "datapacks", Synthesizer())
    first = service.title_reference("device-1", "수학 데이터팩")
    second = service.title_reference("device-2", "수학 데이터팩")

    assert first.startswith("s0-system-audio:")
    assert first != second
    path = service.resolve_reference("device-1", first.removeprefix("s0-system-audio:"))
    assert path.is_file()
    assert path.is_relative_to(service.system_root)
    with pytest.raises(KeyError):
        service.resolve_reference("device-2", first.removeprefix("s0-system-audio:"))
    assert service.cue_path("scan.spread_sent").is_file()
