"""Android UVC camera discovery and guarded OpenCV capture composition."""

from __future__ import annotations

import json
import platform
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .protocols import Clock, FrameSample
from .sources import (
    CameraUnavailableError,
    CaptureFactory,
    OpenCVCameraSource,
)


class CameraDiscoveryError(RuntimeError):
    """The host could not establish one unambiguous camera device."""


@dataclass(frozen=True, slots=True)
class CameraDevice:
    stable_id: str
    name: str
    backend: str
    path: str | None = None
    index: int | None = None

    def matches(self, selector: str) -> bool:
        wanted = selector.strip().casefold()
        return any(
            wanted == value.strip().casefold()
            for value in (self.stable_id, self.name, self.path or "")
            if value.strip()
        )

    def as_report(self) -> dict[str, Any]:
        return {
            "stable_id": self.stable_id,
            "name": self.name,
            "backend": self.backend,
            "path": self.path,
            "index": self.index,
        }


@dataclass(frozen=True, slots=True)
class SelectedCamera:
    device: CameraDevice
    open_target: int | str
    selection_method: str


CameraDeviceProvider = Callable[[str], Sequence[CameraDevice]]


def default_camera_backend(system: str | None = None) -> str:
    host = (system or platform.system()).casefold()
    if host == "windows":
        return "dshow"
    if host == "linux":
        return "v4l2"
    raise CameraDiscoveryError(f"Android UVC camera host is unsupported on {system or platform.system()}")


def camera_backend_api(backend: str) -> int:
    mapping = {
        "dshow": cv2.CAP_DSHOW,
        "msmf": cv2.CAP_MSMF,
        "v4l2": cv2.CAP_V4L2,
    }
    try:
        return mapping[backend.casefold()]
    except KeyError as exc:
        raise CameraDiscoveryError(f"unsupported camera backend: {backend}") from exc


def enumerate_camera_devices(
    backend: str = "auto",
    *,
    system: str | None = None,
) -> tuple[CameraDevice, ...]:
    host = system or platform.system()
    effective_backend = default_camera_backend(host) if backend == "auto" else backend.casefold()
    if host.casefold() == "windows":
        if effective_backend not in {"dshow", "msmf"}:
            raise CameraDiscoveryError("Windows Android UVC host requires dshow or msmf")
        return _enumerate_windows_devices(effective_backend)
    if host.casefold() == "linux":
        if effective_backend != "v4l2":
            raise CameraDiscoveryError("Linux Android UVC host requires v4l2")
        return _enumerate_linux_devices()
    raise CameraDiscoveryError(f"Android UVC camera host is unsupported on {host}")


def resolve_camera_device(
    devices: Sequence[CameraDevice],
    selector: str,
    *,
    fallback_index: int | None = None,
) -> SelectedCamera:
    matches = [device for device in devices if device.matches(selector)]
    if not matches:
        raise CameraDiscoveryError(f"camera selector did not match any device: {selector}")
    if len(matches) != 1:
        raise CameraDiscoveryError(f"camera selector matched multiple devices: {selector}")
    device = matches[0]
    if device.path:
        return SelectedCamera(device, device.path, "persistent_path")
    if device.index is not None:
        return SelectedCamera(device, device.index, "enumerated_index")
    if fallback_index is None:
        raise CameraDiscoveryError(
            "selected Windows camera has no capture index; configure camera_fallback_index"
        )
    return SelectedCamera(device, fallback_index, "selector_guarded_index")


