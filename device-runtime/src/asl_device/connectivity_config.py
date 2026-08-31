"""Typed, secret-safe configuration for the device connectivity layer."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from .types import DeviceId


@dataclass(frozen=True, slots=True)
class DeviceConnectivityConfig:
    device_id: DeviceId
    server_base_url: str
    api_key_file: Path
    connect_timeout_seconds: float = 5.0
    request_timeout_seconds: float = 10.0
    heartbeat_interval_seconds: float = 15.0
    stale_after_seconds: float = 45.0
    offline_after_seconds: float = 120.0
    retry_initial_seconds: float = 1.0
    retry_max_seconds: float = 30.0
    retry_jitter_fraction: float = 0.20
    allow_insecure_http: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.device_id, DeviceId):
            raise TypeError("device_id must be a DeviceId")
        if not isinstance(self.allow_insecure_http, bool):
            raise TypeError("allow_insecure_http must be a boolean")
        normalized = _validate_origin(self.server_base_url, self.allow_insecure_http)
        object.__setattr__(self, "server_base_url", normalized)
        object.__setattr__(self, "api_key_file", Path(self.api_key_file).resolve())
        for name in (
            "connect_timeout_seconds",
            "request_timeout_seconds",
            "heartbeat_interval_seconds",
            "stale_after_seconds",
            "offline_after_seconds",
            "retry_initial_seconds",
            "retry_max_seconds",
        ):
            _positive_number(name, getattr(self, name))
        jitter = self.retry_jitter_fraction
        if isinstance(jitter, bool) or not isinstance(jitter, (int, float)) or not 0 <= jitter <= 1:
            raise ValueError("retry_jitter_fraction must be between 0 and 1")
        if not self.heartbeat_interval_seconds < self.stale_after_seconds < self.offline_after_seconds:
            raise ValueError("heartbeat_interval_seconds < stale_after_seconds < offline_after_seconds is required")
        if self.retry_initial_seconds > self.retry_max_seconds:
            raise ValueError("retry_initial_seconds cannot exceed retry_max_seconds")

    @classmethod
    def from_toml(
        cls,
        path: str | Path,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> "DeviceConnectivityConfig":
        config_path = Path(path).resolve()
        try:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"cannot read connectivity config: {config_path}") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("connectivity config schema_version must be 1")
        allowed = {
            "schema_version",
            "device_id",
            "server_base_url",
            "api_key_file",
            "connect_timeout_seconds",
            "request_timeout_seconds",
            "heartbeat_interval_seconds",
            "stale_after_seconds",
            "offline_after_seconds",
            "retry_initial_seconds",
            "retry_max_seconds",
            "retry_jitter_fraction",
            "allow_insecure_http",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unknown connectivity config fields: {sorted(unknown)}")
        env = os.environ if environ is None else environ
        device_value = env.get("ASL_DEVICE_ID", payload.get("device_id"))
        server_url = env.get("ASL_DEVICE_SERVER_URL", payload.get("server_base_url"))
        secret_value = env.get("ASL_DEVICE_API_KEY_FILE", payload.get("api_key_file"))
        if not isinstance(secret_value, str) or not secret_value:
            raise ValueError("api_key_file must be configured")
        secret = Path(secret_value)
        if not secret.is_absolute():
            secret = config_path.parent / secret
        secret = secret.resolve()
        root = config_path.parent.resolve()
        if secret != root and root not in secret.parents:
            raise ValueError("api_key_file must stay inside the config directory")
        kwargs = {
            key: value
            for key, value in payload.items()
            if key not in {"schema_version", "device_id", "server_base_url", "api_key_file"}
        }
        return cls(
            device_id=DeviceId(device_value),
            server_base_url=server_url,
            api_key_file=secret,
            **kwargs,
        )

    def load_api_key(self) -> str:
        try:
            value = self.api_key_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError("cannot read configured API key file") from exc
        if not value or len(value) > 4096 or any(character in value for character in "\r\n"):
            raise ValueError("configured API key is invalid")
        return value


def _validate_origin(value: object, allow_insecure_http: bool) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("server_base_url must be a non-empty URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("server_base_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("server_base_url cannot contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("server_base_url must be an origin without a path")
    if parsed.scheme == "http" and not allow_insecure_http:
        raise ValueError("HTTP requires allow_insecure_http=true")
    return value.rstrip("/")


def _positive_number(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be positive")
