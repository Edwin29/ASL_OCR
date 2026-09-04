"""Typed configuration for the E0-Core local Device application."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .connectivity_config import DeviceConnectivityConfig
from .delivery_config import DeviceDeliveryConfig


@dataclass(frozen=True, slots=True)
class ScannerHostConfig:
    profile: str
    staging_root: Path
    ready_root: Path
    uvdoc_runtime_path: Path
    uvdoc_checkpoint_path: Path
    uvdoc_device: str
    m1_model_dir: Path
    m1_model_manifest: Path
    replay_path: Path | None = None
    image_paths: tuple[Path, ...] = ()
    camera_index: int = 0
    camera_width: int | None = None
    camera_height: int | None = None
    camera_fps: float | None = None
    camera_selector: str | None = None
    camera_backend: str = "auto"
    camera_fallback_index: int | None = None
    camera_fourcc: str | None = None
    camera_rotation: int = 0
    camera_mirror: bool = False
    camera_crop_normalized: tuple[float, float, float, float] | None = None
    camera_warmup_frames: int = 3
    camera_reopen_attempts: int = 1
    camera_reopen_initial_ms: int = 250
    camera_snapshot_url: str | None = None
    camera_snapshot_username: str | None = None
    camera_snapshot_password_file: Path | None = None
    camera_snapshot_tls_ca_file: Path | None = None
    camera_snapshot_allow_insecure_tls: bool = False
    camera_snapshot_timeout_seconds: float = 8.0
    camera_snapshot_max_response_bytes: int = 32 * 1024 * 1024
    camera_snapshot_min_width: int = 1920
    camera_snapshot_min_height: int = 1080
    camera_snapshot_landscape_rotation: int | None = None
    camera_snapshot_portrait_rotation: int | None = None
    operator_preview_enabled: bool = False
    operator_preview_max_width: int = 1280
    sample_interval_ms: int = 500
    opaque_identity_max_collection_ms: int | None = None

    def __post_init__(self) -> None:
        if self.profile not in {
            "replay",
            "image_sequence",
            "pc_camera",
            "android_uvc",
            "android_ip_camera",
        }:
            raise ValueError(
                "scanner profile must be replay, image_sequence, pc_camera, android_uvc, "
                "or android_ip_camera"
            )
        for name in (
            "staging_root",
            "ready_root",
            "uvdoc_runtime_path",
            "uvdoc_checkpoint_path",
            "m1_model_dir",
            "m1_model_manifest",
        ):
            object.__setattr__(self, name, Path(getattr(self, name)).resolve())
        if self.replay_path is not None:
            object.__setattr__(self, "replay_path", Path(self.replay_path).resolve())
        object.__setattr__(self, "image_paths", tuple(Path(path).resolve() for path in self.image_paths))
        if self.profile == "replay" and self.replay_path is None:
            raise ValueError("replay scanner profile requires replay_path")
        if self.profile == "image_sequence" and not self.image_paths:
            raise ValueError("image_sequence scanner profile requires image_paths")
        if isinstance(self.camera_index, bool) or not isinstance(self.camera_index, int) or self.camera_index < 0:
            raise ValueError("camera_index must be a non-negative integer")
        if self.profile == "android_uvc" and (
            not isinstance(self.camera_selector, str) or not self.camera_selector.strip()
        ):
            raise ValueError("android_uvc scanner profile requires camera_selector")
        if self.profile == "android_ip_camera" and (
            not isinstance(self.camera_snapshot_url, str)
            or not self.camera_snapshot_url.strip()
        ):
            raise ValueError("android_ip_camera scanner profile requires camera_snapshot_url")
        for name in ("camera_snapshot_password_file", "camera_snapshot_tls_ca_file"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, Path(value).resolve())
        if self.camera_snapshot_username is not None and (
            not isinstance(self.camera_snapshot_username, str)
            or not self.camera_snapshot_username.strip()
        ):
            raise ValueError("camera_snapshot_username must be non-empty when configured")
        if (self.camera_snapshot_username is None) != (self.camera_snapshot_password_file is None):
            raise ValueError(
                "camera_snapshot_username and camera_snapshot_password_file must be configured together"
            )
        if not isinstance(self.camera_snapshot_allow_insecure_tls, bool):
            raise TypeError("camera_snapshot_allow_insecure_tls must be a boolean")
        if self.camera_snapshot_tls_ca_file is not None and self.camera_snapshot_allow_insecure_tls:
            raise ValueError("camera snapshot TLS CA and insecure TLS cannot both be configured")
        timeout = self.camera_snapshot_timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise ValueError("camera_snapshot_timeout_seconds must be in (0, 60]")
        for name, ceiling in (
            ("camera_snapshot_max_response_bytes", 128 * 1024 * 1024),
            ("camera_snapshot_min_width", 20_000),
            ("camera_snapshot_min_height", 20_000),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= ceiling:
                raise ValueError(f"{name} must be an integer in [1, {ceiling}]")
        if self.camera_selector is not None and (
            not isinstance(self.camera_selector, str) or not self.camera_selector.strip()
        ):
            raise ValueError("camera_selector must be a non-empty string when configured")
        if not isinstance(self.camera_backend, str) or self.camera_backend not in {
            "auto",
            "dshow",
            "msmf",
            "v4l2",
        }:
            raise ValueError("camera_backend must be auto, dshow, msmf, or v4l2")
        if self.camera_fallback_index is not None and (
            isinstance(self.camera_fallback_index, bool)
            or not isinstance(self.camera_fallback_index, int)
            or self.camera_fallback_index < 0
        ):
            raise ValueError("camera_fallback_index must be a non-negative integer when configured")
        if self.camera_fourcc is not None and (
            not isinstance(self.camera_fourcc, str)
            or len(self.camera_fourcc) != 4
            or not self.camera_fourcc.isascii()
        ):
            raise ValueError("camera_fourcc must contain exactly four ASCII characters")
        if self.camera_rotation not in {0, 90, 180, 270}:
            raise ValueError("camera_rotation must be 0, 90, 180, or 270")
        for name in (
            "camera_snapshot_landscape_rotation",
            "camera_snapshot_portrait_rotation",
        ):
            value = getattr(self, name)
            if value is not None and value not in {0, 90, 180, 270}:
                raise ValueError(f"{name} must be 0, 90, 180, or 270")
        if not isinstance(self.camera_mirror, bool):
            raise TypeError("camera_mirror must be a boolean")
        if self.camera_crop_normalized is not None:
            crop = self.camera_crop_normalized
            if len(crop) != 4 or any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                for value in crop
            ):
                raise TypeError("camera_crop_normalized must contain four numbers")
            left, top, right, bottom = (float(value) for value in crop)
            if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
                raise ValueError("camera_crop_normalized bounds are invalid")
        for name, value, ceiling in (
            ("camera_warmup_frames", self.camera_warmup_frames, 120),
            ("camera_reopen_attempts", self.camera_reopen_attempts, 10),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= ceiling:
                raise ValueError(f"{name} must be an integer in [0, {ceiling}]")
        if (
            isinstance(self.camera_reopen_initial_ms, bool)
            or not isinstance(self.camera_reopen_initial_ms, int)
            or not 1 <= self.camera_reopen_initial_ms <= 10_000
        ):
            raise ValueError("camera_reopen_initial_ms must be an integer in [1, 10000]")
        if not isinstance(self.operator_preview_enabled, bool):
            raise TypeError("operator_preview_enabled must be a boolean")
        if (
            isinstance(self.operator_preview_max_width, bool)
            or not isinstance(self.operator_preview_max_width, int)
            or not 320 <= self.operator_preview_max_width <= 7680
        ):
            raise ValueError("operator_preview_max_width must be an integer in [320, 7680]")
        for name in ("camera_width", "camera_height"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
                raise ValueError(f"{name} must be a positive integer when configured")
        if self.camera_fps is not None and (
            isinstance(self.camera_fps, bool)
            or not isinstance(self.camera_fps, (int, float))
            or self.camera_fps <= 0
        ):
            raise ValueError("camera_fps must be positive when configured")
        if (
            isinstance(self.sample_interval_ms, bool)
            or not isinstance(self.sample_interval_ms, int)
            or self.sample_interval_ms <= 0
        ):
            raise ValueError("sample_interval_ms must be a positive integer")
        if self.opaque_identity_max_collection_ms is not None:
            if (
                isinstance(self.opaque_identity_max_collection_ms, bool)
                or not isinstance(self.opaque_identity_max_collection_ms, int)
                or not 0 < self.opaque_identity_max_collection_ms <= 60_000
            ):
                raise ValueError(
                    "opaque_identity_max_collection_ms must be an integer in [1, 60000]"
                )
        if not isinstance(self.uvdoc_device, str) or self.uvdoc_device not in {"auto", "cpu", "cuda"}:
            raise ValueError("uvdoc_device must be auto, cpu, or cuda")


@dataclass(frozen=True, slots=True)
class StmSerialConfig:
    port: str
    baudrate: int = 9600
    read_timeout_ms: int = 20
    reconnect_initial_ms: int = 500
    reconnect_max_ms: int = 5000
    debounce_ms: int = 30
    cell_count: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.port, str) or not self.port.strip():
            raise ValueError("STM serial port must be a non-empty string")
        for name in ("baudrate", "read_timeout_ms", "reconnect_initial_ms", "reconnect_max_ms", "cell_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"STM serial {name} must be a positive integer")
        if isinstance(self.debounce_ms, bool) or not isinstance(self.debounce_ms, int) or self.debounce_ms < 0:
            raise ValueError("STM serial debounce_ms must be a non-negative integer")
        if self.reconnect_max_ms < self.reconnect_initial_ms:
            raise ValueError("STM serial reconnect_max_ms must be at least reconnect_initial_ms")


@dataclass(frozen=True, slots=True)
class LaptopAudioConfig:
    jsonl_trace: bool = True
    speak_catalog_titles: bool = True
    queue_capacity: int = 32
    powershell_executable: str = "powershell.exe"

    def __post_init__(self) -> None:
        if not isinstance(self.jsonl_trace, bool) or not isinstance(self.speak_catalog_titles, bool):
            raise TypeError("Laptop audio boolean fields must be booleans")
        if isinstance(self.queue_capacity, bool) or not isinstance(self.queue_capacity, int) or self.queue_capacity <= 0:
            raise ValueError("Laptop audio queue_capacity must be a positive integer")
        if not isinstance(self.powershell_executable, str) or not self.powershell_executable.strip():
            raise ValueError("Laptop audio powershell_executable must be a non-empty string")


@dataclass(frozen=True, slots=True)
class ReadingAudioConfig:
    enabled: bool = False
    backend: str = "sounddevice"
    max_resource_bytes: int = 4 * 1024 * 1024
    max_cache_bytes: int = 8 * 1024 * 1024
    max_cache_entries: int = 4
    download_chunk_bytes: int = 64 * 1024
    request_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("reading audio enabled must be a boolean")
        if self.backend != "sounddevice":
            raise ValueError("reading audio backend must be sounddevice")
        limits = {
            "max_resource_bytes": (self.max_resource_bytes, 4 * 1024 * 1024),
            "max_cache_bytes": (self.max_cache_bytes, 16 * 1024 * 1024),
            "max_cache_entries": (self.max_cache_entries, 8),
            "download_chunk_bytes": (self.download_chunk_bytes, 1024 * 1024),
        }
        for name, (value, ceiling) in limits.items():
            if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= ceiling:
                raise ValueError(f"reading audio {name} must be in [1, {ceiling}]")
        if self.max_cache_bytes < self.max_resource_bytes:
            raise ValueError("reading audio max_cache_bytes must be at least max_resource_bytes")
        timeout = self.request_timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 30:
            raise ValueError("reading audio request_timeout_seconds must be in (0, 30]")


@dataclass(frozen=True, slots=True)
class HoldRepeatConfig:
    initial_delay_ms: int = 650
    interval_ms: int = 180

    def __post_init__(self) -> None:
        if (
            isinstance(self.initial_delay_ms, bool)
            or not isinstance(self.initial_delay_ms, int)
            or not 300 <= self.initial_delay_ms <= 1500
        ):
            raise ValueError("hold repeat initial_delay_ms must be in [300, 1500]")
        if (
            isinstance(self.interval_ms, bool)
            or not isinstance(self.interval_ms, int)
            or not 100 <= self.interval_ms <= 1000
        ):
            raise ValueError("hold repeat interval_ms must be in [100, 1000]")


@dataclass(frozen=True, slots=True)
class DeviceAppConfig:
    config_path: Path
    connectivity: DeviceConnectivityConfig
    delivery: DeviceDeliveryConfig
    scanner: ScannerHostConfig
    viewport_size: int = 40
    poll_interval_ms: int = 50
    controls_mode: str = "console"
    feedback_mode: str = "jsonl"
    stm_serial: StmSerialConfig | None = None
    laptop_audio: LaptopAudioConfig = LaptopAudioConfig()
    reading_audio: ReadingAudioConfig = ReadingAudioConfig()
    hold_repeat: HoldRepeatConfig = HoldRepeatConfig()

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_path", Path(self.config_path).resolve())
        if isinstance(self.viewport_size, bool) or not isinstance(self.viewport_size, int) or self.viewport_size <= 0:
            raise ValueError("viewport_size must be a positive integer")
        if (
            isinstance(self.poll_interval_ms, bool)
            or not isinstance(self.poll_interval_ms, int)
            or self.poll_interval_ms <= 0
        ):
            raise ValueError("poll_interval_ms must be a positive integer")
        if self.controls_mode not in {"console", "stm_serial"}:
            raise ValueError("local controls mode must be console or stm_serial")
        if self.feedback_mode not in {"jsonl", "windows_audio"}:
            raise ValueError("local feedback mode must be jsonl or windows_audio")
        if self.feedback_mode == "windows_audio" and self.reading_audio.enabled:
            raise ValueError(
                "windows_audio (legacy SAPI) cannot be combined with Piper transport playback"
            )
        if self.controls_mode == "stm_serial":
            if self.stm_serial is None:
                raise ValueError("stm_serial controls require local_io.stm_serial")
            if self.viewport_size != self.stm_serial.cell_count:
                raise ValueError("viewport_size must equal STM serial cell_count")
        if self.scanner.ready_root != self.delivery.artifact_root:
            raise ValueError("scanner ready_root must equal delivery artifact_root")
        if self.scanner.staging_root == self.scanner.ready_root:
            raise ValueError("scanner staging_root and ready_root must be different")
        if not _same_filesystem(self.scanner.staging_root, self.scanner.ready_root):
            raise ValueError("scanner staging_root and ready_root must use the same filesystem")

    @classmethod
    def from_toml(cls, path: str | Path) -> "DeviceAppConfig":
        config_path = Path(path).resolve()
        try:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"cannot read Device app config: {config_path}") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("Device app config schema_version must be 1")
        allowed = {
            "schema_version",
            "connectivity_config",
            "viewport_size",
            "poll_interval_ms",
            "delivery",
            "scanner",
            "local_io",
        }
        _reject_unknown(payload, allowed, "Device app")
        root = config_path.parent
        connectivity_value = _required_text(payload, "connectivity_config")
        connectivity = DeviceConnectivityConfig.from_toml(_resolve(root, connectivity_value))
        delivery_payload = _required_table(payload, "delivery")
        _reject_unknown(
            delivery_payload,
            {
                "outbox_db_path",
                "artifact_root",
                "upload_timeout_seconds",
                "retry_initial_seconds",
                "retry_max_seconds",
                "response_limit_bytes",
                "file_chunk_bytes",
            },
            "delivery",
        )
        delivery = DeviceDeliveryConfig(
            outbox_db_path=_resolve(root, _required_text(delivery_payload, "outbox_db_path")),
            artifact_root=_resolve(root, _required_text(delivery_payload, "artifact_root")),
            **{
                key: value
                for key, value in delivery_payload.items()
                if key not in {"outbox_db_path", "artifact_root"}
            },
        )
        scanner_payload = _required_table(payload, "scanner")
        _reject_unknown(
            scanner_payload,
            {
                "profile",
                "staging_root",
                "ready_root",
                "uvdoc_runtime_path",
                "uvdoc_checkpoint_path",
                "uvdoc_device",
                "m1_model_dir",
                "m1_model_manifest",
                "replay_path",
                "image_paths",
                "camera_index",
                "camera_width",
                "camera_height",
                "camera_fps",
                "camera_selector",
                "camera_backend",
                "camera_fallback_index",
                "camera_fourcc",
                "camera_rotation",
                "camera_mirror",
                "camera_crop_normalized",
                "camera_warmup_frames",
                "camera_reopen_attempts",
                "camera_reopen_initial_ms",
                "camera_snapshot_url",
                "camera_snapshot_username",
                "camera_snapshot_password_file",
                "camera_snapshot_tls_ca_file",
                "camera_snapshot_allow_insecure_tls",
                "camera_snapshot_timeout_seconds",
                "camera_snapshot_max_response_bytes",
                "camera_snapshot_min_width",
                "camera_snapshot_min_height",
                "camera_snapshot_landscape_rotation",
                "camera_snapshot_portrait_rotation",
                "operator_preview_enabled",
                "operator_preview_max_width",
                "sample_interval_ms",
                "opaque_identity_max_collection_ms",
            },
            "scanner",
        )
        image_values = scanner_payload.get("image_paths", [])
        if not isinstance(image_values, list) or any(not isinstance(item, str) for item in image_values):
            raise ValueError("scanner image_paths must be a string array")
        replay_value = scanner_payload.get("replay_path")
        if replay_value is not None and not isinstance(replay_value, str):
            raise ValueError("scanner replay_path must be a string")
        scanner = ScannerHostConfig(
            profile=_required_text(scanner_payload, "profile"),
            staging_root=_resolve(root, _required_text(scanner_payload, "staging_root")),
            ready_root=_resolve(root, _required_text(scanner_payload, "ready_root")),
            uvdoc_runtime_path=_resolve(root, _required_text(scanner_payload, "uvdoc_runtime_path")),
            uvdoc_checkpoint_path=_resolve(root, _required_text(scanner_payload, "uvdoc_checkpoint_path")),
            uvdoc_device=str(scanner_payload.get("uvdoc_device", "auto")),
            m1_model_dir=_resolve(root, _required_text(scanner_payload, "m1_model_dir")),
            m1_model_manifest=_resolve(root, _required_text(scanner_payload, "m1_model_manifest")),
            replay_path=_resolve(root, replay_value) if replay_value is not None else None,
            image_paths=tuple(_resolve(root, item) for item in image_values),
            camera_index=scanner_payload.get("camera_index", 0),
            camera_width=scanner_payload.get("camera_width"),
            camera_height=scanner_payload.get("camera_height"),
            camera_fps=scanner_payload.get("camera_fps"),
            camera_selector=scanner_payload.get("camera_selector"),
            camera_backend=scanner_payload.get("camera_backend", "auto"),
            camera_fallback_index=scanner_payload.get("camera_fallback_index"),
            camera_fourcc=scanner_payload.get("camera_fourcc"),
            camera_rotation=scanner_payload.get("camera_rotation", 0),
            camera_snapshot_landscape_rotation=scanner_payload.get(
                "camera_snapshot_landscape_rotation"
            ),
            camera_snapshot_portrait_rotation=scanner_payload.get(
                "camera_snapshot_portrait_rotation"
            ),
            camera_mirror=scanner_payload.get("camera_mirror", False),
            camera_crop_normalized=(
                tuple(scanner_payload["camera_crop_normalized"])
                if "camera_crop_normalized" in scanner_payload
                else None
            ),
            camera_warmup_frames=scanner_payload.get("camera_warmup_frames", 3),
            camera_reopen_attempts=scanner_payload.get("camera_reopen_attempts", 1),
            camera_reopen_initial_ms=scanner_payload.get("camera_reopen_initial_ms", 250),
            camera_snapshot_url=scanner_payload.get("camera_snapshot_url"),
            camera_snapshot_username=scanner_payload.get("camera_snapshot_username"),
            camera_snapshot_password_file=(
                _resolve(root, scanner_payload["camera_snapshot_password_file"])
                if "camera_snapshot_password_file" in scanner_payload
                else None
            ),
            camera_snapshot_tls_ca_file=(
                _resolve(root, scanner_payload["camera_snapshot_tls_ca_file"])
                if "camera_snapshot_tls_ca_file" in scanner_payload
                else None
            ),
            camera_snapshot_allow_insecure_tls=scanner_payload.get(
                "camera_snapshot_allow_insecure_tls", False
            ),
            camera_snapshot_timeout_seconds=scanner_payload.get(
                "camera_snapshot_timeout_seconds", 8.0
            ),
            camera_snapshot_max_response_bytes=scanner_payload.get(
                "camera_snapshot_max_response_bytes", 32 * 1024 * 1024
            ),
            camera_snapshot_min_width=scanner_payload.get("camera_snapshot_min_width", 1920),
            camera_snapshot_min_height=scanner_payload.get("camera_snapshot_min_height", 1080),
            operator_preview_enabled=scanner_payload.get("operator_preview_enabled", False),
            operator_preview_max_width=scanner_payload.get("operator_preview_max_width", 1280),
            sample_interval_ms=scanner_payload.get("sample_interval_ms", 500),
            opaque_identity_max_collection_ms=scanner_payload.get(
                "opaque_identity_max_collection_ms"
            ),
        )
        local_io = payload.get("local_io", {})
        if not isinstance(local_io, dict):
            raise ValueError("local_io must be a table")
        _reject_unknown(
            local_io,
            {"controls", "feedback", "stm_serial", "windows_audio", "reading_audio", "hold_repeat"},
            "local_io",
        )
        controls_mode = local_io.get("controls", "console")
        feedback_mode = local_io.get("feedback", "jsonl")
        if not isinstance(controls_mode, str) or not isinstance(feedback_mode, str):
            raise ValueError("local_io controls and feedback must be strings")
        stm_payload = local_io.get("stm_serial")
        stm_serial = None
        if stm_payload is not None:
            if not isinstance(stm_payload, dict):
                raise ValueError("local_io.stm_serial must be a table")
            _reject_unknown(
                stm_payload,
                {
                    "port",
                    "baudrate",
                    "read_timeout_ms",
                    "reconnect_initial_ms",
                    "reconnect_max_ms",
                    "debounce_ms",
                    "cell_count",
                },
                "local_io.stm_serial",
            )
            stm_serial = StmSerialConfig(
                port=_required_text(stm_payload, "port"),
                **{key: value for key, value in stm_payload.items() if key != "port"},
            )
        audio_payload = local_io.get("windows_audio", {})
        if not isinstance(audio_payload, dict):
            raise ValueError("local_io.windows_audio must be a table")
        _reject_unknown(
            audio_payload,
            {"jsonl_trace", "speak_catalog_titles", "queue_capacity", "powershell_executable"},
            "local_io.windows_audio",
        )
        reading_audio_payload = local_io.get("reading_audio", {})
        if not isinstance(reading_audio_payload, dict):
            raise ValueError("local_io.reading_audio must be a table")
        _reject_unknown(
            reading_audio_payload,
            {
                "enabled",
                "backend",
                "max_resource_bytes",
                "max_cache_bytes",
                "max_cache_entries",
                "download_chunk_bytes",
                "request_timeout_seconds",
            },
            "local_io.reading_audio",
        )
        hold_repeat_payload = local_io.get("hold_repeat", {})
        if not isinstance(hold_repeat_payload, dict):
            raise ValueError("local_io.hold_repeat must be a table")
        _reject_unknown(
            hold_repeat_payload,
            {"initial_delay_ms", "interval_ms"},
            "local_io.hold_repeat",
        )
        return cls(
            config_path=config_path,
            connectivity=connectivity,
            delivery=delivery,
            scanner=scanner,
            viewport_size=payload.get("viewport_size", 40),
            poll_interval_ms=payload.get("poll_interval_ms", 50),
            controls_mode=controls_mode,
            feedback_mode=feedback_mode,
            stm_serial=stm_serial,
            laptop_audio=LaptopAudioConfig(**audio_payload),
            reading_audio=ReadingAudioConfig(**reading_audio_payload),
            hold_repeat=HoldRepeatConfig(**hold_repeat_payload),
        )


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def _required_text(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _required_table(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a table")
    return value


def _reject_unknown(payload: dict[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unknown {name} config fields: {sorted(unknown)}")


def _same_filesystem(left: Path, right: Path) -> bool:
    if os.name == "nt":
        return left.drive.casefold() == right.drive.casefold()
    left_probe = next((path for path in (left, *left.parents) if path.exists()), None)
    right_probe = next((path for path in (right, *right.parents) if path.exists()), None)
    return bool(left_probe and right_probe and left_probe.stat().st_dev == right_probe.stat().st_dev)
