from __future__ import annotations

import numpy as np
import pytest

from book_scanner.correct.unwarper import UnwarpFailureReason
from book_scanner.correct.uvdoc_adapter import UVDocAdapter, UVDocConfig


def test_uvdoc_adapter_maps_missing_model_to_reason(tmp_path):
    adapter = UVDocAdapter(UVDocConfig(tmp_path / "missing", tmp_path / "missing.pkl", device="cpu"))
    result = adapter.unwarp(np.zeros((20, 30, 3), dtype=np.uint8))
    assert not result.success
    assert result.reason is UnwarpFailureReason.MODEL_NOT_FOUND


def test_uvdoc_adapter_rejects_invalid_input_before_model_load(tmp_path):
    adapter = UVDocAdapter(UVDocConfig(tmp_path, tmp_path / "weight.pkl"))
    result = adapter.unwarp(np.zeros((20, 30), dtype=np.uint8))
    assert not result.success
    assert result.reason is UnwarpFailureReason.INVALID_INPUT
    assert adapter.load_count == 0


def _configured_adapter(tmp_path, monkeypatch, model_class):
    torch = pytest.importorskip("torch")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "model.py").write_text("# replaced by test loader\n", encoding="utf-8")
    checkpoint = tmp_path / "weight.pkl"
    torch.save({"model_state": {}}, checkpoint)
    adapter = UVDocAdapter(UVDocConfig(runtime, checkpoint, device="cpu", model_input_size=(32, 32)))
    monkeypatch.setattr(adapter, "_load_external_model_class", lambda: model_class)
    return adapter


def test_uvdoc_adapter_loads_once_and_returns_valid_output(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    class FakeModel(torch.nn.Module):
        def __init__(self, **_kwargs):
            super().__init__()

        def forward(self, tensor):
            batch = tensor.shape[0]
            ys = torch.linspace(-1, 1, 45, device=tensor.device)
            xs = torch.linspace(-1, 1, 31, device=tensor.device)
            grid_y, grid_x = torch.meshgrid(ys, xs, indexing="ij")
            grid = torch.stack((grid_x, grid_y)).unsqueeze(0).repeat(batch, 1, 1, 1)
            return grid, torch.zeros((batch, 3, 45, 31), device=tensor.device)

    adapter = _configured_adapter(tmp_path, monkeypatch, FakeModel)
    image = np.random.default_rng(7).integers(0, 256, (40, 30, 3), dtype=np.uint8)

    first = adapter.unwarp(image)
    second = adapter.unwarp(image)

    assert first.success and second.success
    assert first.image is not None and first.image.shape == image.shape
    assert first.device == "cpu"
    assert adapter.load_count == 1
    assert first.diagnostics["grid_shape"] == [1, 2, 45, 31]
    assert first.diagnostics["sampling_mode"] == "bilinear"


def test_uvdoc_adapter_reuses_model_across_sampling_modes(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")

    class FakeModel(torch.nn.Module):
        def __init__(self, **_kwargs):
            super().__init__()

        def forward(self, tensor):
            ys = torch.linspace(-1, 1, 45, device=tensor.device)
            xs = torch.linspace(-1, 1, 31, device=tensor.device)
            grid_y, grid_x = torch.meshgrid(ys, xs, indexing="ij")
            grid = torch.stack((grid_x, grid_y)).unsqueeze(0)
            return grid, torch.zeros((1, 3, 45, 31), device=tensor.device)

    adapter = _configured_adapter(tmp_path, monkeypatch, FakeModel)
    image = np.random.default_rng(13).integers(0, 256, (40, 30, 3), dtype=np.uint8)
    bilinear = adapter.unwarp_with_mode(image, "bilinear")
    bicubic = adapter.unwarp_with_mode(image, "bicubic")

    assert bilinear.success and bicubic.success
    assert bicubic.diagnostics["sampling_mode"] == "bicubic"
    assert adapter.load_count == 1


def test_uvdoc_adapter_rejects_sampling_mode_before_load(tmp_path):
    adapter = UVDocAdapter(UVDocConfig(tmp_path / "missing", tmp_path / "missing.pkl", device="cpu"))
    result = adapter.unwarp_with_mode(np.zeros((20, 30, 3), dtype=np.uint8), "nearest")
    assert not result.success
    assert result.reason is UnwarpFailureReason.INVALID_INPUT
    assert adapter.load_count == 0


def test_uvdoc_adapter_maps_inference_exception_to_reason(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")

    class FailingModel(torch.nn.Module):
        def __init__(self, **_kwargs):
            super().__init__()

        def forward(self, _tensor):
            raise RuntimeError("synthetic inference failure")

    adapter = _configured_adapter(tmp_path, monkeypatch, FailingModel)
    result = adapter.unwarp(np.zeros((40, 30, 3), dtype=np.uint8))
    assert not result.success
    assert result.reason is UnwarpFailureReason.INFERENCE_FAILED


def test_uvdoc_adapter_rejects_invalid_sampling_grid(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")

    class InvalidGridModel(torch.nn.Module):
        def __init__(self, **_kwargs):
            super().__init__()

        def forward(self, tensor):
            grid = torch.full((tensor.shape[0], 2, 45, 31), float("nan"), device=tensor.device)
            return grid, torch.zeros((tensor.shape[0], 3, 45, 31), device=tensor.device)

    adapter = _configured_adapter(tmp_path, monkeypatch, InvalidGridModel)
    result = adapter.unwarp(np.zeros((40, 30, 3), dtype=np.uint8))
    assert not result.success
    assert result.reason is UnwarpFailureReason.INVALID_OUTPUT
