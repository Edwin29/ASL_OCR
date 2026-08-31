"""Persistent OpenCV-only numeric recognizer for prelocalized footer ROIs."""

from __future__ import annotations

import math
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from .config import PageNumberPolicy
from .page_number import PageNumberRecognition, PageNumberStatus
from .types import PageSide

_GLYPH_SIZE = (32, 48)


@dataclass(frozen=True, slots=True)
class _GlyphCandidate:
    digit: str
    confidence: float
    bbox: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class _SequenceCandidate:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]


class OpenCVHogDigitRecognizer:
    """Small deterministic baseline; no OCR model download or text detector."""

    engine_id = "opencv-hog-knn-digits"
    engine_version = "1"
    preprocessing_version = "footer-roi-otsu-adaptive-v1"

    def __init__(self, policy: PageNumberPolicy = PageNumberPolicy()) -> None:
        self.policy = policy
        self._samples, self._labels = _synthetic_training_set()
        self.load_count = 1
        self.calls = 0

    def recognize(self, roi: np.ndarray, side: PageSide) -> PageNumberRecognition:
        self.calls += 1
        gray = _normalize_roi(roi)
        variants = _threshold_variants(gray)
        candidates = [candidate for binary in variants if (candidate := self._recognize_binary(binary, side))]
        if not candidates:
            return PageNumberRecognition(None, None, None, 0, PageNumberStatus.NOT_OBSERVED)
        groups: dict[str, list[_SequenceCandidate]] = {}
        for candidate in candidates:
            groups.setdefault(candidate.text, []).append(candidate)
        winner_text, winner_items = max(
            groups.items(),
            key=lambda item: (len(item[1]), sum(value.confidence for value in item[1]) / len(item[1])),
        )
        agreement = len(winner_items)
        confidence = float(sum(value.confidence for value in winner_items) / agreement)
        bbox = _union_bbox(tuple(value.bbox for value in winner_items))
        competing = len(groups) > 1 and max(len(items) for text, items in groups.items() if text != winner_text) >= agreement
        status = PageNumberStatus.CONFLICT if competing else PageNumberStatus.OBSERVED
        return PageNumberRecognition(winner_text, confidence, bbox, agreement, status)

    def _recognize_binary(self, binary: np.ndarray, side: PageSide) -> _SequenceCandidate | None:
        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, 8)
        height, width = binary.shape
        glyphs: list[_GlyphCandidate] = []
        min_height = max(8, round(height * 0.025))
        max_height = max(min_height + 1, round(height * 0.24))
        for index in range(1, count):
            x, y, w, h, area = (int(value) for value in stats[index])
            if h < min_height or h > max_height or w < 2 or area < 10:
                continue
            if w > h * 1.25 or w < max(1.0, h * 0.13):
                continue
            if y + h / 2.0 < height * 0.42:
                continue
            if area / max(1, w * h) < 0.08:
                continue
            glyph = binary[y : y + h, x : x + w]
            digit, confidence = self._classify(glyph)
            if confidence < 0.20:
                continue
            glyphs.append(_GlyphCandidate(digit, confidence, (x, y, w, h)))
        if not glyphs:
            return None
        glyphs.sort(key=lambda item: item.bbox[0])
        clusters: list[list[_GlyphCandidate]] = []
        current: list[_GlyphCandidate] = []
        for candidate in glyphs:
            if not current:
                current = [candidate]
                continue
            previous = current[-1]
            px, py, pw, ph = previous.bbox
            cx, cy, _cw, ch = candidate.bbox
            gap = cx - (px + pw)
            median_height = float(np.median([item.bbox[3] for item in current]))
            baseline_delta = abs((cy + ch) - (py + ph))
            compatible = (
                -2 <= gap <= median_height * 0.95
                and 0.55 <= ch / max(1, median_height) <= 1.75
                and baseline_delta <= max(ph, ch) * 0.42
            )
            if compatible:
                current.append(candidate)
            else:
                clusters.append(current)
                current = [candidate]
        if current:
            clusters.append(current)
        sequences = [
            _sequence(cluster)
            for cluster in clusters
            if self.policy.min_digits <= len(cluster) <= self.policy.max_digits
        ]
        if not sequences:
            return None

        def score(item: _SequenceCandidate) -> float:
            x, _y, w, _h = item.bbox
            center = (x + w / 2.0) / max(1, width)
            outer = 1.0 - center if side is PageSide.LEFT else center
            length_bonus = min(len(item.text), 3) * 0.09
            return item.confidence + outer * 0.38 + length_bonus

        return max(sequences, key=score)

    def _classify(self, glyph: np.ndarray) -> tuple[str, float]:
        feature = _hog_feature(_normalize_glyph(glyph))
        all_distances = np.sum((self._samples - feature) ** 2, axis=1)
        nearest = np.argsort(all_distances)[:5]
        labels = [int(self._labels[index]) for index in nearest]
        distance_values = [float(all_distances[index]) for index in nearest]
        votes: dict[int, list[float]] = {}
        for label, distance in zip(labels, distance_values):
            votes.setdefault(label, []).append(distance)
        winner, winner_distances = max(votes.items(), key=lambda item: (len(item[1]), -min(item[1])))
        vote_fraction = len(winner_distances) / len(labels)
        distance_score = math.exp(-min(winner_distances) / 1.5)
        confidence = max(0.0, min(1.0, 0.65 * vote_fraction + 0.35 * distance_score))
        return str(winner), confidence