class AndroidUvcCameraSource:
    """Resolve an Android UVC device before exposing frames to the Scanner."""

    def __init__(
        self,
        selector: str,
        *,
        backend: str = "auto",
        fallback_index: int | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: float | None = None,
        fourcc: str | None = None,
        rotation: int = 0,
        mirror: bool = False,
        warmup_frames: int = 3,
        reopen_attempts: int = 1,
        reopen_initial_ms: int = 250,
        drain_grabs: int = 2,
        clock: Clock | None = None,
        device_provider: CameraDeviceProvider = enumerate_camera_devices,
        capture_factory: CaptureFactory = cv2.VideoCapture,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError("Android UVC camera selector must be a non-empty string")
        self.selector = selector.strip()
        self.backend = default_camera_backend() if backend == "auto" else backend.casefold()
        camera_backend_api(self.backend)
        self.fallback_index = fallback_index
        self.width = width
        self.height = height
        self.fps = fps
        self.fourcc = fourcc
        self.rotation = rotation
        self.mirror = mirror
        self.warmup_frames = warmup_frames
        self.reopen_attempts = reopen_attempts
        self.reopen_initial_ms = reopen_initial_ms
        self.drain_grabs = drain_grabs
        self.clock = clock
        self.device_provider = device_provider
        self.capture_factory = capture_factory
        self.sleep = sleep
        self._selected: SelectedCamera | None = None
        self._source: OpenCVCameraSource | None = None

    @property
    def exhausted(self) -> bool:
        return False

    @property
    def selected_camera(self) -> SelectedCamera | None:
        return self._selected

    @property
    def effective_mode(self) -> dict[str, float | str] | None:
        return None if self._source is None else self._source.effective_mode

    def start(self) -> None:
        if self._source is not None:
            raise RuntimeError("Android UVC camera source is already started")
        try:
            selected = resolve_camera_device(
                self.device_provider(self.backend),
                self.selector,
                fallback_index=self.fallback_index,
            )
        except CameraDiscoveryError as exc:
            raise CameraUnavailableError(str(exc)) from exc
        kwargs: dict[str, Any] = {}
        if self.sleep is not None:
            kwargs["sleep"] = self.sleep
        source = OpenCVCameraSource(
            selected.open_target,
            clock=self.clock,
            drain_grabs=self.drain_grabs,
            width=self.width,
            height=self.height,
            fps=self.fps,
            backend_api=camera_backend_api(self.backend),
            fourcc=self.fourcc,
            rotation=self.rotation,
            mirror=self.mirror,
            warmup_frames=self.warmup_frames,
            reopen_attempts=self.reopen_attempts,
            reopen_initial_ms=self.reopen_initial_ms,
            capture_factory=self.capture_factory,
            frame_prefix="android-uvc",
            **kwargs,
        )
        try:
            source.start()
        except Exception:
            source.stop()
            raise
        self._selected = selected
        self._source = source

    def read(self) -> FrameSample[np.ndarray] | None:
        if self._source is None:
            return None
        return self._source.read()

    def stop(self) -> None:
        source, self._source = self._source, None
        if source is not None:
            source.stop()


def _enumerate_windows_devices(backend: str) -> tuple[CameraDevice, ...]:
    command = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
        "$items=@(Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.PNPClass -eq 'Camera' -or $_.PNPClass -eq 'Image' } | "
        "Select-Object Name,PNPDeviceID);"
        "$items | ConvertTo-Json -Compress"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            creationflags=flags,
        )
        payload = json.loads(result.stdout or "[]")
    except (OSError, subprocess.SubprocessError, UnicodeError, json.JSONDecodeError) as exc:
        raise CameraDiscoveryError("could not enumerate Windows camera devices") from exc
    rows = payload if isinstance(payload, list) else [payload]
    devices = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("Name")
        stable_id = row.get("PNPDeviceID")
        if isinstance(name, str) and name.strip() and isinstance(stable_id, str) and stable_id.strip():
            devices.append(CameraDevice(stable_id.strip(), name.strip(), backend))
    return tuple(sorted(devices, key=lambda device: (device.name.casefold(), device.stable_id.casefold())))


def _enumerate_linux_devices(
    *,
    dev_root: Path = Path("/dev"),
    sys_video_root: Path = Path("/sys/class/video4linux"),
) -> tuple[CameraDevice, ...]:
    by_id = dev_root / "v4l/by-id"
    resolved: set[Path] = set()
    devices: list[CameraDevice] = []
    if by_id.is_dir():
        for link in sorted(by_id.iterdir()):
            try:
                target = link.resolve(strict=True)
            except OSError:
                continue
            if not target.name.startswith("video"):
                continue
            resolved.add(target)
            devices.append(
                CameraDevice(
                    stable_id=str(link),
                    name=_linux_camera_name(target, sys_video_root),
                    backend="v4l2",
                    path=str(link),
                )
            )
    for path in sorted(dev_root.glob("video*")):
        try:
            target = path.resolve(strict=True)
        except OSError:
            continue
        if target in resolved:
            continue
        devices.append(
            CameraDevice(
                stable_id=str(path),
                name=_linux_camera_name(target, sys_video_root),
                backend="v4l2",
                path=str(path),
            )
        )
    return tuple(devices)


def _linux_camera_name(path: Path, sys_video_root: Path) -> str:
    name_file = sys_video_root / path.name / "name"
    try:
        value = name_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        value = ""
    return value or path.name
