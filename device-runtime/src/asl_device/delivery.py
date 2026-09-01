"""Poll-driven single-sender implementation of the DeliveryPort contract."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Protocol

from .delivery_config import DeviceDeliveryConfig
from .delivery_domain import (
    PreparedDelivery,
    V4HttpResponse,
    V4TransportError,
    prepare_delivery,
    verify_prepared,
)
from .delivery_store import DeliveryStore
from .protocols import FatalPortError, RecoverablePortError
from .types import (
    ArtifactId,
    ClientSpreadSequence,
    DeliveryStatus,
    DeliveryUpdate,
    DeviceId,
    FlushResult,
    FlushStatus,
    ScanSessionId,
    ScannerArtifactReady,
)


class UploadTransport(Protocol):
    def upload(self, prepared: PreparedDelivery) -> V4HttpResponse: ...


class DurableDeliveryPort:
    def __init__(
        self,
        device_id: DeviceId,
        config: DeviceDeliveryConfig,
        store: DeliveryStore,
        transport: UploadTransport,
        clock: Callable[[], float],
        *,
        before_ack_commit: Callable[[], None] | None = None,
    ) -> None:
        if not isinstance(device_id, DeviceId):
            raise TypeError("device_id must be a DeviceId")
        self.device_id = device_id
        self.config = config
        self.store = store
        self.transport = transport
        self.clock = clock
        self._next_attempt: dict[str, float] = {}
        self._before_ack_commit = before_ack_commit
        self.config.artifact_root.mkdir(parents=True, exist_ok=True)

    def queue(
        self,
        scan_session_id: ScanSessionId,
        sequence: ClientSpreadSequence,
        artifact: ScannerArtifactReady,
    ) -> DeliveryUpdate:
        existing = self.store.find_position(scan_session_id.value, sequence.value)
        if existing is not None:
            if (
                existing["artifact_id"] != artifact.artifact_id.value
                or existing["manifest_sha256"] != artifact.manifest_sha256
            ):
                raise FatalPortError("delivery position already belongs to different content")
            return _update(existing)
        prepared = prepare_delivery(self.config, self.device_id, scan_session_id, sequence, artifact)
        return _update(self.store.enqueue(prepared))

    def pending_status(self, scan_session_id: ScanSessionId) -> tuple[DeliveryUpdate, ...]:
        self._advance_one(scan_session_id)
        return tuple(_update(row) for row in self.store.list_scan(scan_session_id.value))

    def flush_through(self, scan_session_id: ScanSessionId, through_sequence: int) -> FlushResult:
        if isinstance(through_sequence, bool) or not isinstance(through_sequence, int) or through_sequence < 0:
            raise ValueError("through_sequence must be a non-negative integer")
        self._advance_one(scan_session_id)
        rows = {int(row["sequence"]): row for row in self.store.list_scan(scan_session_id.value)}
        relevant = [rows.get(sequence) for sequence in range(1, through_sequence + 1)]
        if any(row is not None and row["status"] == "rejected" for row in relevant):
            reason = next(
                str(row["last_error_detail"] or row["last_error_code"] or "delivery rejected")
                for row in relevant
                if row is not None and row["status"] == "rejected"
            )
            return FlushResult(scan_session_id, through_sequence, FlushStatus.BLOCKED, reason)
        if all(row is not None and row["status"] == "acked" for row in relevant):
            return FlushResult(scan_session_id, through_sequence, FlushStatus.FLUSHED)
        return FlushResult(scan_session_id, through_sequence, FlushStatus.PENDING)

    def _advance_one(self, scan_session_id: ScanSessionId) -> None:
        row = self.store.next_nonterminal(scan_session_id.value)
        if row is None:
            return
        outbox_id = str(row["outbox_id"])
        if self.clock() < self._next_attempt.get(outbox_id, 0.0):
            return
        claimed = self.store.claim(outbox_id)
        if claimed is None:
            return
        prepared = self.store.prepared(claimed)
        try:
            verify_prepared(self.config, prepared)
        except FatalPortError as exc:
            self.store.reject(
                outbox_id,
                code="LOCAL_ARTIFACT_INVALID",
                detail=str(exc),
                http_status=0,
            )
            return
        try:
            response = self.transport.upload(prepared)
        except V4TransportError as exc:
            self._retry(claimed, "TRANSPORT_UNAVAILABLE", str(exc), None, None)
            return
        except FatalPortError as exc:
            self.store.retry(
                outbox_id,
                code="SERVER_RESPONSE_INVALID",
                detail=str(exc),
            )
            raise
        except (OSError, TimeoutError) as exc:
            self._retry(claimed, "TRANSPORT_UNAVAILABLE", str(exc), None, None)
            return
        self._handle_response(claimed, prepared, response)

    def _handle_response(
        self,
        row,
        prepared: PreparedDelivery,
        response: V4HttpResponse,
    ) -> None:
        outbox_id = str(row["outbox_id"])
        body = response.body
        if 200 <= response.status < 300:
            try:
                receipt_id, accepted_at = _validated_receipt(prepared, body)
            except FatalPortError as exc:
                self.store.retry(
                    outbox_id,
                    code="RECEIPT_IDENTITY_MISMATCH",
                    detail=str(exc),
                    http_status=response.status,
                )
                raise
            if self._before_ack_commit is not None:
                self._before_ack_commit()
            self.store.acknowledge(
                outbox_id,
                receipt_id=receipt_id,
                accepted_at=accepted_at,
                http_status=response.status,
            )
            self._next_attempt.pop(outbox_id, None)
            self._cleanup_acked(outbox_id, prepared)
            return
        code = str(body.get("code") or f"HTTP_{response.status}")
        detail = str(body.get("message") or code)
        if response.status in {401, 403}:
            self.store.retry(outbox_id, code=code, detail=detail, http_status=response.status)
            raise FatalPortError("Server V4 authentication failed")
        if bool(body.get("retryable")) or response.status >= 500 or response.status in {408, 429}:
            self._retry(row, code, detail, response.status, response.retry_after_seconds)
            return
        self.store.reject(outbox_id, code=code, detail=detail, http_status=response.status)
        self._next_attempt.pop(outbox_id, None)

    def _retry(
        self,
        row,
        code: str,
        detail: str,
        http_status: int | None,
        retry_after_seconds: float | None,
    ) -> None:
        outbox_id = str(row["outbox_id"])
        self.store.retry(outbox_id, code=code, detail=detail, http_status=http_status)
        attempts = max(1, int(row["attempt_count"]))
        delay = min(
            self.config.retry_max_seconds,
            self.config.retry_initial_seconds * (2 ** (attempts - 1)),
        )
        if retry_after_seconds is not None:
            delay = max(delay, retry_after_seconds)
        self._next_attempt[outbox_id] = self.clock() + delay

    def _cleanup_acked(self, outbox_id: str, prepared: PreparedDelivery) -> None:
        root = Path(prepared.manifest_path).parent
        expected = self.config.artifact_root / prepared.artifact_id
        if (
            root != expected
            or root.parent != self.config.artifact_root
            or _is_link_like(root)
            or root.resolve() != root
        ):
            self.store.set_cleanup_error(outbox_id, "refused artifact cleanup outside configured root")
            return
        try:
            if root.exists():
                shutil.rmtree(root)
        except OSError as exc:
            self.store.set_cleanup_error(outbox_id, f"{type(exc).__name__}: {exc}")
        else:
            self.store.set_cleanup_error(outbox_id, None)


def _validated_receipt(
    prepared: PreparedDelivery,
    body,
) -> tuple[str, str]:
    expected = {
        "status": "acked",
        "scan_session_id": prepared.scan_session_id,
        "sequence": prepared.sequence,
        "artifact_id": prepared.artifact_id,
        "manifest_sha256": prepared.manifest_sha256,
        "upload_digest": prepared.upload_digest,
    }
    if any(body.get(field) != value for field, value in expected.items()):
        raise FatalPortError("Server V4 success receipt identity does not match outbox row")
    receipt_id = body.get("receipt_id")
    accepted_at = body.get("accepted_at")
    if not isinstance(receipt_id, str) or not receipt_id or not isinstance(accepted_at, str) or not accepted_at:
        raise FatalPortError("Server V4 success receipt is incomplete")
    return receipt_id, accepted_at


def _update(row) -> DeliveryUpdate:
    status = DeliveryStatus(str(row["status"]))
    reason = None
    if status is DeliveryStatus.REJECTED:
        reason = str(row["last_error_detail"] or row["last_error_code"] or "delivery rejected")
    return DeliveryUpdate(
        ScanSessionId(str(row["scan_session_id"])),
        ClientSpreadSequence(int(row["sequence"])),
        ArtifactId(str(row["artifact_id"])),
        status,
        receipt_id=str(row["receipt_id"]) if row["receipt_id"] is not None else None,
        reason=reason,
    )


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction is not None and is_junction(path))