class OpenCVDnnDigitRecognizer(OpenCVHogDigitRecognizer):
    """Tiny digits-only ONNX classifier executed by the existing OpenCV DNN runtime.

    The caller must provide both a local model path and its expected SHA-256.  The
    adapter never downloads assets and keeps one persistent ``cv2.dnn.Net`` per
    recognizer instance.  Sequence localization and threshold-variant agreement
    intentionally remain identical to the rejected HOG control so backend
    comparisons do not silently change the ROI or component policy.
    """

    engine_id = "opencv-dnn-page-digits"
    engine_version = "1"
    preprocessing_version = "footer-roi-adaptive-raw-scale-morph-dnn-v1"

    def __init__(
        self,
        model_path: str | Path,
        expected_sha256: str,
        policy: PageNumberPolicy = PageNumberPolicy(),
        *,
        confidence_temperature: float = 1.0,
    ) -> None:
        path = Path(model_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"page-number ONNX model does not exist: {path}")
        expected = expected_sha256.strip().lower()
        if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
            raise ValueError("expected_sha256 must be a lowercase SHA-256")
        actual = _file_sha256(path)
        if actual != expected:
            raise ValueError("page-number ONNX model SHA-256 mismatch")
        if not math.isfinite(confidence_temperature) or confidence_temperature <= 0.0:
            raise ValueError("confidence_temperature must be positive and finite")
        self.policy = policy
        self.model_path = path
        self.model_sha256 = actual
        self.model_bytes = path.stat().st_size
        self.confidence_temperature = float(confidence_temperature)
        self._net = cv2.dnn.readNetFromONNX(str(path))
        self.load_count = 1
        self.calls = 0

    def recognize(self, roi: np.ndarray, side: PageSide) -> PageNumberRecognition:
        self.calls += 1
        gray = _as_gray(roi)
        adaptive, clusters = _candidate_clusters(gray, side, self.policy.max_digits)
        # Seam-conservative crops intentionally preserve a narrow opposite-page
        # strip.  Absolute outermost-first ranking can therefore select the
        # smaller page number printed on that strip.  The active page footer is
        # the largest coherent numeric line in this fixed camera layout; use
        # median glyph height first and physical outer position only as a tie
        # breaker.  Ambiguous predictions still fail variant agreement below.
        width = gray.shape[1]
        clusters.sort(
            key=lambda cluster: (
                float(np.median([bbox[3] for bbox in cluster])),
                -_union_bbox(tuple(cluster))[0]
                if side is PageSide.LEFT
                else sum(_union_bbox(tuple(cluster))[index] for index in (0, 2)),
                -abs(len(cluster) - 3),
            ),
            reverse=True,
        )
        for cluster in clusters[:4]:
            if float(np.median([bbox[3] for bbox in cluster])) < gray.shape[0] * 0.045:
                continue
            glyph_boxes = _split_wide_glyph_boxes(adaptive, cluster, self.policy.max_digits)
            if not self.policy.min_digits <= len(glyph_boxes) <= self.policy.max_digits:
                continue
            variant_texts: list[tuple[str, float]] = []
            for variant in ("adaptive_raw", "adaptive_morph"):
                digits: list[str] = []
                confidences: list[float] = []
                for x, y, w, h in glyph_boxes:
                    glyph = adaptive[y : y + h, x : x + w]
                    if variant == "adaptive_morph":
                        glyph = cv2.morphologyEx(
                            glyph,
                            cv2.MORPH_CLOSE if h < 18 else cv2.MORPH_OPEN,
                            np.ones((2, 2), dtype=np.uint8),
                        )
                    digit, confidence = self._classify(glyph)
                    if not digit or confidence < 0.20:
                        digits = []
                        break
                    digits.append(digit)
                    confidences.append(confidence)
                if self.policy.min_digits <= len(digits) <= self.policy.max_digits:
                    variant_texts.append(("".join(digits), float(np.mean(confidences))))
            if not variant_texts:
                continue
            groups: dict[str, list[float]] = {}
            for text, confidence in variant_texts:
                groups.setdefault(text, []).append(confidence)
            winner, scores = max(groups.items(), key=lambda item: (len(item[1]), np.mean(item[1])))
            agreement = len(scores)
            status = PageNumberStatus.OBSERVED if agreement == len(variant_texts) else PageNumberStatus.CONFLICT
            return PageNumberRecognition(
                winner,
                float(np.mean(scores)),
                _union_bbox(tuple(cluster)),
                agreement,
                status,
            )
        return PageNumberRecognition(None, None, None, 0, PageNumberStatus.NOT_OBSERVED)

    def _classify(self, glyph: np.ndarray) -> tuple[str, float]:
        normalized = _normalize_glyph(glyph).astype(np.float32) / 255.0
        blob = normalized[None, None, :, :]
        self._net.setInput(blob)
        logits = np.asarray(self._net.forward(), dtype=np.float32).reshape(-1)
        if logits.size != 10 or not np.all(np.isfinite(logits)):
            return "", 0.0
        scaled = logits / self.confidence_temperature
        scaled -= float(np.max(scaled))
        probabilities = np.exp(scaled)
        denominator = float(np.sum(probabilities))
        if denominator <= 0.0 or not math.isfinite(denominator):
            return "", 0.0
        probabilities /= denominator
        winner = int(np.argmax(probabilities))
        return str(winner), float(probabilities[winner])


