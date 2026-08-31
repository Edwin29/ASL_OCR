"""Generate deterministic, split-safe synthetic footer digit glyphs.

This is an offline training tool.  It is deliberately outside the production
package import graph and uses only OpenCV's built-in Hershey fonts, whose source
is distributed under OpenCV's Apache-2.0 license.  No font file or generated
training tensor is required by the scanner runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from book_scanner.video.page_number_recognizer import _normalize_glyph


@dataclass(frozen=True, slots=True)
class FontSpec:
    family: str
    license: str
    source: int | Path


TRAIN_FONTS = (
    FontSpec("FONT_HERSHEY_SIMPLEX", "OpenCV-Apache-2.0", cv2.FONT_HERSHEY_SIMPLEX),
    FontSpec("FONT_HERSHEY_DUPLEX", "OpenCV-Apache-2.0", cv2.FONT_HERSHEY_DUPLEX),
    FontSpec("FONT_HERSHEY_COMPLEX", "OpenCV-Apache-2.0", cv2.FONT_HERSHEY_COMPLEX),
)
VALIDATION_FONTS = (
    FontSpec("FONT_HERSHEY_TRIPLEX", "OpenCV-Apache-2.0", cv2.FONT_HERSHEY_TRIPLEX),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--train-per-digit", type=int, default=600)
    parser.add_argument("--validation-per-digit", type=int, default=180)
    parser.add_argument(
        "--train-font",
        action="append",
        default=[],
        metavar="FAMILY|LICENSE|PATH",
        help="Use a local font for training without copying it into the dataset.",
    )
    parser.add_argument(
        "--validation-font",
        action="append",
        default=[],
        metavar="FAMILY|LICENSE|PATH",
        help="Use a disjoint local font family for validation.",
    )
    args = parser.parse_args()
    if args.train_per_digit <= 0 or args.validation_per_digit <= 0:
        parser.error("per-digit counts must be positive")

    train_fonts = _parse_fonts(args.train_font) if args.train_font else TRAIN_FONTS
    validation_fonts = _parse_fonts(args.validation_font) if args.validation_font else VALIDATION_FONTS
    train_families = {font.family for font in train_fonts}
    validation_families = {font.family for font in validation_fonts}
    overlap = sorted(train_families & validation_families)
    if overlap:
        parser.error(f"font families must be split-safe; overlap: {overlap}")
    train_x, train_y = _make_split(args.seed, args.train_per_digit, train_fonts)
    validation_x, validation_y = _make_split(
        args.seed + 1_000_003,
        args.validation_per_digit,
        validation_fonts,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        train_x=train_x,
        train_y=train_y,
        validation_x=validation_x,
        validation_y=validation_y,
    )
    payload = {
        "schema_version": 1,
        "generator_version": "opencv-freetype-page-digit-v2",
        "seed": args.seed,
        "output_sha256": _sha256(args.output),
        "input_shape": [1, 48, 32],
        "normalization": "binary_foreground_0_or_1_centered_with_8px_margin",
        "splits": {
            "train": {
                "samples": int(train_y.size),
                "per_digit": args.train_per_digit,
                "font_families": sorted(train_families),
            },
            "validation": {
                "samples": int(validation_y.size),
                "per_digit": args.validation_per_digit,
                "font_families": sorted(validation_families),
            },
            "font_family_overlap": overlap,
        },
        "font_license": {
            "sources": [_font_provenance(font) for font in (*train_fonts, *validation_fonts)],
            "redistributed_font_files": False,
            "opencv_version": cv2.__version__,
        },
        "augmentations": [
            "rotation_-8_to_8_deg",
            "scale_0.72_to_1.32",
            "translation_up_to_4px",
            "x_shear_-0.10_to_0.10",
            "gaussian_blur_0_to_1.15",
            "erosion_or_dilation_probability_0.18",
            "jpeg_quality_45_to_95_probability_0.35",
            "salt_pepper_probability_up_to_0.012",
        ],
        "sequence_probes": ["1", "30", "309", "9999", "316", "317"],
        "hard_negative_probes": ["2026", "11.4", "Level", "EBS", "①", "기초연습"],
        "scope_note": (
            "Synthetic tensors are training/tuning data only. Real corrected and preview labels "
            "remain the backend selection evidence."
        ),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _make_split(
    seed: int,
    per_digit: int,
    fonts: tuple[FontSpec, ...],
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    images: list[np.ndarray] = []
    labels: list[int] = []
    for digit in range(10):
        for _ordinal in range(per_digit):
            font = fonts[int(rng.integers(0, len(fonts)))]
            images.append(_render_digit(str(digit), font, rng))
            labels.append(digit)
    order = rng.permutation(len(labels))
    x = np.asarray(images, dtype=np.float32)[order, None, :, :] / 255.0
    y = np.asarray(labels, dtype=np.int64)[order]
    return x, y


def _render_digit(digit: str, font: FontSpec, rng: np.random.Generator) -> np.ndarray:
    canvas = np.zeros((80, 64), dtype=np.uint8)
    if isinstance(font.source, int):
        scale = float(rng.uniform(0.72, 1.32))
        thickness = int(rng.integers(1, 3))
        (text_width, text_height), baseline = cv2.getTextSize(digit, font.source, scale, thickness)
        origin = (
            (canvas.shape[1] - text_width) // 2 + int(rng.integers(-3, 4)),
            (canvas.shape[0] + text_height - baseline) // 2 + int(rng.integers(-4, 5)),
        )
        cv2.putText(canvas, digit, origin, font.source, scale, 255, thickness, cv2.LINE_AA)
    else:
        size = int(rng.integers(31, 59))
        pil_font = ImageFont.truetype(str(font.source), size=size)
        image = Image.fromarray(canvas)
        draw = ImageDraw.Draw(image)
        left, top, right, bottom = draw.textbbox((0, 0), digit, font=pil_font)
        text_width, text_height = right - left, bottom - top
        origin = (
            (canvas.shape[1] - text_width) // 2 - left + int(rng.integers(-3, 4)),
            (canvas.shape[0] - text_height) // 2 - top + int(rng.integers(-4, 5)),
        )
        draw.text(origin, digit, font=pil_font, fill=255)
        canvas = np.asarray(image)
    angle = float(rng.uniform(-8.0, 8.0))
    matrix = cv2.getRotationMatrix2D((32.0, 40.0), angle, 1.0)
    matrix[0, 1] += float(rng.uniform(-0.10, 0.10))
    matrix[0, 2] += float(rng.uniform(-2.0, 2.0))
    matrix[1, 2] += float(rng.uniform(-2.0, 2.0))
    image = cv2.warpAffine(canvas, matrix, (64, 80), flags=cv2.INTER_LINEAR, borderValue=0)
    sigma = float(rng.uniform(0.0, 1.15))
    if sigma >= 0.15:
        image = cv2.GaussianBlur(image, (3, 3), sigma)
    morphology = float(rng.random())
    if morphology < 0.09:
        image = cv2.erode(image, np.ones((2, 2), np.uint8), iterations=1)
    elif morphology < 0.18:
        image = cv2.dilate(image, np.ones((2, 2), np.uint8), iterations=1)
    if rng.random() < 0.35:
        quality = int(rng.integers(45, 96))
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ok:
            decoded = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
            if decoded is not None:
                image = decoded
    noise_probability = float(rng.uniform(0.0, 0.012))
    if noise_probability > 0.002:
        noise = rng.random(image.shape)
        image = image.copy()
        image[noise < noise_probability / 2.0] = 0
        image[noise > 1.0 - noise_probability / 2.0] = 255
    _threshold, binary = cv2.threshold(image, 24, 255, cv2.THRESH_BINARY)
    return _normalize_glyph(binary)


def _parse_fonts(values: list[str]) -> tuple[FontSpec, ...]:
    result: list[FontSpec] = []
    for value in values:
        parts = value.split("|", 2)
        if len(parts) != 3 or not parts[0].strip() or not parts[1].strip():
            raise ValueError("font must use FAMILY|LICENSE|PATH")
        path = Path(parts[2]).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"font does not exist: {path}")
        result.append(FontSpec(parts[0].strip(), parts[1].strip(), path))
    return tuple(result)


def _font_provenance(font: FontSpec) -> dict[str, object]:
    if isinstance(font.source, int):
        return {
            "family": font.family,
            "license": font.license,
            "source": "opencv_builtin_hershey",
        }
    return {
        "family": font.family,
        "license": font.license,
        "source": "local_file_not_redistributed",
        "file_name": font.source.name,
        "sha256": _sha256(font.source),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
