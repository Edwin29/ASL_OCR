"""Dependency-free HTTP client for the Server S0 Catalog/Scan/Reading ports."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from asl_device.protocols import FatalPortError, RecoverablePortError
from asl_device.types import (
    CatalogEntry,
    DatapackId,
    DatapackRevision,
    DatapackStatus,
    DeviceControl,
    DeviceId,
    FinalizeResult,
    FinalizeStatus,
    InputAction,
    ReadingSessionId,
    ReadingSnapshot,
    ScanSessionId,
    ScanSessionRef,
    ScanSessionStatus,
)

Transport = Callable[[str, str, dict[str, Any] | None, dict[str, str]], tuple[int, dict[str, Any]]]


class S0HttpClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 10.0,
        transport: Transport | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be an HTTP(S) URL")
        if not api_key:
            raise ValueError("api_key must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._transport = transport or self._urllib_transport

    def list_datapacks(self, device_id: DeviceId) -> tuple[CatalogEntry, ...]:
        body = self._call("GET", f"/api/v1/devices/{_quote(device_id.value)}/datapacks")
        rows = body.get("datapacks")
        if not isinstance(rows, list):
            raise FatalPortError("server catalog response is malformed")
        return tuple(_catalog(row) for row in rows)

    def create_datapack(self, device_id: DeviceId, operation_id: str) -> CatalogEntry:
        body = self._call(
            "POST",
            f"/api/v1/devices/{_quote(device_id.value)}/datapacks",
            {},
            operation_id,
        )
        return _catalog(body)

    def open_scan(
        self,
        device_id: DeviceId,
        datapack_id: DatapackId,
        operation_id: str,
    ) -> ScanSessionRef:
        body = self._call(
            "POST",
            f"/api/v1/datapacks/{_quote(datapack_id.value)}/scan-sessions",
            {"device_id": device_id.value},
            operation_id,
        )
        return _scan(body)

    def open_reading(
        self,
        device_id: DeviceId,
        datapack_id: DatapackId,
        viewport_size: int,
        operation_id: str,
    ) -> ReadingSnapshot:
        body = self._call(
            "POST",
            "/api/v1/reading-sessions",
            {
                "device_id": device_id.value,
                "datapack_id": datapack_id.value,
                "viewport_size": viewport_size,
            },
            operation_id,
        )
        return _reading(body)

    def seal(self, scan_session_id: ScanSessionId, through_sequence: int) -> FinalizeResult:
        body = self._call(
            "POST",
            f"/api/v1/scan-sessions/{_quote(scan_session_id.value)}/seal-intent",
            {"through_sequence": through_sequence},
        )
        return _finalization(body)

    def get_status(self, scan_session_id: ScanSessionId) -> FinalizeResult:
        body = self._call("GET", f"/api/v1/scan-sessions/{_quote(scan_session_id.value)}")
        return _finalization(body)

    def get_current(self, reading_session_id: ReadingSessionId) -> ReadingSnapshot:
        body = self._call(
            "GET", f"/api/v1/reading-sessions/{_quote(reading_session_id.value)}"
        )
        return _reading(body)

    def send_command(
        self,
        reading_session_id: ReadingSessionId,
        command_id: str,
        control: DeviceControl,
        action: InputAction,
    ) -> ReadingSnapshot:
        body = self._call(
            "POST",
            f"/api/v1/reading-sessions/{_quote(reading_session_id.value)}/commands",
            {
                "command_id": command_id,
                "button": control.value.upper(),
                "action": action.value.upper(),
            },
        )
        return _reading(body)

    def _call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"X-API-Key": self.api_key, "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        try:
            status, body = self._transport(method, path, payload, headers)
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise RecoverablePortError(f"server transport unavailable: {exc}") from exc
        if not isinstance(body, dict):
            raise FatalPortError("server response must be a JSON object")
        if 200 <= status < 300:
            return body
        message = str(body.get("message") or body.get("code") or f"HTTP {status}")
        if bool(body.get("retryable")) or status >= 500 or status in {408, 429}:
            raise RecoverablePortError(message)
        if status in {404, 409}:
            raise RecoverablePortError(message)
        raise FatalPortError(message)

    def _urllib_transport(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> tuple[int, dict[str, Any]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FatalPortError("server response is not valid UTF-8 JSON") from exc
        return status, body


class S0CatalogHttpAdapter:
    def __init__(self, client: S0HttpClient) -> None:
        self.client = client

    def list_datapacks(self, device_id: DeviceId) -> tuple[CatalogEntry, ...]:
        return self.client.list_datapacks(device_id)

    def create_datapack(self, device_id: DeviceId, operation_id: str) -> CatalogEntry:
        return self.client.create_datapack(device_id, operation_id)


class S0ScanHttpAdapter:
    def __init__(self, client: S0HttpClient) -> None:
        self.client = client

    def open(
        self, device_id: DeviceId, datapack_id: DatapackId, operation_id: str
    ) -> ScanSessionRef:
        return self.client.open_scan(device_id, datapack_id, operation_id)

    def seal(self, scan_session_id: ScanSessionId, through_sequence: int) -> FinalizeResult:
        return self.client.seal(scan_session_id, through_sequence)

    def get_status(self, scan_session_id: ScanSessionId) -> FinalizeResult:
        return self.client.get_status(scan_session_id)


class S0ReadingHttpAdapter:
    def __init__(self, client: S0HttpClient) -> None:
        self.client = client

    def open(
        self,
        device_id: DeviceId,
        datapack_id: DatapackId,
        viewport_size: int,
        operation_id: str,
    ) -> ReadingSnapshot:
        return self.client.open_reading(
            device_id, datapack_id, viewport_size, operation_id
        )

    def get_current(self, reading_session_id: ReadingSessionId) -> ReadingSnapshot:
        return self.client.get_current(reading_session_id)

    def send_command(
        self,
        reading_session_id: ReadingSessionId,
        command_id: str,
        control: DeviceControl,
        action: InputAction,
    ) -> ReadingSnapshot:
        return self.client.send_command(
            reading_session_id, command_id, control, action
        )


def _catalog(value: Any) -> CatalogEntry:
    try:
        revision = value.get("revision")
        return CatalogEntry(
            DatapackId(value["datapack_id"]),
            value["title"],
            DatapackStatus(value["status"]),
            DatapackRevision(revision) if revision is not None else None,
            value.get("title_audio_ref"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FatalPortError("server catalog row is malformed") from exc


def _scan(value: Any) -> ScanSessionRef:
    try:
        return ScanSessionRef(
            ScanSessionId(value["scan_session_id"]),
            DatapackId(value["datapack_id"]),
            ScanSessionStatus(value["status"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FatalPortError("server scan response is malformed") from exc


def _finalization(value: Any) -> FinalizeResult:
    try:
        status = value["status"]
        if status in {"open", "sealing"}:
            final = FinalizeStatus.FINALIZING
        elif status == "sealed":
            final = FinalizeStatus.READY
        else:
            final = FinalizeStatus.ERROR
        revision = value.get("revision")
        return FinalizeResult(
            ScanSessionId(value["scan_session_id"]),
            DatapackId(value["datapack_id"]),
            final,
            DatapackRevision(revision) if revision is not None else None,
            value.get("error_detail") or ("scan session failed" if final is FinalizeStatus.ERROR else None),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FatalPortError("server finalization response is malformed") from exc


def _reading(value: Any) -> ReadingSnapshot:
    try:
        cursor = value["cursor"]
        frame = value["braille_frame"]
        audio = value.get("audio")
        if not isinstance(cursor, dict) or not isinstance(frame, dict):
            raise TypeError
        scalar_cursor = tuple(
            (str(key), item)
            for key, item in cursor.items()
            if isinstance(item, (str, int, float, bool)) or item is None
        )
        audio_ref = audio.get("audio_ref") if isinstance(audio, dict) else None
        return ReadingSnapshot(
            ReadingSessionId(value["reading_session_id"]),
            DatapackId(value["datapack_id"]),
            scalar_cursor,
            tuple(frame.get("cells") or ()),
            audio_ref,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FatalPortError("server reading response is malformed") from exc


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")
