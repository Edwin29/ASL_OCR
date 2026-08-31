"""Train and export the V3-A.2 tiny digit classifier.

PyTorch and ONNX are offline training dependencies only.  The exported runtime
asset is consumed through cv2.dnn and the scanner package never imports either
training dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn


class TinyDigitNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 12, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(12, 24, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(24, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Linear(32 * 6 * 4, 10)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.classifier(torch.flatten(self.features(image), 1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--output-model", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--onnx-deps-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--epochs", type=int, default=18)
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()
    if args.epochs <= 0 or args.batch_size <= 0:
        parser.error("epochs and batch size must be positive")
    if not args.dataset.is_file() or not args.dataset_manifest.is_file():
        parser.error("dataset and dataset manifest must exist")
    if not args.onnx_deps_dir.is_dir():
        parser.error("isolated ONNX training dependency directory does not exist")

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    torch.use_deterministic_algorithms(True)
    payload = np.load(args.dataset)
    train_x = torch.from_numpy(payload["train_x"])
    train_y = torch.from_numpy(payload["train_y"])
    validation_x = torch.from_numpy(payload["validation_x"])
    validation_y = torch.from_numpy(payload["validation_y"])

    model = TinyDigitNet()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003, weight_decay=1e-5)
    criterion = nn.CrossEntropyLoss()
    history: list[dict[str, float | int]] = []
    best_accuracy = -1.0
    best_state: dict[str, torch.Tensor] | None = None
    started = time.perf_counter()
    for epoch in range(args.epochs):
        generator = torch.Generator().manual_seed(args.seed + epoch)
        order = torch.randperm(train_y.numel(), generator=generator)
        model.train()
        total_loss = 0.0
        total_correct = 0
        for offset in range(0, order.numel(), args.batch_size):
            indices = order[offset : offset + args.batch_size]
            logits = model(train_x[indices])
            loss = criterion(logits, train_y[indices])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * indices.numel()
            total_correct += int((logits.argmax(1) == train_y[indices]).sum())
        model.eval()
        with torch.no_grad():
            validation_logits = model(validation_x)
            validation_accuracy = float(
                (validation_logits.argmax(1) == validation_y).float().mean()
            )
        history.append(
            {
                "epoch": epoch + 1,
                "train_loss": total_loss / train_y.numel(),
                "train_accuracy": total_correct / train_y.numel(),
                "validation_accuracy": validation_accuracy,
            }
        )
        if validation_accuracy > best_accuracy:
            best_accuracy = validation_accuracy
            best_state = {name: value.detach().clone() for name, value in model.state_dict().items()}
    assert best_state is not None
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        final_logits = model(validation_x)
    temperature = _calibrate_temperature(final_logits.numpy(), validation_y.numpy())

    # Import the isolated export-only package after NumPy/Torch have already
    # resolved their production environment versions.  This prevents the target
    # directory's transitive NumPy wheel from replacing the active runtime.
    sys.path.append(str(args.onnx_deps_dir.resolve()))
    import onnx  # noqa: PLC0415

    args.output_model.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros((1, 1, 48, 32), dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy,
        str(args.output_model),
        input_names=["image"],
        output_names=["logits"],
        dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        do_constant_folding=True,
        dynamo=False,
    )
    onnx.checker.check_model(onnx.load(str(args.output_model)))
    net = cv2.dnn.readNetFromONNX(str(args.output_model))
    parity_count = min(128, validation_y.numel())
    parity_input = validation_x[:parity_count].numpy()
    net.setInput(parity_input)
    opencv_logits = np.asarray(net.forward(), dtype=np.float32)
    torch_logits = final_logits[:parity_count].numpy()
    max_abs_error = float(np.max(np.abs(opencv_logits - torch_logits)))
    parity_agreement = float(
        np.mean(np.argmax(opencv_logits, axis=1) == np.argmax(torch_logits, axis=1))
    )
    dataset_manifest = json.loads(args.dataset_manifest.read_text(encoding="utf-8"))
    result = {
        "schema_version": 1,
        "model_id": "tiny-page-digit-cnn-v1",
        "format": "ONNX",
        "opset": 17,
        "runtime": "opencv-dnn",
        "runtime_dependencies": ["opencv-python", "numpy"],
        "training_dependencies": {
            "torch": torch.__version__,
            "onnx": onnx.__version__,
            "production_imported": False,
        },
        "seed": args.seed,
        "architecture": "conv12-conv24-conv32-maxpool-linear10",
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "input_shape": [1, 48, 32],
        "class_order": [str(value) for value in range(10)],
        "confidence_temperature": temperature,
        "dataset": {
            "path": str(args.dataset),
            "sha256": _sha256(args.dataset),
            "generator_version": dataset_manifest["generator_version"],
            "train_samples": int(train_y.numel()),
            "validation_samples": int(validation_y.numel()),
            "font_family_overlap": dataset_manifest["splits"]["font_family_overlap"],
        },
        "training": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "wall_seconds": time.perf_counter() - started,
            "best_validation_accuracy": best_accuracy,
            "history": history,
        },
        "onnx_parity": {
            "sample_count": parity_count,
            "argmax_agreement": parity_agreement,
            "max_abs_logit_error": max_abs_error,
        },
        "asset": {
            "path": str(args.output_model),
            "bytes": args.output_model.stat().st_size,
            "sha256": _sha256(args.output_model),
            "runtime_download_required": False,
        },
        "license": {
            "training_font_source": dataset_manifest["font_license"],
            "model_project_license_inheritance": True,
            "external_model_weights_used": False,
        },
        "validated": False,
        "scope_note": "Synthetic validation is not real-page production evidence.",
    }
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _calibrate_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    candidates = np.linspace(0.55, 3.0, 99)
    best_temperature = 1.0
    best_loss = math.inf
    rows = np.arange(labels.size)
    for temperature in candidates:
        scaled = logits / float(temperature)
        scaled -= scaled.max(axis=1, keepdims=True)
        log_probabilities = scaled - np.log(np.exp(scaled).sum(axis=1, keepdims=True))
        loss = -float(np.mean(log_probabilities[rows, labels]))
        if loss < best_loss:
            best_loss = loss
            best_temperature = float(temperature)
    return best_temperature


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
