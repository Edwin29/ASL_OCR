"""Build and validate one immutable incremental datapack revision."""

from __future__ import annotations

import hashlib
import json
import shutil
import wave
from pathlib import Path
from typing import Any, Callable

from document_parser.datapack.ingest import (
    ensure_system_pool,
    enumerate_utterances,
    synthesize_all,
)
from document_parser.datapack.loader import load_datapack
from document_parser.datapack.preflight import preflight_datapack_root
from document_parser.datapack.schema import build_manifest
from document_parser.server.session import DatapackSession
from document_parser.server.s0_domain import S0ConflictError, S0ValidationError


class IncrementalDatapackAssembler:
    def __init__(
        self,
        datapacks_root: Path,
        synthesize: Callable[[str], tuple[bytes, int, int]],
        tts_manifest: dict[str, object],
    ) -> None:
        self.datapacks_root = datapacks_root.resolve()
        self.synthesize = synthesize
        self.tts_manifest = dict(tts_manifest)

    def assemble(
        self,
        staging: Path,
        *,
        datapack_id: str,
        title: str,
        base_revision: int | None,
        target_revision: int,
        base_root: Path | None,
        fragments: list[dict[str, Any]],
        scan_session_id: str,
        through_sequence: int,
        created_at: str,
    ) -> str:
        staging.mkdir(parents=True, exist_ok=False)
        base_pages: list[dict[str, object]] = []
        existing_index: dict[str, dict[str, Any]] = {}
        if base_root is not None:
            base_root = base_root.resolve()
            _require_confined(base_root, self.datapacks_root)
            document = _read_json(base_root / "document.json")
            if document.get("document_id") != datapack_id:
                raise S0ConflictError("BASE_DOCUMENT_ID_MISMATCH", "base document ID differs")
            pages = document.get("pages")
            if not isinstance(pages, list):
                raise S0ValidationError("BASE_DOCUMENT_INVALID", "base pages are invalid")
            base_pages = [page for page in pages if isinstance(page, dict)]
            existing_index = _read_audio_index(base_root / "audio_index.json")
            self._copy_existing_audio(base_root, staging, existing_index)
        new_pages: list[dict[str, object]] = []
        parser_engines: list[object] = []
        validations: list[object] = []
        for fragment in fragments:
            page_path = self.datapacks_root / fragment["accessible_page_relative_path"]
            _require_confined(page_path.resolve(), self.datapacks_root)
            page = _read_json(page_path)
            if page.get("page_id") != fragment["page_id"]:
                raise S0ConflictError("FRAGMENT_PAGE_ID_MISMATCH", "fragment page identity differs")
            new_pages.append(page)
            parser_engines.append(_json_or_empty(fragment.get("parser_engine_json")))
            validations.append(_json_or_empty(fragment.get("validation_json")))
        pages = base_pages + new_pages
        _validate_pages(pages)
        document = {
            "document_id": datapack_id,
            "pages": pages,
            "global_reading_order": [
                str(item["id"])
                for page in pages
                for item in page.get("focus_items", [])
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ],
            "issues": [],
        }
        utterances = enumerate_utterances(document)
        # A stable item key may legitimately acquire new spoken text when a
        # TTS-only pronunciation rule evolves (for example x축 -> 엑스축).
        # ``synthesize_all`` already reuses only exact text matches and safely
        # regenerates a mismatched key, so do not reject such revisions as ID
        # collisions.
        audio_index = synthesize_all(
            utterances,
            self.synthesize,
            staging,
            existing_index,
            log_fn=lambda _message: None,
        )
        ensure_system_pool(
            self.synthesize,
            self.datapacks_root / "_system",
            log_fn=lambda _message: None,
        )
        validation_summary: dict[str, object] = {
            "schema_valid": True,
            "incremental_fragment_count": len(new_pages),
            "fragment_validations": validations,
        }
        manifest = build_manifest(
            book_id=datapack_id,
            title=title,
            page_ids=[str(page["page_id"]) for page in pages],
            created_at=created_at,
            engine_manifest={
                "pipeline": {"mode": "incremental_spread_s1"},
                "fragments": parser_engines,
            },
            tts_manifest=self.tts_manifest,
            validation_summary=validation_summary,
        )
        manifest["revision"] = target_revision
        manifest["base_revision"] = base_revision
        manifest["incremental_provenance"] = {
            "scan_session_id": scan_session_id,
            "through_sequence": through_sequence,
            "fragment_page_ids": [str(page["page_id"]) for page in new_pages],
        }
        manifest["audio_sha256"] = _audio_hashes(staging, audio_index)
        _write_json(staging / "document.json", document)
        _write_json(staging / "audio_index.json", {"schema_version": 1, "utterances": audio_index})
        _write_json(staging / "manifest.json", manifest)
        self.validate(staging, datapack_id)
        return _sha256_file(staging / "manifest.json")

    def validate(self, root: Path, datapack_id: str) -> None:
        manifest = _read_json(root / "manifest.json")
        document = _read_json(root / "document.json")
        audio = _read_audio_index(root / "audio_index.json")
        audio_hashes = manifest.get("audio_sha256")
        pages = document.get("pages")
        if manifest.get("book_id") != datapack_id or document.get("document_id") != datapack_id:
            raise S0ConflictError("REVISION_IDENTITY_MISMATCH", "staging datapack identity differs")
        if not isinstance(pages, list):
            raise S0ValidationError("REVISION_DOCUMENT_INVALID", "staging pages are invalid")
        _validate_pages([page for page in pages if isinstance(page, dict)])
        page_ids = [page.get("page_id") for page in pages if isinstance(page, dict)]
        if manifest.get("page_ids") != page_ids:
            raise S0ConflictError("REVISION_PAGE_ORDER_MISMATCH", "manifest and document page order differ")
        utterances = enumerate_utterances(document)
        if set(audio) != set(utterances):
            raise S0ConflictError("REVISION_AUDIO_INDEX_MISMATCH", "audio keys do not cover the document")
        expected_audio_paths: set[str] = set()
        if not isinstance(audio_hashes, dict) or any(
            not isinstance(path, str) or not isinstance(digest, str)
            for path, digest in audio_hashes.items()
        ):
            raise S0ValidationError("REVISION_AUDIO_HASHES_INVALID", "audio SHA-256 map is invalid")
        for key, text in utterances.items():
            entry = audio[key]
            if entry.get("text") != text:
                raise S0ConflictError("REVISION_AUDIO_TEXT_MISMATCH", "audio text differs")
            wav = _safe_relative(entry.get("wav"))
            path = (root / wav).resolve()
            _require_confined(path, root.resolve())
            if not path.is_file():
                raise S0ValidationError("REVISION_AUDIO_MISSING", "revision WAV file is missing")
            normalized = wav.as_posix()
            expected_audio_paths.add(normalized)
            if audio_hashes.get(normalized) != _sha256_file(path):
                raise S0ConflictError("REVISION_AUDIO_HASH_MISMATCH", "revision WAV hash differs")
            _validate_wav(path, entry)
        if set(audio_hashes) != expected_audio_paths:
            raise S0ConflictError(
                "REVISION_AUDIO_HASH_SET_MISMATCH",
                "audio SHA-256 map does not exactly cover the audio index",
            )
        datapack = load_datapack(root, self.datapacks_root / "_system")
        DatapackSession(datapack)
        preflight = preflight_datapack_root(
            root,
            self.datapacks_root / "_system",
            expected_datapack_id=datapack_id,
        )
        if preflight["error_count"]:
            codes = sorted({issue["code"] for issue in preflight["issues"] if issue["severity"] == "error"})
            raise S0ValidationError(
                "REVISION_PREFLIGHT_FAILED",
                f"serving preflight failed: {', '.join(codes)}",
            )

    def _copy_existing_audio(
        self,
        base_root: Path,
        staging: Path,
        existing_index: dict[str, dict[str, Any]],
    ) -> None:
        copied: set[Path] = set()
        for entry in existing_index.values():
            relative = _safe_relative(entry.get("wav"))
            if relative in copied:
                continue
            source = (base_root / relative).resolve()
            _require_confined(source, base_root)
            if not source.is_file():
                raise S0ValidationError("BASE_AUDIO_MISSING", "base audio file is missing")
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.add(relative)


