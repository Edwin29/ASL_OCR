from __future__ import annotations

import hashlib
import json
from pathlib import Path

from document_parser.ingest import ImageDocument
from document_parser.ocr.base import OcrPageResult


class OcrResultCache:
    """Filesystem cache for raw OCR adapter outputs."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def cache_key(self, image: ImageDocument, result: OcrPageResult) -> str:
        cache_signature = ""
        if isinstance(result.raw_result, dict):
            cache_signature = str(result.raw_result.get("cache_signature", ""))
        seed = f"{image.sha256}:{result.engine_id}:{result.engine_version}:{cache_signature}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]

    def path_for(self, image: ImageDocument, result: OcrPageResult) -> Path:
        return self.cache_dir / result.engine_id / f"{image.page_id}-{self.cache_key(image, result)}.json"

    def write(self, image: ImageDocument, result: OcrPageResult) -> Path:
        path = self.path_for(image, result)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "image": {
                "page_id": image.page_id,
                "path": str(image.path),
                "width": image.width,
                "height": image.height,
                "sha256": image.sha256,
            },
            "ocr_result": result.to_jsonable(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path