class PaddleRoiDigitRecognizer:
    """Optional recognition-only backend with an explicit, offline model path."""

    engine_id = "paddle-en-ppocrv5-mobile-rec-roi"
    engine_version = "1"
    preprocessing_version = "footer-component-roi-gray-clahe-v1"

    def __init__(
        self,
        model_dir: str | Path,
        policy: PageNumberPolicy = PageNumberPolicy(),
        *,
        expected_file_hashes: Mapping[str, str] | None = None,
        device: str | None = None,
    ) -> None:
        root = Path(model_dir).resolve()
        required = (root / "inference.json", root / "inference.pdiparams", root / "inference.yml")
        if not all(path.is_file() for path in required):
            raise FileNotFoundError("explicit Paddle recognition model is incomplete")
        verified_hashes: dict[str, str] = {}
        if expected_file_hashes is not None:
            if not expected_file_hashes:
                raise ValueError("expected_file_hashes must not be empty")
            for relative_name, expected_hash in expected_file_hashes.items():
                if not isinstance(relative_name, str) or not relative_name.strip():
                    raise ValueError("model asset name must be non-empty")
                relative = Path(relative_name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("model asset name must remain inside model_dir")
                expected = str(expected_hash).strip().lower()
                if len(expected) != 64 or any(value not in "0123456789abcdef" for value in expected):
                    raise ValueError("model asset SHA-256 must be lowercase hexadecimal")
                asset = (root / relative).resolve()
                if root not in asset.parents or not asset.is_file():
                    raise FileNotFoundError(f"model asset is missing: {relative_name}")
                actual = _file_sha256(asset)
                if actual != expected:
                    raise ValueError(f"model asset SHA-256 mismatch: {relative_name}")
                verified_hashes[relative_name] = actual
        try:
            from paddleocr import TextRecognition
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("Paddle recognition backend is not installed") from exc
        self.policy = policy
        self.model_dir = root
        self.verified_file_hashes = verified_hashes
        self.model_bytes = sum(path.stat().st_size for path in root.iterdir() if path.is_file())
        self.device = device
        self._model = TextRecognition(
            model_name="en_PP-OCRv5_mobile_rec",
            model_dir=str(root),
            **({"device": device} if device is not None else {}),
        )
        self.load_count = 1
        self.calls = 0

    def recognize(self, roi: np.ndarray, side: PageSide) -> PageNumberRecognition:
        self.calls += 1
        gray = _as_gray(roi)
        regions = _candidate_regions(gray, side, self.policy.max_digits)
        if not regions:
            return PageNumberRecognition(None, None, None, 0, PageNumberStatus.NOT_OBSERVED)
        candidates: list[PageNumberRecognition] = []
        for bbox in regions[:4]:
            x, y, w, h = bbox
            crop = gray[y : y + h, x : x + w]
            pad = max(4, round(h * 0.25))
            original = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
            enhanced = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4, 4)).apply(original)
            predictions = [self._predict(original), self._predict(enhanced)]
            valid = [item for item in predictions if item[0].isdigit() and self.policy.min_digits <= len(item[0]) <= self.policy.max_digits]
            if not valid:
                continue
            groups: dict[str, list[float]] = {}
            for text, score in valid:
                groups.setdefault(text, []).append(score)
            text, scores = max(groups.items(), key=lambda item: (len(item[1]), sum(item[1]) / len(item[1])))
            candidates.append(
                PageNumberRecognition(
                    text,
                    float(sum(scores) / len(scores)),
                    bbox,
                    len(scores),
                    PageNumberStatus.OBSERVED if len(scores) == 2 else PageNumberStatus.CONFLICT,
                )
            )
        if not candidates:
            return PageNumberRecognition(None, None, None, 0, PageNumberStatus.NOT_OBSERVED)
        # Regions are ranked from the physical outer edge inward.  Footer years
        # and section numbers may be recognized with higher confidence, so do
        # not let confidence override the fixed page-number position.
        return candidates[0]

    def _predict(self, image: np.ndarray) -> tuple[str, float]:
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        result_items = list(self._model.predict(input=image, batch_size=1))
        if len(result_items) != 1:
            return "", 0.0
        payload: Any = getattr(result_items[0], "json", None)
        if callable(payload):
            payload = payload()
        record = payload.get("res") if isinstance(payload, Mapping) else None
        if not isinstance(record, Mapping):
            return "", 0.0
        return str(record.get("rec_text", "")).strip(), float(record.get("rec_score", 0.0))


