"""Bounded streaming HTTP client for the Server V4 bundle endpoint."""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import uuid
from pathlib import Path
from typing import BinaryIO, Callable
from urllib.parse import quote, urlsplit

from asl_device.delivery_config import DeviceDeliveryConfig
from asl_device.delivery_domain import PreparedDelivery, V4HttpResponse, V4TransportError
from asl_device.protocols import FatalPortError


ConnectionFactory = Callable[[str, int | None, float], http.client.HTTPConnection]


class V4HttpClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        config: DeviceDeliveryConfig,
        *,
        allow_insecure_http: bool = False,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an absolute HTTP(S) origin")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("base_url must not contain path, credentials, query, or fragment")
        if parsed.scheme == "http" and not allow_insecure_http:
            raise ValueError("HTTP requires allow_insecure_http=true")
        if not api_key or any(character in api_key for character in "\r\n"):
            raise ValueError("api_key is invalid")
        self._scheme = parsed.scheme
        self._host = parsed.hostname
        self._port = parsed.port
        self._api_key = api_key
        self.config = config
        self._connection_factory = connection_factory

    def __repr__(self) -> str:
        return f"V4HttpClient(origin={self._scheme}://{self._host}:{self._port or ''})"

    def upload(self, prepared: PreparedDelivery) -> V4HttpResponse:
        boundary = f"asl-v3b-{uuid.uuid4().hex}"
        manifest = Path(prepared.manifest_path).read_bytes()
        metadata = prepared.metadata_bytes()
        segments = _multipart_segments(prepared, boundary, metadata, manifest)
        content_length = sum(_segment_length(segment) for segment in segments)
        connection = self._connection()
        path = f"/api/v1/scan-sessions/{quote(prepared.scan_session_id, safe='')}/spreads"
        try:
            connection.putrequest("POST", path)
            connection.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
            connection.putheader("Content-Length", str(content_length))
            connection.putheader("X-API-Key", self._api_key)
            connection.putheader("Idempotency-Key", prepared.idempotency_key)
            connection.putheader("X-ASL-Upload-Digest", prepared.upload_digest)
            connection.putheader("Accept", "application/json")
            connection.endheaders()
            for segment in segments:
                if isinstance(segment, bytes):
                    connection.send(segment)
                else:
                    self._send_file(connection, segment)
            response = connection.getresponse()
            raw = response.read(self.config.response_limit_bytes + 1)
            if len(raw) > self.config.response_limit_bytes:
                raise FatalPortError("Server V4 response exceeds configured limit")
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FatalPortError("Server V4 response is not valid UTF-8 JSON") from exc
            if not isinstance(body, dict):
                raise FatalPortError("Server V4 response must be a JSON object")
            return V4HttpResponse(
                status=response.status,
                body=body,
                retry_after_seconds=_retry_after(response.getheader("Retry-After")),
            )
        except FatalPortError:
            raise
        except (OSError, TimeoutError, socket.timeout, http.client.HTTPException) as exc:
            raise V4TransportError("Server V4 upload outcome is unknown") from exc
        finally:
            connection.close()

    def _connection(self) -> http.client.HTTPConnection:
        if self._connection_factory is not None:
            return self._connection_factory(self._host, self._port, self.config.upload_timeout_seconds)
        if self._scheme == "https":
            return http.client.HTTPSConnection(
                self._host,
                self._port,
                timeout=self.config.upload_timeout_seconds,
                context=ssl.create_default_context(),
            )
        return http.client.HTTPConnection(
            self._host,
            self._port,
            timeout=self.config.upload_timeout_seconds,
        )

    def _send_file(self, connection: http.client.HTTPConnection, path: Path) -> None:
        try:
            with path.open("rb") as handle:
                _copy_chunks(handle, connection, self.config.file_chunk_bytes)
        except OSError as exc:
            raise V4TransportError("artifact file became unreadable during upload") from exc


def _multipart_segments(
    prepared: PreparedDelivery,
    boundary: str,
    metadata: bytes,
    manifest: bytes,
) -> tuple[bytes | Path, ...]:
    result: list[bytes | Path] = []
    result.extend(_memory_part(boundary, "metadata", metadata, "application/json"))
    result.extend(
        _memory_part(
            boundary,
            "manifest",
            manifest,
            "application/json",
            filename="manifest.json",
        )
    )
    for item in prepared.files:
        result.append(
            _part_header(
                boundary,
                "bundle_file",
                "application/octet-stream",
                filename=item.path,
            )
        )
        result.append(prepared.root.joinpath(*item.path.split("/")))
        result.append(b"\r\n")
    result.append(f"--{boundary}--\r\n".encode("ascii"))
    return tuple(result)


def _memory_part(
    boundary: str,
    name: str,
    body: bytes,
    content_type: str,
    *,
    filename: str | None = None,
) -> tuple[bytes, ...]:
    return (_part_header(boundary, name, content_type, filename=filename), body, b"\r\n")


def _part_header(
    boundary: str,
    name: str,
    content_type: str,
    *,
    filename: str | None = None,
) -> bytes:
    disposition = f'Content-Disposition: form-data; name="{name}"'
    if filename is not None:
        disposition += f'; filename="{filename}"'
    return (
        f"--{boundary}\r\n"
        f"{disposition}\r\n"
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("ascii")


def _segment_length(segment: bytes | Path) -> int:
    return len(segment) if isinstance(segment, bytes) else segment.stat().st_size


def _copy_chunks(
    source: BinaryIO,
    connection: http.client.HTTPConnection,
    chunk_bytes: int,
) -> None:
    while True:
        chunk = source.read(chunk_bytes)
        if not chunk:
            return
        connection.send(chunk)


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None
