from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
from typing import Any, Protocol

from document_parser.ingest import ImageDocument
from document_parser.ocr.base import BBox, OcrPageResult, OcrToken


class PaddleOcrReader(Protocol):
    def predict(self, image: str) -> list[object]:
        """Return PaddleOCR v3 prediction results."""


class PaddleOcrGeneralAdapter:
    """General OCR adapter backed by PaddleOCR with Windows-safe defaults."""

    engine_id = "paddleocr-general-ocr"

    def __init__(
        self,
        model_home: Path | None = None,
        text_detection_model_name: str = "PP-OCRv5_server_det",
        text_recognition_model_name: str = "korean_PP-OCRv5_mobile_rec",
        text_detection_model_dir: Path | None = None,
        text_recognition_model_dir: Path | None = None,
        text_det_limit_side_len: int = 1600,
        text_det_limit_type: str = "max",
        enable_mkldnn: bool = False,
        cpu_threads: int = 2,
        device: str = "cpu",
        low_confidence_threshold: float = 0.5,
        reader: PaddleOcrReader | None = None,
    ) -> None:
        self.model_home = model_home
        self.text_detection_model_name = text_detection_model_name
        self.text_recognition_model_name = text_recognition_model_name
        self.text_detection_model_dir = text_detection_model_dir
        self.text_recognition_model_dir = text_recognition_model_dir
        self.text_det_limit_side_len = text_det_limit_side_len
        self.text_det_limit_type = text_det_limit_type
        self.enable_mkldnn = enable_mkldnn
        self.cpu_threads = cpu_threads
        self.device = device
        self.low_confidence_threshold = low_confidence_threshold
        self._reader = reader

    @property
    def engine_version(self) -> str:
        try:
            return importlib.metadata.version("paddleocr")
        except importlib.metadata.PackageNotFoundError:
            return "not-installed"

    def recognize(self, image: ImageDocument) -> OcrPageResult:
        raw_results = self.reader.predict(str(image.path))
        tokens = []
        skipped_count = 0
        for index, item in enumerate(iter_paddleocr_items(raw_results), start=1):
            token = token_from_paddleocr_item(item, image.page_id, index)
            if token is None:
                skipped_count += 1
            else:
                tokens.append(token)

        low_confidence_count = sum(1 for token in tokens if token.confidence < self.low_confidence_threshold)
        issues: list[dict[str, Any]] = []
        if low_confidence_count:
            issues.append({
                "code": "OCR_LOW_CONFIDENCE",
                "severity": "warning",
                "message": f"{low_confidence_count} PaddleOCR tokens below confidence {self.low_confidence_threshold:.2f}",
            })
        if skipped_count:
            issues.append({
                "code": "UNKNOWN",
                "severity": "warning",
                "message": f"{skipped_count} PaddleOCR results were skipped because they could not be normalized.",
            })

        return OcrPageResult(
            page_id=image.page_id,
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            tokens=tokens,
            raw_result={
                "adapter": self.engine_id,
                "cache_signature": self.cache_signature,
                "result_count": len(raw_results),
                "token_count": len(tokens),
                "skipped_count": skipped_count,
                "safe_runtime": {
                    "device": self.device,
                    "enable_mkldnn": self.enable_mkldnn,
                    "cpu_threads": self.cpu_threads,
                    "text_det_limit_side_len": self.text_det_limit_side_len,
                    "text_det_limit_type": self.text_det_limit_type,
                },
            },
            issues=issues,
        )

    @property
    def cache_signature(self) -> str:
        return (
            f"paddleocr:{self.engine_version}:det={self.text_detection_model_name}:"
            f"rec={self.text_recognition_model_name}:device={self.device}:"
            f"mkldnn={self.enable_mkldnn}:threads={self.cpu_threads}:"
            f"limit={self.text_det_limit_side_len}:{self.text_det_limit_type}"
        )

    @property
    def reader(self) -> PaddleOcrReader:
        if self._reader is None:
            configure_paddle_home(self.model_home)
            from paddleocr import PaddleOCR

            kwargs: dict[str, object] = {
                "device": self.device,
                "enable_mkldnn": self.enable_mkldnn,
                "cpu_threads": self.cpu_threads,
                "text_det_limit_side_len": self.text_det_limit_side_len,
                "text_det_limit_type": self.text_det_limit_type,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
                "text_detection_model_name": self.text_detection_model_name,
                "text_recognition_model_name": self.text_recognition_model_name,
            }
            if self.text_detection_model_dir is not None:
                kwargs["text_detection_model_dir"] = str(self.text_detection_model_dir)
            if self.text_recognition_model_dir is not None:
                kwargs["text_recognition_model_dir"] = str(self.text_recognition_model_dir)
            self._reader = PaddleOCR(**kwargs)
        return self._reader


def configure_paddle_home(model_home: Path | None) -> None:
    if model_home is None:
        return
    model_home.mkdir(parents=True, exist_ok=True)
    cache_home = model_home / ".cache"
    paddle_home = cache_home / "paddle"
    paddle_home.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(model_home)
    os.environ["USERPROFILE"] = str(model_home)
    os.environ["XDG_CACHE_HOME"] = str(cache_home)
    os.environ["PADDLE_HOME"] = str(paddle_home)


def iter_paddleocr_items(raw_results: list[object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for result in raw_results:
        if isinstance(result, dict):
            texts = result.get("rec_texts")
            scores = result.get("rec_scores")
            polys = result.get("rec_polys") or result.get("dt_polys")
            if isinstance(texts, list) and isinstance(scores, list):
                for text, score, poly in zip(texts, scores, polys if isinstance(polys, list) else []):
                    items.append({"text": text, "score": score, "poly": poly})
    return items


def token_from_paddleocr_item(item: dict[str, object], page_id: str, index: int) -> OcrToken | None:
    text = item.get("text")
    if not isinstance(text, str):
        return None
    try:
        confidence = float(item.get("score"))
    except (TypeError, ValueError):
        return None
    points = normalize_poly(item.get("poly"))
    if points is None:
        return None
    bbox = bbox_from_points(points)
    if bbox is None:
        return None
    return OcrToken(
        text=text,
        bbox=bbox,
        confidence=max(0.0, min(1.0, confidence)),
        token_id=f"{page_id}-paddleocr-t{index:04d}",
        raw={"points": points, "text": text, "confidence": confidence},
    )


def normalize_poly(poly: object) -> list[list[float]] | None:
    if hasattr(poly, "tolist"):
        poly = poly.tolist()
    if not isinstance(poly, (list, tuple)):
        return None
    points = []
    for point in poly:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        try:
            points.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError):
            return None
    return points if points else None


def bbox_from_points(points: list[list[float]]) -> BBox | None:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x = min(xs)
    min_y = min(ys)
    max_x = max(xs)
    max_y = max(ys)
    width = max_x - min_x
    height = max_y - min_y
    if width < 0 or height < 0:
        return None
    return BBox(x=min_x, y=min_y, width=width, height=height)