def _synthetic_training_set() -> tuple[np.ndarray, np.ndarray]:
    fonts = (
        cv2.FONT_HERSHEY_SIMPLEX,
        cv2.FONT_HERSHEY_DUPLEX,
        cv2.FONT_HERSHEY_COMPLEX,
        cv2.FONT_HERSHEY_TRIPLEX,
    )
    samples: list[np.ndarray] = []
    labels: list[float] = []
    for digit in range(10):
        for font in fonts:
            for scale in (0.75, 0.9, 1.05, 1.2):
                for thickness in (1, 2):
                    canvas = np.zeros((72, 64), dtype=np.uint8)
                    text = str(digit)
                    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
                    origin = ((canvas.shape[1] - tw) // 2, (canvas.shape[0] + th - baseline) // 2)
                    cv2.putText(canvas, text, origin, font, scale, 255, thickness, cv2.LINE_AA)
                    for angle in (-3.0, 0.0, 3.0):
                        matrix = cv2.getRotationMatrix2D((32, 36), angle, 1.0)
                        transformed = cv2.warpAffine(canvas, matrix, (64, 72), flags=cv2.INTER_LINEAR)
                        _threshold, transformed = cv2.threshold(transformed, 24, 255, cv2.THRESH_BINARY)
                        samples.append(_hog_feature(_normalize_glyph(transformed)))
                        labels.append(float(digit))
    return np.asarray(samples, dtype=np.float32), np.asarray(labels, dtype=np.float32)


def _normalize_roi(roi: np.ndarray) -> np.ndarray:
    gray = _as_gray(roi)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)


