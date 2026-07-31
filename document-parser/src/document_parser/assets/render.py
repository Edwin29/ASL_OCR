from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Iterable

import pypdfium2 as pdfium

from document_parser.assets.audit import detect_project_root, find_assets


def parse_page_spec(spec: str) -> list[int]:
    pages: set[int] = set()
    for part in spec.split(","):
        item = part.strip()
        if not item:
            continue
        if "-" in item:
            start_text, end_text = item.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                raise ValueError(f"Invalid page range: {item}")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(item))
    if not pages:
        raise ValueError("No pages were requested.")
    return sorted(pages)


def safe_pdf_path(pdf_path: Path, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    target = work_dir / "source.pdf"
    if not target.exists() or target.stat().st_mtime < pdf_path.stat().st_mtime:
        shutil.copy2(pdf_path, target)
    return target


def render_pages(
    pdf_path: Path,
    output_dir: Path,
    page_numbers: Iterable[int],
    dpi: int = 300,
    file_prefix: str = "ebs_2027_math1",
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    working_pdf = safe_pdf_path(pdf_path, output_dir / "_render_work")
    document = pdfium.PdfDocument(str(working_pdf))
    scale = dpi / 72
    rendered: list[dict[str, object]] = []
    for page_number in page_numbers:
        if page_number < 1 or page_number > len(document):
            raise ValueError(f"Page {page_number} is outside the PDF page range 1-{len(document)}.")
        page = document[page_number - 1]
        image = page.render(scale=scale).to_pil()
        output_path = output_dir / f"{file_prefix}_p{page_number:03d}.png"
        image.save(output_path)
        rendered.append({
            "page_number": page_number,
            "output_path": str(output_path),
            "width": image.width,
            "height": image.height,
            "dpi": dpi,
        })
    return rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render selected PDF pages to PNG images.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("data/pages_pdf300"))
    parser.add_argument("--pages", required=True, help="Comma-separated pages or ranges, for example 3,4,8,12-14.")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--report", type=Path, default=Path("data/manifests/render_report.json"))
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve() if args.project_root else detect_project_root()
    pdf_path = find_assets(project_root).pdf_path
    rendered = render_pages(pdf_path, args.output_dir.resolve(), parse_page_spec(args.pages), dpi=args.dpi)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"rendered_pages": rendered}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered {len(rendered)} pages to {args.output_dir.resolve()}")
    print(f"Wrote {args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

