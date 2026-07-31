from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any, Protocol

from document_parser.ingest import ImageDocument
from document_parser.ocr.base import BBox, OcrPageResult, OcrToken


class EasyOcrReader(Protocol):
    def readtext(
        self,
        image: str,
        detail: int = 1,
        paragraph: bool = False,
    ) -> list[object]:
        """Return EasyOCR detail=1 results."""


class EasyOcrGeneralAdapter:
    """General OCR adapter backed by EasyOCR.

    The EasyOCR dependency is imported lazily so the rest of the parser can be
    tested without installing the engine.
    """

    engine_id = "easyocr-general-ocr"

    def __init__(
        self,
        languages: tuple[str, ...] = ("ko", "en"),
        gpu: bool = False,
        model_storage_directory: Path | None = None,
        download_enabled: bool = False,
        low_confidence_threshold: float = 0.5,
        reader: EasyOcrReader | None = None,
    ) -> None:
        self.languages = languages
        self.gpu = gpu
        self.model_storage_directory = model_storage_directory
        self.download_enabled = download_enabled
        self.low_confidence_threshold = low_confidence_threshold
        self._reader = reader

    @property
    def engine_version(self) -> str:
        try:
            return importlib.metadata.version("easyocr")
        except importlib.metadata.PackageNotFoundError:
            return "not-installed"

    def recognize(self, image: ImageDocument) -> OcrPageResult:
        raw_results = self.reader.readtext(str(image.path), detail=1, paragraph=False)
        tokens = []
        skipped_count = 0
        for index, item in enumerate(raw_results, start=1):
            token = token_from_easyocr_result(item, image.page_id, index)
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
                "message": f"{low_confidence_count} EasyOCR tokens below confidence {self.low_confidence_threshold:.2f}",
            })
        if skipped_count:
            issues.append({
                "code": "UNKNOWN",
                "severity": "warning",
                "message": f"{skipped_count} EasyOCR results were skipped because they could not be normalized.",
            })

        return OcrPageResult(
            page_id=image.page_id,
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            tokens=tokens,
            raw_result={
                "adapter": self.engine_id,
                "cache_signature": self.cache_signature,
                "languages": list(self.languages),
                "gpu": self.gpu,
                "download_enabled": self.download_enabled,
                "result_count": len(raw_results),
                "skipped_count": skipped_count,
                "results": [jsonable_easyocr_result(item) for item in raw_results],
            },
            issues=issues,
        )

    @property
    def cache_signature(self) -> str:
        languages = ",".join(self.languages)
        model_dir = str(self.model_storage_directory) if self.model_storage_directory is not None else "default"
        return (
            f"easyocr:{self.engine_version}:languages={languages}:gpu={self.gpu}:"
            f"model_dir={model_dir}:low_confidence={self.low_confidence_threshold:.3f}"
        )

    @property
    def reader(self) -> EasyOcrReader:
        if self._reader is None:
            import easyocr

            kwargs: dict[str, object] = {
                "gpu": self.gpu,
                "download_enabled": self.download_enabled,
                "verbose": False,
            }
            if self.model_storage_directory is not None:
                kwargs["model_storage_directory"] = str(self.model_storage_directory)
            self._reader = easyocr.Reader(list(self.languages), **kwargs)
        return self._reader


def token_from_easyocr_result(item: object, page_id: str, index: int) -> OcrToken | None:
    parsed = parse_easyocr_result(item)
    if parsed is None:
        return None
    points, text, confidence = parsed
    bbox = bbox_from_points(points)
    if bbox is None:
        return None
    return OcrToken(
        text=text,
        bbox=bbox,
        confidence=confidence,
        token_id=f"{page_id}-easyocr-t{index:04d}",
        raw={
            "points": points,
            "text": text,
            "confidence": confidence,
        },
    )


def parse_easyocr_result(item: object) -> tuple[list[list[float]], str, float] | None:
    if not isinstance(item, (list, tuple)) or len(item) < 3:
        return None
    points_raw, text_raw, confidence_raw = item[0], item[1], item[2]
    if not isinstance(text_raw, str):
        return None
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        return None
    points = normalize_points(points_raw)
    if points is None:
        return None
    return points, text_raw, max(0.0, min(1.0, confidence))


def normalize_points(points_raw: object) -> list[list[float]] | None:
    if not isinstance(points_raw, (list, tuple)):
        return None
    points: list[list[float]] = []
    for point in points_raw:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError):
            return None
        points.append([x, y])
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


def jsonable_easyocr_result(item: object) -> dict[str, object]:
    parsed = parse_easyocr_result(item)
    if parsed is None:
        return {"raw": str(item), "normalized": False}
    points, text, confidence = parsed
    return {
        "points": points,
        "text": text,
        "confidence": confidence,
        "normalized": True,
    }