def _as_gray(roi: np.ndarray) -> np.ndarray:
    if not isinstance(roi, np.ndarray) or roi.size == 0:
        raise ValueError("recognizer ROI must be a non-empty ndarray")
    if roi.ndim == 3:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    elif roi.ndim == 2:
        gray = roi
    else:
        raise ValueError("recognizer ROI must be grayscale or BGR")
    return gray


def _threshold_variants(gray: np.ndarray) -> tuple[np.ndarray, ...]:
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _value, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    block_size = max(15, min(61, (min(gray.shape) // 8) | 1))
    adaptive = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block_size,
        9,
    )
    kernel = np.ones((2, 2), dtype=np.uint8)
    return (
        cv2.morphologyEx(otsu, cv2.MORPH_OPEN, kernel),
        cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, kernel),
    )


def _candidate_regions(
    gray: np.ndarray,
    side: PageSide,
    max_digits: int,
) -> list[tuple[int, int, int, int]]:
    _binary, clusters = _candidate_clusters(gray, side, max_digits)
    return [_union_bbox(tuple(cluster)) for cluster in clusters]


def _candidate_clusters(
    gray: np.ndarray,
    side: PageSide,
    max_digits: int,
) -> tuple[np.ndarray, list[list[tuple[int, int, int, int]]]]:
    height, width = gray.shape
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    block_size = max(31, min(81, (min(gray.shape) // 7) | 1))
    binary = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block_size,
        9,
    )
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, 8)
    components: list[tuple[int, int, int, int]] = []
    for index in range(1, count):
        x, y, w, h, area = (int(value) for value in stats[index])
        if y + h / 2.0 < height * 0.40:
            continue
        if h < max(10, height * 0.032) or h > height * 0.20:
            continue
        if not 0.14 <= w / max(1, h) <= 1.55:
            continue
        if not 0.10 <= area / max(1, w * h) <= 0.88:
            continue
        components.append((x, y, w, h))
    components.sort(key=lambda item: item[0])
    clusters: list[list[tuple[int, int, int, int]]] = []
    current: list[tuple[int, int, int, int]] = []
    for component in components:
        if not current:
            current = [component]
            continue
        px, py, pw, ph = current[-1]
        x, y, _w, h = component
        median_h = float(np.median([item[3] for item in current]))
        compatible = (
            -2 <= x - (px + pw) <= median_h * 0.75
            and 0.62 <= h / max(1, median_h) <= 1.55
            and abs((y + h) - (py + ph)) <= max(h, ph) * 0.38
        )
        if compatible:
            current.append(component)
        else:
            clusters.append(current)
            current = [component]
    if current:
        clusters.append(current)
    clusters = [cluster for cluster in clusters if 1 <= len(cluster) <= max_digits]

    multi = [cluster for cluster in clusters if len(cluster) >= 2]
    ranked = multi or clusters
    ranked.sort(
        key=lambda cluster: (
            _union_bbox(tuple(cluster))[0]
            if side is PageSide.LEFT
            else -sum((_union_bbox(tuple(cluster))[index] for index in (0, 2))),
            -_union_bbox(tuple(cluster))[2],
        )
    )
    return binary, ranked


def _cluster_count(
    region: tuple[int, int, int, int],
    components: list[tuple[int, int, int, int]],
) -> int:
    x, y, w, h = region
    return sum(
        1
        for cx, cy, cw, ch in components
        if x <= cx and y <= cy and cx + cw <= x + w and cy + ch <= y + h
    )


def _split_wide_glyph_boxes(
    binary: np.ndarray,
    cluster: list[tuple[int, int, int, int]],
    max_digits: int,
) -> list[tuple[int, int, int, int]]:
    """Split low-resolution digit pairs joined by threshold interpolation.

    At 1920px spread preview, footer digits are only about 12px tall and the
    `30` pair can become one connected component.  Corrected-page glyphs are
    taller and remain narrow.  A wide component is split only at its lowest
    central foreground projection, never into more than the configured digit
    count.
    """

    result: list[tuple[int, int, int, int]] = []
    for box in cluster:
        x, y, w, h = box
        remaining = max_digits - len(result)
        if remaining >= 2 and w / max(1, h) >= 0.85:
            glyph = binary[y : y + h, x : x + w]
            projection = np.count_nonzero(glyph, axis=0)
            start = max(2, round(w * 0.28))
            end = min(w - 2, round(w * 0.72))
            if end > start:
                split = start + int(np.argmin(projection[start:end]))
                left_width = split
                right_start = split
                while right_start < w - 1 and projection[right_start] == 0:
                    right_start += 1
                if left_width >= 2 and w - right_start >= 2:
                    result.extend(
                        [
                            (x, y, left_width, h),
                            (x + right_start, y, w - right_start, h),
                        ]
                    )
                    continue
        result.append(box)
    return result


def _normalize_glyph(glyph: np.ndarray) -> np.ndarray:
    binary = (glyph > 0).astype(np.uint8) * 255
    ys, xs = np.nonzero(binary)
    if not len(xs):
        return np.zeros((_GLYPH_SIZE[1], _GLYPH_SIZE[0]), dtype=np.uint8)
    crop = binary[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    target_w, target_h = _GLYPH_SIZE
    scale = min((target_w - 8) / max(1, crop.shape[1]), (target_h - 8) / max(1, crop.shape[0]))
    size = (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale)))
    resized = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
    canvas = np.zeros((target_h, target_w), dtype=np.uint8)
    x = (target_w - size[0]) // 2
    y = (target_h - size[1]) // 2
    canvas[y : y + size[1], x : x + size[0]] = resized
    return canvas


def _hog_feature(glyph: np.ndarray) -> np.ndarray:
    image = glyph.astype(np.float32) / 255.0
    gx = cv2.Sobel(image, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(image, cv2.CV_32F, 0, 1, ksize=3)
    magnitude, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    angle %= 180.0
    bins = np.floor(angle / 20.0).astype(np.int32) % 9
    histograms: list[np.ndarray] = []
    for y in range(0, _GLYPH_SIZE[1], 8):
        for x in range(0, _GLYPH_SIZE[0], 8):
            cell_bins = bins[y : y + 8, x : x + 8].reshape(-1)
            cell_magnitude = magnitude[y : y + 8, x : x + 8].reshape(-1)
            histograms.append(np.bincount(cell_bins, weights=cell_magnitude, minlength=9).astype(np.float32))
    feature = np.concatenate(histograms)
    norm = float(np.linalg.norm(feature))
    return feature if norm == 0.0 else feature / norm


def _sequence(glyphs: list[_GlyphCandidate]) -> _SequenceCandidate:
    return _SequenceCandidate(
        "".join(item.digit for item in glyphs),
        float(sum(item.confidence for item in glyphs) / len(glyphs)),
        _union_bbox(tuple(item.bbox for item in glyphs)),
    )


def _union_bbox(boxes: tuple[tuple[int, int, int, int], ...]) -> tuple[int, int, int, int]:
    x0 = min(item[0] for item in boxes)
    y0 = min(item[1] for item in boxes)
    x1 = max(item[0] + item[2] for item in boxes)
    y1 = max(item[1] + item[3] for item in boxes)
    return x0, y0, x1 - x0, y1 - y0


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
