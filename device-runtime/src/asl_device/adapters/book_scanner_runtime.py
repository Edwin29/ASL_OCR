"""Concrete bridge from the Book Scanner engine to the Device ScannerRuntime port."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Protocol

from asl_device.protocols import FatalPortError
from asl_device.types import (
    ArtifactId,
    DeliveryStatus,
    DeliveryUpdate,
    ScanSessionRef,
    ScannerArtifactReady,
    ScannerEvent,
    ScannerEventType,
)


class BookScannerEngine(Protocol):
    @property
    def pending_artifact(self) -> Any | None: ...

    def start(self) -> tuple[Any, ...]: ...

    def poll(self) -> tuple[Any, ...]: ...

    def delivery_queued(self, artifact_id: Any) -> tuple[Any, ...]: ...

    def delivery_retrying(self, artifact_id: Any) -> tuple[Any, ...]: ...

    def delivery_confirmed(self, artifact_id: Any, receipt_id: str) -> tuple[Any, ...]: ...

    def delivery_rejected(self, artifact_id: Any, reason: str) -> tuple[Any, ...]: ...

    def cancel(self) -> tuple[Any, ...]: ...

    def close(self) -> None: ...


class BookScannerEngineFactory(Protocol):
    def create(self, *, session_id: str, datapack_id: str) -> BookScannerEngine: ...


class BookScannerRuntimeAdapter:
    """Own exactly one scan-session-scoped engine and preserve its delivery lineage."""

    def __init__(self, factory: BookScannerEngineFactory, artifact_root: Path) -> None:
        self.factory = factory
        self.artifact_root = Path(artifact_root).resolve()
        self._engine: BookScannerEngine | None = None
        self._scan_session: ScanSessionRef | None = None
        self._artifact_ids: dict[str, Any] = {}
        self._terminal_artifacts: set[str] = set()
        self._frozen = False

    def start(self, scan_session: ScanSessionRef) -> None:
        if not isinstance(scan_session, ScanSessionRef):
            raise TypeError("scan_session must be a ScanSessionRef")
        if self._engine is not None:
            raise FatalPortError("Book Scanner engine is already active")
        engine: BookScannerEngine | None = None
        try:
            engine = self.factory.create(
                session_id=scan_session.scan_session_id.value,
                datapack_id=scan_session.datapack_id.value,
            )
            engine.start()
        except FatalPortError:
            raise
        except Exception as exc:
            try:
                if engine is not None:
                    engine.close()
            except Exception:
                pass
            raise FatalPortError(f"cannot start Book Scanner engine: {type(exc).__name__}") from exc
        self._engine = engine
        self._scan_session = scan_session
        self._artifact_ids.clear()
        self._terminal_artifacts.clear()
        self._frozen = False

    def poll(self) -> tuple[ScannerEvent, ...]:
        if self._engine is None or self._scan_session is None or self._frozen:
            return ()
        try:
            events = self._engine.poll()
        except Exception as exc:
            raise FatalPortError(f"Book Scanner poll failed: {type(exc).__name__}") from exc
        try:
            mapped: list[ScannerEvent] = []
            for event in events:
                converted = self._convert_event(event)
                if converted is not None:
                    mapped.append(converted)
            return tuple(mapped)
        except FatalPortError:
            raise
        except Exception as exc:
            raise FatalPortError(
                f"Book Scanner event mapping failed: {type(exc).__name__}"
            ) from exc

    def freeze(self) -> None:
        self._frozen = True
        if self._engine is not None and self._engine.pending_artifact is None:
            self._close_engine(cancel=True)

    def cancel(self) -> None:
        self._frozen = True
        self._close_engine(cancel=True)

    def close(self) -> None:
        self.cancel()

    def apply_delivery_update(self, artifact_id: ArtifactId, update: DeliveryUpdate) -> None:
        if not isinstance(artifact_id, ArtifactId) or not isinstance(update, DeliveryUpdate):
            raise TypeError("artifact_id and update must be Device Runtime domain values")
        session = self._scan_session
        engine = self._engine
        if session is None or engine is None:
            return
        if update.scan_session_id != session.scan_session_id or update.artifact_id != artifact_id:
            return
        key = artifact_id.value
        scanner_artifact_id = self._artifact_ids.get(key)
        if scanner_artifact_id is None:
            return
        if key in self._terminal_artifacts:
            return
        try:
            if update.status in {DeliveryStatus.QUEUED, DeliveryStatus.SENDING}:
                engine.delivery_queued(scanner_artifact_id)
            elif update.status is DeliveryStatus.RETRYING:
                engine.delivery_retrying(scanner_artifact_id)
            elif update.status is DeliveryStatus.ACKED:
                if not update.receipt_id:
                    raise FatalPortError("ACKED delivery update has no receipt")
                events = engine.delivery_confirmed(scanner_artifact_id, update.receipt_id)
                self._require_terminal_event(events, "delivery_confirmed")
                self._terminal_artifacts.add(key)
            elif update.status is DeliveryStatus.REJECTED:
                reason = update.reason or "delivery rejected"
                events = engine.delivery_rejected(scanner_artifact_id, reason)
                self._require_terminal_event(events, "parser_rejected")
                self._terminal_artifacts.add(key)
        except FatalPortError:
            raise
        except Exception as exc:
            raise FatalPortError(
                f"Book Scanner delivery callback failed: {type(exc).__name__}"
            ) from exc
        if self._frozen and key in self._terminal_artifacts:
            self._close_engine(cancel=True)

    def _convert_event(self, event: Any) -> ScannerEvent | None:
        session = self._scan_session
        engine = self._engine
        assert session is not None and engine is not None
        event_type = _enum_value(getattr(event, "event_type", None))
        event_session = getattr(event, "session_id", None)
        if event_session != session.scan_session_id.value:
            raise FatalPortError("Book Scanner event session does not match active scan")
        event_id = getattr(event, "event_id", None)
        if not isinstance(event_id, str) or not event_id:
            raise FatalPortError("Book Scanner event has no stable event ID")
        details = _details(getattr(event, "details", ()))
        if event_type == "artifact_ready":
            artifact = engine.pending_artifact
            if artifact is None:
                raise FatalPortError("Book Scanner ARTIFACT_READY has no pending artifact")
            source = _enum_value(getattr(artifact, "source_frame_id", None))
            spread = _enum_value(getattr(artifact, "spread_id", None))
            scanner_id = getattr(artifact, "artifact_id", None)
            artifact_value = _enum_value(scanner_id)
            if (
                artifact_value != _enum_value(getattr(event, "artifact_id", None))
                or source != _enum_value(getattr(event, "source_frame_id", None))
                or spread != _enum_value(getattr(event, "spread_id", None))
            ):
                raise FatalPortError("Book Scanner artifact event lineage is inconsistent")
            artifact_component = Path(artifact_value)
            if (
                not artifact_value
                or artifact_component.is_absolute()
                or artifact_component.name != artifact_value
                or artifact_value in {".", ".."}
            ):
                raise FatalPortError("Book Scanner artifact ID is not one safe path component")
            manifest_path = Path(os.path.abspath(getattr(artifact, "manifest_path", "")))
            expected_root = self.artifact_root / artifact_value
            if (
                expected_root.parent != self.artifact_root
                or manifest_path != expected_root / "manifest.json"
                or manifest_path.parent != expected_root
                or _is_link_like(expected_root)
                or expected_root.resolve() != expected_root
            ):
                raise FatalPortError("Book Scanner manifest escaped the configured artifact root")
            manifest_sha = getattr(artifact, "manifest_sha256", None)
            if not isinstance(manifest_sha, str) or _sha256_file(manifest_path) != manifest_sha:
                raise FatalPortError("Book Scanner manifest identity is invalid")
            device_artifact_id = ArtifactId(artifact_value)
            self._artifact_ids[artifact_value] = scanner_id
            return ScannerEvent(
                event_id,
                session.scan_session_id,
                ScannerEventType.ARTIFACT_READY,
                ScannerArtifactReady(
                    session.scan_session_id,
                    device_artifact_id,
                    spread,
                    source,
                    str(manifest_path),
                    manifest_sha,
                ),
                details=details,
            )
        if event_type == "guidance_requested":
            return ScannerEvent(
                event_id,
                session.scan_session_id,
                ScannerEventType.GUIDANCE,
                code=_reason_value(event, "scanner_guidance"),
                details=details,
            )
        if event_type == "session_error":
            return ScannerEvent(
                event_id,
                session.scan_session_id,
                ScannerEventType.FATAL,
                code=_reason_value(event, "scanner_session_error"),
                details=details,
            )
        return None

    def _close_engine(self, *, cancel: bool) -> None:
        engine, self._engine = self._engine, None
        self._scan_session = None
        if engine is None:
            return
        try:
            if cancel:
                engine.cancel()
        finally:
            engine.close()

    @staticmethod
    def _require_terminal_event(events: tuple[Any, ...], expected: str) -> None:
        if not any(_enum_value(getattr(event, "event_type", None)) == expected for event in events):
            raise FatalPortError(f"Book Scanner did not confirm terminal transition: {expected}")


def _enum_value(value: Any) -> str:
    nested = getattr(value, "value", value)
    return nested if isinstance(nested, str) else ""


def _reason_value(event: Any, fallback: str) -> str:
    value = _enum_value(getattr(event, "reason", None))
    return value or fallback


def _details(value: Any) -> tuple[tuple[str, str | int | float | bool | None], ...]:
    try:
        items = dict(value).items()
    except (TypeError, ValueError):
        return ()
    return tuple(
        (str(key), item)
        for key, item in items
        if isinstance(item, (str, int, float, bool)) or item is None
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FatalPortError("Book Scanner manifest cannot be read") from exc
    return digest.hexdigest()


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction is not None and is_junction(path))
