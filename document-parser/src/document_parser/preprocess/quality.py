from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

from document_parser.assets.constants import ZIP_PAGE_RE
from document_parser.ingest import ImageDocument, ImageIngestor


QUALITY_PASS = "PASS"
QUALITY_PASS_WITH_CORRECTION = "PASS_WITH_CORRECTION"
QUALITY_LOW = "LOW_QUALITY"
QUALITY_REJECTED = "REJECTED"


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class QualityReport:
    page_id: str
    source: str
    status: str
    width: int
    height: int
    mode: str
    image_format: str | None
    long_edge: int
    aspect_ratio: float
    blur_score: float | None
    issues: list[QualityIssue]

    def to_jsonable(self) -> dict[str, object]:
        payload = asdict(self)
        payload["issues"] = [asdict(issue) for issue in self.issues]
        return payload


class ImageQualityGate:
    """Rule-based image quality checks used before OCR."""

    def __init__(
        self,
        min_long_edge: int = 1800,
        recommended_long_edge: int = 2800,
        aspect_ratio_range: tuple[float, float] = (0.68, 0.82),
        blur_warning_threshold: float = 25.0,
    ) -> None:
        self.min_long_edge = min_long_edge
        self.recommended_long_edge = recommended_long_edge
        self.aspect_ratio_range = aspect_ratio_range
        self.blur_warning_threshold = blur_warning_threshold

    def evaluate_path(self, image_path: Path, page_id: str | None = None) -> QualityReport:
        document = ImageIngestor().load(image_path, page_id=page_id)
        with Image.open(document.path) as image:
            blur_score = laplacian_variance(image)
        return self.evaluate_document(document, blur_score=blur_score, source=str(document.path))

    def evaluate_document(self, document: ImageDocument, blur_score: float | None, source: str) -> QualityReport:
        issues: list[QualityIssue] = []
        if document.long_edge < self.min_long_edge:
            issues.append(QualityIssue(
                code="LOW_RESOLUTION",
                severity="warning",
                message=f"Long edge {document.long_edge}px is below minimum OCR baseline {self.min_long_edge}px.",
            ))
        elif document.long_edge < self.recommended_long_edge:
            issues.append(QualityIssue(
                code="BELOW_RECOMMENDED_RESOLUTION",
                severity="info",
                message=f"Long edge {document.long_edge}px is below recommended {self.recommended_long_edge}px.",
            ))

        low_ratio, high_ratio = self.aspect_ratio_range
        if not (low_ratio <= document.aspect_ratio <= high_ratio):
            issues.append(QualityIssue(
                code="ASPECT_RATIO_OUT_OF_PROFILE",
                severity="warning",
                message=f"Aspect ratio {document.aspect_ratio:.3f} is outside {low_ratio:.2f}-{high_ratio:.2f}.",
            ))

        if document.mode not in {"RGB", "RGBA", "L"}:
            issues.append(QualityIssue(
                code="UNSUPPORTED_COLOR_MODE",
                severity="warning",
                message=f"Image mode {document.mode} should be converted before OCR.",
            ))

        if blur_score is not None and blur_score < self.blur_warning_threshold:
            issues.append(QualityIssue(
                code="POSSIBLE_BLUR",
                severity="warning",
                message=f"Laplacian variance {blur_score:.2f} is below blur warning threshold.",
            ))

        status = self._status_for(document, issues)
        return QualityReport(
            page_id=document.page_id,
            source=source,
            status=status,
            width=document.width,
            height=document.height,
            mode=document.mode,
            image_format=document.image_format,
            long_edge=document.long_edge,
            aspect_ratio=round(document.aspect_ratio, 6),
            blur_score=round(blur_score, 6) if blur_score is not None else None,
            issues=issues,
        )

    def _status_for(self, document: ImageDocument, issues: list[QualityIssue]) -> str:
        if document.width <= 0 or document.height <= 0:
            return QUALITY_REJECTED
        if any(issue.severity == "error" for issue in issues):
            return QUALITY_REJECTED
        if any(issue.code == "LOW_RESOLUTION" for issue in issues):
            return QUALITY_LOW
        if issues:
            return QUALITY_PASS_WITH_CORRECTION
        return QUALITY_PASS


def laplacian_variance(image: Image.Image) -> float:
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    if gray.size == 0:
        return 0.0
    center = gray[1:-1, 1:-1]
    if center.size == 0:
        return 0.0
    laplacian = (
        -4 * center
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    return float(np.var(laplacian))


def evaluate_zip_pages(zip_path: Path, page_numbers: Iterable[int]) -> list[QualityReport]:
    gate = ImageQualityGate()
    wanted = set(page_numbers)
    reports: list[QualityReport] = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            match = ZIP_PAGE_RE.search(info.filename)
            if not match:
                continue
            page_number = int(match.group(1))
            if page_number not in wanted:
                continue
            data = archive.read(info)
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
                document = ImageDocument(
                    page_id=f"zip-p{page_number:03d}",
                    path=Path(info.filename),
                    width=width,
                    height=height,
                    mode=image.mode,
                    image_format=image.format,
                    size_bytes=info.file_size,
                    sha256="",
                )
                blur_score = laplacian_variance(image)
            reports.append(gate.evaluate_document(document, blur_score=blur_score, source=f"{zip_path.name}!{info.filename}"))
    return sorted(reports, key=lambda report: report.page_id)


def evaluate_rendered_pages(image_dir: Path) -> list[QualityReport]:
    gate = ImageQualityGate()
    reports = []
    for image_path in sorted(image_dir.glob("*.png")):
        reports.append(gate.evaluate_path(image_path, page_id=image_path.stem))
    return reports


def write_quality_report(path: Path, reports: list[QualityReport]) -> None:
    payload = {
        "report_type": "image_quality",
        "report_count": len(reports),
        "status_counts": status_counts(reports),
        "reports": [report.to_jsonable() for report in reports],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def status_counts(reports: list[QualityReport]) -> dict[str, int]:
    counts = {QUALITY_PASS: 0, QUALITY_PASS_WITH_CORRECTION: 0, QUALITY_LOW: 0, QUALITY_REJECTED: 0}
    for report in reports:
        counts[report.status] = counts.get(report.status, 0) + 1
    return counts


def parse_page_spec(spec: str) -> list[int]:
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                raise ValueError(f"Invalid page range: {part}")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    return sorted(pages)


def main(argv: list[str] | None = None) -> int:
    from document_parser.assets.audit import detect_project_root, find_assets

    parser = argparse.ArgumentParser(description="Generate image quality reports for ZIP and rendered page images.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--rendered-dir", type=Path, default=Path("document-parser/data/pages_pdf300"))
    parser.add_argument("--zip-pages", default="3,4,8,12,19,20,54,102")
    parser.add_argument("--output", type=Path, default=Path("document-parser/data/debug/image_quality_report.json"))
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve() if args.project_root else detect_project_root()
    zip_path = find_assets(project_root).zip_path
    zip_reports = evaluate_zip_pages(zip_path, parse_page_spec(args.zip_pages))
    rendered_reports = evaluate_rendered_pages(args.rendered_dir.resolve())
    write_quality_report(args.output.resolve(), zip_reports + rendered_reports)
    print(f"Wrote {args.output.resolve()}")
    print(f"ZIP reports: {len(zip_reports)}")
    print(f"Rendered reports: {len(rendered_reports)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
