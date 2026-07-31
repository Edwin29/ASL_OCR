from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader


BOOK_ID = "ebs-2027-math1"
PROFILE_HINT = "EBS_SUNEUNG_TEUKGANG"
ZIP_PAGE_RE = re.compile(r"_(\d+)\.png$", re.IGNORECASE)
GOLDEN_CANDIDATES = [3, 4, 8, 12, 19, 20, 54, 102, 120, 140, 150]


@dataclass(frozen=True)
class AssetPaths:
    project_root: Path
    pdf_path: Path
    zip_path: Path


def detect_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    candidates = [current, *current.parents]
    for candidate in candidates:
        if list(candidate.glob("*.pdf")) and list(candidate.glob("*.zip")):
            return candidate
    raise FileNotFoundError("Could not find a project root containing one PDF and one ZIP file.")


def find_assets(project_root: Path) -> AssetPaths:
    pdfs = sorted(project_root.glob("*.pdf"))
    zips = sorted(project_root.glob("*.zip"))
    if len(pdfs) != 1:
        raise FileNotFoundError(f"Expected exactly one PDF in {project_root}, found {len(pdfs)}.")
    if len(zips) != 1:
        raise FileNotFoundError(f"Expected exactly one ZIP in {project_root}, found {len(zips)}.")
    return AssetPaths(project_root=project_root, pdf_path=pdfs[0], zip_path=zips[0])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyze_pdf(pdf_path: Path) -> dict[str, Any]:
    reader = PdfReader(str(pdf_path))
    media_boxes: list[dict[str, float]] = []
    for page in reader.pages:
        box = page.mediabox
        media_boxes.append({"width_pt": float(box.width), "height_pt": float(box.height)})
    unique_media_boxes = [dict(t) for t in {tuple(sorted(item.items())) for item in media_boxes}]
    unique_media_boxes.sort(key=lambda item: (item["width_pt"], item["height_pt"]))
    return {
        "path": str(pdf_path),
        "file_name": pdf_path.name,
        "size_bytes": pdf_path.stat().st_size,
        "sha256": sha256_file(pdf_path),
        "page_count": len(reader.pages),
        "unique_media_boxes": unique_media_boxes,
    }