def _validate_pages(pages: list[dict[str, object]]) -> None:
    page_ids: set[str] = set()
    item_ids: set[str] = set()
    for page in pages:
        page_id = page.get("page_id")
        if not isinstance(page_id, str) or not page_id or page_id in page_ids:
            raise S0ConflictError("REVISION_PAGE_ID_COLLISION", "page IDs must be unique and non-empty")
        page_ids.add(page_id)
        items = page.get("focus_items")
        if not isinstance(items, list) or not items:
            raise S0ValidationError("REVISION_EMPTY_PAGE", "each page must contain focus items")
        for item in items:
            item_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(item_id, str) or not item_id or item_id in item_ids:
                raise S0ConflictError("REVISION_ITEM_ID_COLLISION", "focus item IDs must be unique")
            if item.get("page_id") != page_id:
                raise S0ConflictError("REVISION_ITEM_PAGE_MISMATCH", "focus item page ID differs")
            item_ids.add(item_id)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise S0ValidationError("REVISION_JSON_INVALID", f"invalid JSON file: {path.name}") from exc
    if not isinstance(value, dict):
        raise S0ValidationError("REVISION_JSON_INVALID", f"JSON root must be an object: {path.name}")
    return value


def _read_audio_index(path: Path) -> dict[str, dict[str, Any]]:
    value = _read_json(path).get("utterances")
    if not isinstance(value, dict) or any(not isinstance(entry, dict) for entry in value.values()):
        raise S0ValidationError("AUDIO_INDEX_INVALID", "audio index utterances are invalid")
    return value


