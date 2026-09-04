"""HTTP transport for health compatibility and authenticated device presence."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from asl_device.connectivity import FatalConnectivityError, RetryableConnectivityError

WireTransport = Callable[
    [str, str, dict[str, Any] | None, dict[str, str], float],
    tuple[int, dict[str, Any]],
]


class HttpConnectivityTransport:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 10.0,
        health_timeout_seconds: float | None = None,
        transport: WireTransport | None = None,
        minimum_schema_version: int = 3,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be an HTTP(S) URL")
        if not api_key:
            raise ValueError("api_key must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if minimum_schema_version < 1:
            raise ValueError("minimum_schema_version must be positive")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.health_timeout_seconds = (
            timeout_seconds if health_timeout_seconds is None else health_timeout_seconds
        )
        if self.health_timeout_seconds <= 0:
            raise ValueError("health_timeout_seconds must be positive")
        self.minimum_schema_version = minimum_schema_version
        self._transport = transport or self._urllib_transport

    def __repr__(self) -> str:
        return (
            f"HttpConnectivityTransport(base_url={self.base_url!r}, "
            f"timeout_seconds={self.timeout_seconds!r})"
        )

    def probe_health(self) -> dict[str, object]:
        body = self._call(
            "GET",
            "/api/v1/health",
            authenticated=False,
            timeout_seconds=self.health_timeout_seconds,
        )
        if body.get("status") != "ok" or body.get("service") != "asl-ocr-server":
            raise FatalConnectivityError("configured endpoint is not a healthy ASL OCR server", code="SERVER_INCOMPATIBLE")
        versions = body.get("api_versions")
        schema = body.get("schema_version")
        if not isinstance(versions, list) or "v1" not in versions:
            raise FatalConnectivityError("server does not support API v1", code="SERVER_INCOMPATIBLE")
        if isinstance(schema, bool) or not isinstance(schema, int) or schema < self.minimum_schema_version:
            raise FatalConnectivityError("server schema is incompatible", code="SERVER_INCOMPATIBLE")
        return body

    def start_presence(
        self,
        *,
        device_id: str,
        presence_session_id: str,
        boot_id: str,
        client_version: str,
        platform: str,
        capabilities: tuple[str, ...],
    ) -> dict[str, object]:
        return self._call(
            "POST",
            f"/api/v1/devices/{_quote(device_id)}/presence-sessions",
            {
                "presence_session_id": presence_session_id,
                "boot_id": boot_id,
                "heartbeat_sequence": 0,
                "client_version": client_version,
                "platform": platform,
                "capabilities": list(capabilities),
            },
        )

    def heartbeat(
        self,
        *,
        device_id: str,
        presence_session_id: str,
        boot_id: str,
        sequence: int,
    ) -> dict[str, object]:
        return self._call(
            "PUT",
            f"/api/v1/devices/{_quote(device_id)}/presence-sessions/{_quote(presence_session_id)}",
            {
                "boot_id": boot_id,
                "heartbeat_sequence": sequence,
                "connection_state": "online",
            },
        )

    def disconnect(self, *, device_id: str, presence_session_id: str) -> None:
        self._call(
            "DELETE",
            f"/api/v1/devices/{_quote(device_id)}/presence-sessions/{_quote(presence_session_id)}",
        )

    def _call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["X-API-Key"] = self._api_key
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            status, body = self._transport(
                method,
                path,
                payload,
                headers,
                self.timeout_seconds if timeout_seconds is None else timeout_seconds,
            )
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise RetryableConnectivityError(f"server transport unavailable: {exc}") from exc
        if status in {408, 429} or status >= 500:
            message = (
                str(body.get("message") or body.get("code") or f"HTTP {status}")
                if isinstance(body, dict)
                else f"HTTP {status}"
            )
            raise RetryableConnectivityError(message)
        if not isinstance(body, dict):
            raise FatalConnectivityError("server response is not a JSON object", code="SERVER_INCOMPATIBLE")
        if 200 <= status < 300:
            return body
        message = str(body.get("message") or body.get("code") or f"HTTP {status}")
        if status in {401, 403}:
            raise FatalConnectivityError(message, code="SERVER_AUTH_FAILED")
        if status == 404:
            raise FatalConnectivityError(message, code="SERVER_INCOMPATIBLE")
        if bool(body.get("retryable")):
            raise RetryableConnectivityError(message)
        raise FatalConnectivityError(message, code="SERVER_INCOMPATIBLE")

    def _urllib_transport(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> tuple[int, dict[str, Any]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        opener = urllib.request.build_opener(_NoRedirectHandler())
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(64 * 1024 + 1)
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read(64 * 1024 + 1)
            status = exc.code
        # Proxies may return plain text, HTML, or empty error responses when
        # the server is offline. Classify transient HTTP failures before JSON
        # validation, which is only evidence of incompatibility on other paths.
        if status in {408, 429} or status >= 500:
            raise RetryableConnectivityError(f"HTTP {status}: server temporarily unavailable")
        if len(raw) > 64 * 1024:
            raise FatalConnectivityError("server response exceeds 64 KiB", code="SERVER_INCOMPATIBLE")
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FatalConnectivityError("server response is not valid UTF-8 JSON", code="SERVER_INCOMPATIBLE") from exc
        return status, body


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _quote(value: str) -> str:
    return quote(value, safe="")