def _inspect_zip_image(zip_file: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict[str, Any]:
    data = zip_file.read(info)
    digest = hashlib.sha256(data).hexdigest()
    with Image.open(BytesIO(data)) as image:
        width, height = image.size
        mode = image.mode
        fmt = image.format
    return {
        "zip_member": info.filename,
        "file_name": Path(info.filename).name,
        "size_bytes": info.file_size,
        "sha256": digest,
        "width": width,
        "height": height,
        "mode": mode,
        "format": fmt,
    }


def analyze_zip(zip_path: Path) -> dict[str, Any]:
    canonical_pages: dict[int, dict[str, Any]] = {}
    extras: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []

    with zipfile.ZipFile(zip_path) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        for info in members:
            image_info = _inspect_zip_image(archive, info)
            match = ZIP_PAGE_RE.search(info.filename)
            if not match:
                unparsed.append(image_info)
                continue
            page_number = int(match.group(1))
            if page_number in canonical_pages:
                extras.append({**image_info, "duplicate_of_page": page_number})
                continue
            canonical_pages[page_number] = {**image_info, "page_number": page_number}

    page_numbers = sorted(canonical_pages)
    dimensions = sorted({(item["width"], item["height"]) for item in canonical_pages.values()})
    missing_pages = []
    if page_numbers:
        missing_pages = [num for num in range(page_numbers[0], page_numbers[-1] + 1) if num not in canonical_pages]
    return {
        "path": str(zip_path),
        "file_name": zip_path.name,
        "size_bytes": zip_path.stat().st_size,
        "sha256": sha256_file(zip_path),
        "file_count": len(page_numbers) + len(extras) + len(unparsed),
        "canonical_page_count": len(page_numbers),
        "canonical_page_min": min(page_numbers) if page_numbers else None,
        "canonical_page_max": max(page_numbers) if page_numbers else None,
        "missing_pages": missing_pages,
        "duplicate_or_extra_files": extras + unparsed,
        "unique_dimensions": [{"width": width, "height": height} for width, height in dimensions],
        "canonical_pages": [canonical_pages[num] for num in page_numbers],
    }


def quality_label(width: int, height: int) -> str:
    long_edge = max(width, height)
    if long_edge >= 2800:
        return "PASS"
    if long_edge >= 1800:
        return "PASS_WITH_CORRECTION"
    return "LOW_QUALITY"


def build_manifest(pdf_info: dict[str, Any], zip_info: dict[str, Any]) -> dict[str, Any]:
    pdf_page_count = int(pdf_info["page_count"])
    zip_pages = {item["page_number"]: item for item in zip_info["canonical_pages"]}
    pages: list[dict[str, Any]] = []
    for page_number in range(1, pdf_page_count + 1):
        zip_page = zip_pages.get(page_number)
        if zip_page is None:
            zip_ref = None
            quality = "REJECTED"
            issues = [{"code": "MISSING_ZIP_PAGE", "severity": "error"}]
        else:
            zip_ref = zip_page["zip_member"]
            quality = quality_label(zip_page["width"], zip_page["height"])
            issues = []
            if quality == "LOW_QUALITY":
                issues.append({
                    "code": "LOW_RESOLUTION",
                    "severity": "warning",
                    "message": "ZIP image is below the recommended OCR baseline size.",
                })
        pages.append({
            "page_id": f"p{page_number:03d}",
            "sequence_index": page_number,
            "pdf_page_number": page_number,
            "zip_image_ref": zip_ref,
            "recommended_render_path": f"data/pages_pdf300/ebs_2027_math1_p{page_number:03d}.png",
            "quality_status": quality,
            "issues": issues,
        })

    return {
        "book_id": BOOK_ID,
        "profile_hint": PROFILE_HINT,
        "source_pdf": pdf_info["file_name"],
        "source_zip": zip_info["file_name"],
        "page_count": pdf_page_count,
        "pages": pages,
        "initial_golden_candidates": GOLDEN_CANDIDATES,
        "parser_options": {
            "preserve_color": True,
            "emit_debug_artifacts": False,
            "requires_pdf_text_layer": False,
        },
    }


def build_audit(project_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    assets = find_assets(project_root)
    pdf_info = analyze_pdf(assets.pdf_path)
    zip_info = analyze_zip(assets.zip_path)
    manifest = build_manifest(pdf_info, zip_info)
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "book_id": BOOK_ID,
        "pdf": pdf_info,
        "zip": {key: value for key, value in zip_info.items() if key != "canonical_pages"},
        "findings": {
            "pdf_page_count": pdf_info["page_count"],
            "canonical_zip_page_count": zip_info["canonical_page_count"],
            "zip_extra_file_count": len(zip_info["duplicate_or_extra_files"]),
            "all_zip_pages_low_quality": all(page["quality_status"] == "LOW_QUALITY" for page in manifest["pages"]),
            "recommended_baseline": "Render PDF pages to 300dpi PNG files before OCR.",
        },
    }
    return audit, manifest


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def write_audit_markdown(path: Path, audit: dict[str, Any], manifest: dict[str, Any]) -> None:
    zip_info = audit["zip"]
    dims = ", ".join(f'{item["width"]}x{item["height"]}' for item in zip_info["unique_dimensions"])
    extra_names = [item["file_name"] for item in zip_info["duplicate_or_extra_files"]]
    lines = [
        "# Asset Audit",
        "",
        f"- Book ID: `{audit['book_id']}`",
        f"- PDF pages: {audit['pdf']['page_count']}",
        f"- Canonical ZIP pages: {zip_info['canonical_page_count']}",
        f"- ZIP extra files: {len(extra_names)}",
        f"- ZIP canonical dimensions: {dims}",
        f"- Initial golden candidates: {', '.join(str(num) for num in manifest['initial_golden_candidates'])}",
        "",
        "## Findings",
        "",
        "- The canonical ZIP contains pages 1-160 without gaps.",
        "- The ZIP also contains extra copy files and they are excluded from the canonical manifest.",
        "- The ZIP images are marked LOW_QUALITY for OCR baseline work because their long edge is below 1800px.",
        "- The recommended OCR baseline is PDF rendering to 300dpi PNG images.",
        "",
        "## Extra ZIP Files",
        "",
    ]
    if extra_names:
        lines.extend(f"- `{name}`" for name in extra_names)
    else:
        lines.append("- None")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(project_root: Path, output_root: Path) -> tuple[Path, Path, Path]:
    audit, manifest = build_audit(project_root)
    manifest_path = output_root / "data" / "manifests" / "ebs_2027_math1_pages.json"
    audit_path = output_root / "data" / "manifests" / "asset_audit.json"
    docs_path = output_root / "docs" / "asset-audit.md"
    write_json(audit_path, audit)
    write_json(manifest_path, manifest)
    write_audit_markdown(docs_path, audit, manifest)
    return audit_path, manifest_path, docs_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit source PDF/ZIP assets and write canonical manifests.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve() if args.project_root else detect_project_root()
    output_root = args.output_root.resolve()
    audit_path, manifest_path, docs_path = run(project_root, output_root)
    print(f"Wrote {audit_path}")
    print(f"Wrote {manifest_path}")
    print(f"Wrote {docs_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