def _json_or_empty(value: object) -> object:
    if not isinstance(value, str):
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _safe_relative(value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise S0ValidationError("REVISION_PATH_INVALID", "revision path must be relative")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise S0ValidationError("REVISION_PATH_INVALID", "revision path escapes root")
    return path


def _require_confined(path: Path, root: Path) -> None:
    root = root.resolve()
    path = path.resolve()
    if path != root and root not in path.parents:
        raise S0ValidationError("REVISION_PATH_INVALID", "revision path escapes root")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audio_hashes(root: Path, audio_index: dict[str, dict[str, Any]]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for entry in audio_index.values():
        relative = _safe_relative(entry.get("wav"))
        normalized = relative.as_posix()
        path = (root / relative).resolve()
        _require_confined(path, root.resolve())
        if not path.is_file():
            raise S0ValidationError("REVISION_AUDIO_MISSING", "revision WAV file is missing")
        digest = _sha256_file(path)
        existing = hashes.setdefault(normalized, digest)
        if existing != digest:
            raise S0ConflictError("REVISION_AUDIO_PATH_COLLISION", "audio path has conflicting content")
    return dict(sorted(hashes.items()))


def _validate_wav(path: Path, entry: dict[str, Any]) -> None:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frame_count = handle.getnframes()
    except (OSError, EOFError, wave.Error) as exc:
        raise S0ValidationError("REVISION_AUDIO_DECODE_FAILED", "revision WAV cannot decode") from exc
    if channels < 1 or sample_width != 2 or sample_rate < 1 or frame_count < 1:
        raise S0ValidationError("REVISION_AUDIO_FORMAT_INVALID", "revision WAV format is invalid")
    if entry.get("sample_rate") != sample_rate:
        raise S0ConflictError("REVISION_AUDIO_RATE_MISMATCH", "audio sample rate metadata differs")
    duration_ms = round(frame_count / sample_rate * 1000)
    if entry.get("duration_ms") != duration_ms:
        raise S0ConflictError("REVISION_AUDIO_DURATION_MISMATCH", "audio duration metadata differs")
