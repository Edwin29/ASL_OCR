from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class ImageDocument:
    """Immutable metadata for a page image loaded from disk."""

    page_id: str
    path: Path
    width: int
    height: int
    mode: str
    image_format: str | None
    size_bytes: int
    sha256: str

    @property
    def long_edge(self) -> int:
        return max(self.width, self.height)

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height


class ImageIngestor:
    """Load page image metadata without mutating the source image."""

    def load(self, image_path: Path, page_id: str | None = None) -> ImageDocument:
        path = image_path.resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as image:
            width, height = image.size
            mode = image.mode
            image_format = image.format
        return ImageDocument(
            page_id=page_id or path.stem,
            path=path,
            width=width,
            height=height,
            mode=mode,
            image_format=image_format,
            size_bytes=path.stat().st_size,
            sha256=digest,
        )

