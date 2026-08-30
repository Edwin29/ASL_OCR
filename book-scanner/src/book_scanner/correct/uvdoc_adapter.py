"""Small, failure-aware adapter around an external UVDoc checkout."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from book_scanner.correct.unwarper import UnwarpFailureReason, UnwarpResult


@dataclass(frozen=True)
class UVDocConfig:
    runtime_path: Path
    checkpoint_path: Path
    device: str = "auto"
    model_input_size: tuple[int, int] = (488, 712)  # width, height from official utils.py
    sampling_mode: str = "bilinear"


class UVDocAdapter:
    name = "uvdoc"

    def __init__(self, config: UVDocConfig):
        self.config = config
        self._model = None
        self._torch = None
        self._device = "unresolved"
        self._load_count = 0
        self._load_ms = 0.0

    @property
    def load_count(self) -> int:
        return self._load_count

    def _resolve_device(self, torch) -> str:
        requested = self.config.device.lower()
        if requested == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if requested == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        if requested not in {"cpu", "cuda"}:
            raise ValueError(f"unsupported UVDoc device: {self.config.device}")
        return requested

    def _load_external_model_class(self):
        model_path = Path(self.config.runtime_path) / "model.py"
        if not model_path.is_file():
            raise FileNotFoundError(f"UVDoc model.py not found: {model_path}")
        module_name = f"_book_scanner_uvdoc_{hashlib.sha256(str(model_path).encode()).hexdigest()[:12]}"
        spec = importlib.util.spec_from_file_location(module_name, model_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not import UVDoc model module: {model_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.UVDocnet

    def _ensure_loaded(self) -> tuple[bool, UnwarpFailureReason | None, str | None]:
        if self._model is not None:
            return True, None, None
        runtime_path, checkpoint_path = Path(self.config.runtime_path), Path(self.config.checkpoint_path)
        if not runtime_path.is_dir() or not checkpoint_path.is_file():
            return False, UnwarpFailureReason.MODEL_NOT_FOUND, (
                f"UVDoc runtime/checkpoint missing: runtime={runtime_path}, checkpoint={checkpoint_path}"
            )
        started = time.perf_counter()
        try:
            import torch

            device = self._resolve_device(torch)
            model_class = self._load_external_model_class()
            model = model_class(num_filter=32, kernel_size=5)
            load_kwargs = {"map_location": torch.device(device)}
            if "weights_only" in inspect.signature(torch.load).parameters:
                load_kwargs["weights_only"] = True
            checkpoint = torch.load(checkpoint_path, **load_kwargs)
            state_dict = checkpoint.get("model_state") if isinstance(checkpoint, dict) else None
            if state_dict is None:
                raise ValueError("UVDoc checkpoint has no 'model_state'")
            model.load_state_dict(state_dict)
            model.to(device)
            model.eval()
            self._torch, self._model, self._device = torch, model, device
            self._load_count += 1
            self._load_ms = (time.perf_counter() - started) * 1000.0
            return True, None, None
        except Exception as exc:
            return False, UnwarpFailureReason.MODEL_LOAD_FAILED, f"{type(exc).__name__}: {exc}"

    def unwarp(self, image: np.ndarray) -> UnwarpResult:
        return self.unwarp_with_mode(image, self.config.sampling_mode)

    def unwarp_with_mode(self, image: np.ndarray, sampling_mode: str) -> UnwarpResult:
        if (
            not isinstance(image, np.ndarray)
            or image.ndim != 3
            or image.shape[2] != 3
            or image.size == 0
            or image.dtype != np.uint8
        ):
            size = (image.shape[1], image.shape[0]) if isinstance(image, np.ndarray) and image.ndim >= 2 else (0, 0)
            return UnwarpResult(
                False, None, self.name, self._device, 0.0, size, None,
                UnwarpFailureReason.INVALID_INPUT, {"message": "UVDoc input must be a non-empty HxWx3 uint8 BGR image"},
            )

        sampling_mode = str(sampling_mode).lower()
        if sampling_mode not in {"bilinear", "bicubic"}:
            return UnwarpResult(
                False, None, self.name, self._device, 0.0, (int(image.shape[1]), int(image.shape[0])), None,
                UnwarpFailureReason.INVALID_INPUT,
                {"message": f"unsupported UVDoc sampling mode: {sampling_mode}", "sampling_mode": sampling_mode},
            )

        input_size = (int(image.shape[1]), int(image.shape[0]))
        loaded, reason, message = self._ensure_loaded()
        if not loaded:
            return UnwarpResult(
                False, None, self.name, self._device, 0.0, input_size, None, reason,
                {"message": message or "model load failed", "load_count": self._load_count},
            )

        started = time.perf_counter()
        try:
            torch = self._torch
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            resized = cv2.resize(rgb, self.config.model_input_size, interpolation=cv2.INTER_AREA)
            tensor = torch.from_numpy(resized.transpose(2, 0, 1)).unsqueeze(0).to(self._device)
            source = torch.from_numpy(rgb.transpose(2, 0, 1)).unsqueeze(0).to(self._device)
            with torch.inference_mode():
                point_positions, _ = self._model(tensor)
                if (
                    not torch.is_tensor(point_positions)
                    or point_positions.ndim != 4
                    or point_positions.shape[0] != 1
                    or point_positions.shape[1] != 2
                    or not bool(torch.isfinite(point_positions).all())
                ):
                    elapsed = (time.perf_counter() - started) * 1000.0
                    shape = list(point_positions.shape) if torch.is_tensor(point_positions) else None
                    return UnwarpResult(
                        False, None, self.name, self._device, elapsed, input_size, None,
                        UnwarpFailureReason.INVALID_OUTPUT,
                        {"message": f"invalid UVDoc sampling grid shape/value: {shape}", "load_count": self._load_count},
                    )
                grid = torch.nn.functional.interpolate(
                    point_positions,
                    size=(input_size[1], input_size[0]),
                    mode="bilinear",
                    align_corners=True,
                )
                output = torch.nn.functional.grid_sample(
                    source,
                    grid.transpose(1, 2).transpose(2, 3),
                    mode=sampling_mode,
                    align_corners=True,
                )
            if output.shape != source.shape or not bool(torch.isfinite(output).all()):
                elapsed = (time.perf_counter() - started) * 1000.0
                return UnwarpResult(
                    False, None, self.name, self._device, elapsed, input_size, None,
                    UnwarpFailureReason.INVALID_OUTPUT,
                    {"message": f"invalid UVDoc sampled output shape/value: {list(output.shape)}", "load_count": self._load_count},
                )
            rgb_output = np.clip(
                output[0].detach().cpu().numpy().transpose(1, 2, 0) * 255.0, 0, 255
            ).astype(np.uint8)
            bgr_output = cv2.cvtColor(rgb_output, cv2.COLOR_RGB2BGR)
            elapsed = (time.perf_counter() - started) * 1000.0
            if bgr_output.shape != image.shape or bgr_output.dtype != np.uint8:
                return UnwarpResult(
                    False, None, self.name, self._device, elapsed, input_size, None,
                    UnwarpFailureReason.INVALID_OUTPUT,
                    {"message": f"unexpected UVDoc output shape {bgr_output.shape}", "load_count": self._load_count},
                )
            return UnwarpResult(
                True,
                bgr_output,
                self.name,
                self._device,
                elapsed,
                input_size,
                (bgr_output.shape[1], bgr_output.shape[0]),
                None,
                {
                    "load_count": self._load_count,
                    "load_ms": self._load_ms,
                    "model_input_size": list(self.config.model_input_size),
                    "grid_shape": list(point_positions.shape),
                    "sampling_mode": sampling_mode,
                },
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            return UnwarpResult(
                False, None, self.name, self._device, elapsed, input_size, None,
                UnwarpFailureReason.INFERENCE_FAILED,
                {"message": f"{type(exc).__name__}: {exc}", "load_count": self._load_count},
            )
