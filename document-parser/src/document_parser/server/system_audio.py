"""Piper-backed, device-scoped S0 system prompt resources."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from document_parser.datapack.ingest import SynthesizeFn, ensure_system_utterances
from document_parser.datapack.schema import SYSTEM_UI_PROMPTS


class SystemAudioService:
    """Own the shared system pool and issue device-scoped opaque references."""

    def __init__(self, datapacks_root: Path, synthesize: SynthesizeFn) -> None:
        self.datapacks_root = Path(datapacks_root).resolve()
        self.system_root = (self.datapacks_root / "_system").resolve()
        self.synthesize = synthesize
        self._lock = threading.RLock()
        self._entries_by_text: dict[str, dict[str, object]] = {}
        self.ensure_fixed_prompts()

    def ensure_fixed_prompts(self) -> None:
        with self._lock:
            ensure_system_utterances(
                list(SYSTEM_UI_PROMPTS.values()),
                self.synthesize,
                self.system_root,
            )
            self._reload()

    def title_reference(self, device_id: str, title: str) -> str:
        with self._lock:
            if title not in self._entries_by_text:
                ensure_system_utterances([title], self.synthesize, self.system_root)
                self._reload()
            path = self._path_for_text(title)
            return self._reference(device_id, path)

    def cue_path(self, cue: str) -> Path:
        try:
            text = SYSTEM_UI_PROMPTS[cue]
        except KeyError as exc:
            raise KeyError("unknown system audio cue") from exc
        with self._lock:
            return self._path_for_text(text)

    def resolve_reference(self, device_id: str, audio_id: str) -> Path:
        expected = f"s0-system-audio:{audio_id}"
        with self._lock:
            for entry in self._entries_by_text.values():
                path = self._entry_path(entry)
                if self._reference(device_id, path) == expected:
                    return path
        raise KeyError("unknown system audio resource")

    def _reload(self) -> None:
        payload = json.loads(
            (self.system_root / "audio_index.json").read_text(encoding="utf-8")
        )
        entries = payload.get("utterances")
        if not isinstance(entries, dict):
            raise ValueError("system audio index is malformed")
        by_text: dict[str, dict[str, object]] = {}
        for entry in entries.values():
            if isinstance(entry, dict) and isinstance(entry.get("text"), str):
                by_text[str(entry["text"])] = dict(entry)
        self._entries_by_text = by_text

    def _path_for_text(self, text: str) -> Path:
        try:
            entry = self._entries_by_text[text]
        except KeyError as exc:
            raise KeyError("system audio text is unavailable") from exc
        return self._entry_path(entry)

    def _entry_path(self, entry: dict[str, object]) -> Path:
        wav = entry.get("wav")
        if not isinstance(wav, str):
            raise ValueError("system audio entry has no WAV path")
        relative = Path(wav)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("system audio path is unsafe")
        path = (self.system_root / relative).resolve()
        if path != self.system_root and self.system_root not in path.parents:
            raise ValueError("system audio path escapes the system pool")
        return path

    def _reference(self, device_id: str, path: Path) -> str:
        relative = path.relative_to(self.datapacks_root).as_posix()
        digest = hashlib.sha256(
            f"{device_id}\0{relative}".encode("utf-8")
        ).hexdigest()[:32]
        return f"s0-system-audio:{digest}"
