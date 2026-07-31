from __future__ import annotations

import importlib.metadata
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from document_parser.ocr.baseline import (
    DEFAULT_DETECTION_MODEL_DIR,
    DEFAULT_DETECTION_MODEL_NAME,
    DEFAULT_MODEL_HOME,
    DEFAULT_RECOGNITION_MODEL_DIR,
    DEFAULT_RECOGNITION_MODEL_NAME,
)
from document_parser.structure.domain_mapping import map_region_to_ebs_math_domain
from document_parser.structure.linking import link_structure_regions_to_text

DEFAULT_LAYOUT_MODEL_NAME = "PP-DocLayout_plus-L"
DEFAULT_LAYOUT_MODEL_DIR = DEFAULT_MODEL_HOME / ".paddlex" / "official_models" / DEFAULT_LAYOUT_MODEL_NAME


class StructureReader(Protocol):
    def predict(self, image: str) -> list[object]:
        """Return PaddleOCR PP-StructureV3 prediction results."""


@dataclass(frozen=True)
class StructureRegion:
    label: str
    bbox: dict[str, float]
    confidence: float
    raw: dict[str, object]


class PaddleStructureRegionAdapter:
    """Experimental PP-StructureV3 adapter for layout/table region candidates."""

    engine_id = "paddleocr-ppstructurev3-layout"

    def __init__(
        self,
        model_home: Path | None = DEFAULT_MODEL_HOME,
        text_detection_model_name: str = DEFAULT_DETECTION_MODEL_NAME,
        text_recognition_model_name: str = DEFAULT_RECOGNITION_MODEL_NAME,
        text_detection_model_dir: Path | None = DEFAULT_DETECTION_MODEL_DIR,
        text_recognition_model_dir: Path | None = DEFAULT_RECOGNITION_MODEL_DIR,
        layout_detection_model_name: str = DEFAULT_LAYOUT_MODEL_NAME,
        layout_detection_model_dir: Path | None = DEFAULT_LAYOUT_MODEL_DIR,
        layout_threshold: float = 0.35,
        backend: str = "layout_detection",
        device: str = "cpu",
        enable_mkldnn: bool = False,
        cpu_threads: int = 2,
        text_det_limit_side_len: int = 1600,
        text_det_limit_type: str = "max",
        use_table_recognition: bool = False,
        use_formula_recognition: bool = False,
        use_chart_recognition: bool = False,
        use_region_detection: bool = False,
        reader: StructureReader | None = None,
    ) -> None:
        self.model_home = model_home
        self.text_detection_model_name = text_detection_model_name
        self.text_recognition_model_name = text_recognition_model_name
        self.text_detection_model_dir = text_detection_model_dir
        self.text_recognition_model_dir = text_recognition_model_dir
        self.layout_detection_model_name = layout_detection_model_name
        self.layout_detection_model_dir = layout_detection_model_dir
        self.layout_threshold = layout_threshold
        self.backend = backend
        self.device = device
        self.enable_mkldnn = enable_mkldnn
        self.cpu_threads = cpu_threads
        self.text_det_limit_side_len = text_det_limit_side_len
        self.text_det_limit_type = text_det_limit_type
        self.use_table_recognition = use_table_recognition
        self.use_formula_recognition = use_formula_recognition
        self.use_chart_recognition = use_chart_recognition
        self.use_region_detection = use_region_detection
        self._reader = reader

    @property
    def engine_version(self) -> str:
        try:
            return importlib.metadata.version("paddleocr")
        except importlib.metadata.PackageNotFoundError:
            return "not-installed"

    def detect_regions(self, image_path: Path) -> list[StructureRegion]:
        raw_results = self.reader.predict(str(image_path))
        return structure_regions_from_results(raw_results)

    @property
    def reader(self) -> StructureReader:
        if self._reader is None:
            configure_structure_home(self.model_home)
            if self.backend == "layout_detection":
                from paddleocr import LayoutDetection

                kwargs: dict[str, object] = {
                    "model_name": self.layout_detection_model_name,
                    "threshold": self.layout_threshold,
                    "device": self.device,
                    "enable_mkldnn": self.enable_mkldnn,
                    "cpu_threads": self.cpu_threads,
                }
                if self.layout_detection_model_dir is not None:
                    kwargs["model_dir"] = str(self.layout_detection_model_dir)
                self._reader = LayoutDetection(**kwargs)
            elif self.backend == "pp_structurev3":
                from paddleocr import PPStructureV3

                kwargs = {
                    "device": self.device,
                    "enable_mkldnn": self.enable_mkldnn,
                    "cpu_threads": self.cpu_threads,
                    "layout_detection_model_name": self.layout_detection_model_name,
                    "layout_threshold": self.layout_threshold,
                    "text_detection_model_name": self.text_detection_model_name,
                    "text_recognition_model_name": self.text_recognition_model_name,
                    "text_det_limit_side_len": self.text_det_limit_side_len,
                    "text_det_limit_type": self.text_det_limit_type,
                    "use_doc_orientation_classify": False,
                    "use_doc_unwarping": False,
                    "use_textline_orientation": False,
                    "use_table_recognition": self.use_table_recognition,
                    "use_formula_recognition": self.use_formula_recognition,
                    "use_chart_recognition": self.use_chart_recognition,
                    "use_region_detection": self.use_region_detection,
                    "use_seal_recognition": False,
                    "format_block_content": False,
                }
                if self.layout_detection_model_dir is not None:
                    kwargs["layout_detection_model_dir"] = str(self.layout_detection_model_dir)
                if self.text_detection_model_dir is not None:
                    kwargs["text_detection_model_dir"] = str(self.text_detection_model_dir)
                if self.text_recognition_model_dir is not None:
                    kwargs["text_recognition_model_dir"] = str(self.text_recognition_model_dir)
                self._reader = PPStructureV3(**kwargs)
            else:
                raise ValueError(f"Unsupported Paddle structure backend: {self.backend}")
        return self._reader


def configure_structure_home(model_home: Path | None) -> None:
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


def apply_structure_regions_to_document(
    payload: dict[str, object],
    regions_by_page_id: dict[str, list[StructureRegion]],
) -> dict[str, object]:
    result = deepcopy(payload)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    result["pages"] = [
        apply_structure_regions_to_page(page, regions_by_page_id.get(str(page.get("page_id")), []))
        if isinstance(page, dict)
        else page
        for page in pages
    ]
    manifest = result.setdefault("engine_manifest", {})
    if isinstance(manifest, dict):
        manifest["structure_layout"] = {
            "engine_id": PaddleStructureRegionAdapter.engine_id,
            "mode": "experimental_region_candidates",
        }
    return result


def apply_structure_regions_to_page(
    page: dict[str, Any],
    regions: list[StructureRegion],
) -> dict[str, object]:
    page = deepcopy(page)
    if not regions:
        return page
    geometry = page.get("page_geometry") if isinstance(page.get("page_geometry"), dict) else {}
    page_width = number_value(geometry.get("width")) or 1.0
    page_height = number_value(geometry.get("height")) or 1.0
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    reading_order = [node_id for node_id in page.get("reading_order", []) if isinstance(node_id, str)]
    existing_ids = {str(node.get("node_id")) for node in nodes if isinstance(node.get("node_id"), str)}
    page_id = str(page.get("page_id", "page"))
    next_index = 1
    for region in regions:
        node_id = f"{page_id}-structure-r{next_index:03d}"
        next_index += 1
        while node_id in existing_ids:
            node_id = f"{page_id}-structure-r{next_index:03d}"
            next_index += 1
        existing_ids.add(node_id)
        node = structure_region_node(
            node_id=node_id,
            region=region,
            page_width=page_width,
            page_height=page_height,
            reading_order_index=len(reading_order),
        )
        nodes.append(node)
        reading_order.append(node_id)

    page["nodes"] = nodes
    page["reading_order"] = reading_order
    page = link_structure_regions_to_text(page)
    page.setdefault("parse_issues", [])
    if isinstance(page["parse_issues"], list):
        page["parse_issues"].append({
            "code": "STRUCTURE_REGION_CANDIDATES_ADDED",
            "severity": "info",
            "message": f"{len(regions)} experimental PaddleOCR structure region candidates were added.",
        })
    return page


def structure_region_node(
    node_id: str,
    region: StructureRegion,
    page_width: float,
    page_height: float,
    reading_order_index: int,
) -> dict[str, object]:
    bbox = clamp_bbox(region.bbox, page_width, page_height)
    label = normalize_label(region.label)
    domain_label = map_region_to_ebs_math_domain(region, page_width, page_height)
    node = {
        "node_id": node_id,
        "content_type": domain_label.content_type,
        "bbox": bbox,
        "normalized_bbox": normalize_bbox(bbox, page_width, page_height),
        "reading_order_index": reading_order_index,
        "confidence": region.confidence,
        "source_engine": PaddleStructureRegionAdapter.engine_id,
        "issues": [{
            "code": "STRUCTURE_REGION_CANDIDATE",
            "severity": "info",
            "message": f"Experimental PaddleOCR layout region candidate: {domain_label.domain_label}.",
        }],
        "layout": {
            "is_structure_region_candidate": True,
            "structure_label": domain_label.domain_label,
            "domain_mapping_reason": domain_label.reason,
            "raw_label": region.label,
            "normalized_raw_label": label,
            "raw": region.raw,
        },
    }
    if domain_label.content_type == "UNSUPPORTED_VISUAL":
        node["visual_type_candidate"] = domain_label.domain_label
    return node


def structure_regions_from_results(raw_results: list[object]) -> list[StructureRegion]:
    regions: list[StructureRegion] = []
    for result in raw_results:
        payload = jsonable_result(result)
        for candidate in iter_region_candidates(payload):
            region = structure_region_from_candidate(candidate)
            if region is not None:
                regions.append(region)
    return regions


def jsonable_result(result: object) -> object:
    json_attr = getattr(result, "json", None)
    if isinstance(json_attr, dict):
        return json_attr
    if callable(json_attr):
        payload = json_attr()
        if isinstance(payload, (dict, list)):
            return payload
    if isinstance(result, (dict, list)):
        return result
    if hasattr(result, "to_dict"):
        payload = result.to_dict()
        if isinstance(payload, (dict, list)):
            return payload
    return {}


def iter_region_candidates(payload: object) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    if isinstance(payload, list):
        for item in payload:
            candidates.extend(iter_region_candidates(item))
        return candidates
    if not isinstance(payload, dict):
        return candidates

    if looks_like_region(payload):
        candidates.append(payload)

    for key, value in payload.items():
        if key in {"input_path", "model_settings", "overall_ocr_res"}:
            continue
        if isinstance(value, (dict, list)):
            candidates.extend(iter_region_candidates(value))
    return candidates


def looks_like_region(payload: dict[str, object]) -> bool:
    return label_from_candidate(payload) is not None and coordinate_from_candidate(payload) is not None


def structure_region_from_candidate(candidate: dict[str, object]) -> StructureRegion | None:
    label = label_from_candidate(candidate)
    coordinate = coordinate_from_candidate(candidate)
    if label is None or coordinate is None:
        return None
    bbox = bbox_from_coordinate(coordinate)
    if bbox is None:
        return None
    return StructureRegion(
        label=label,
        bbox=bbox,
        confidence=score_from_candidate(candidate),
        raw=safe_raw_candidate(candidate),
    )


def label_from_candidate(candidate: dict[str, object]) -> str | None:
    for key in ("block_label", "label", "category", "cls_name", "class_name"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def coordinate_from_candidate(candidate: dict[str, object]) -> object | None:
    for key in ("coordinate", "bbox", "box", "rec_box"):
        if key in candidate:
            return candidate[key]
    return None


def score_from_candidate(candidate: dict[str, object]) -> float:
    for key in ("score", "confidence", "layout_score"):
        value = number_value(candidate.get(key))
        if value is not None:
            return max(0.0, min(1.0, value))
    return 0.0


def bbox_from_coordinate(coordinate: object) -> dict[str, float] | None:
    if hasattr(coordinate, "tolist"):
        coordinate = coordinate.tolist()
    if not isinstance(coordinate, (list, tuple)):
        return None
    if len(coordinate) == 4 and all(number_value(value) is not None for value in coordinate):
        left, top, right, bottom = [float(value) for value in coordinate]
        if right >= left and bottom >= top:
            return {"x": left, "y": top, "width": right - left, "height": bottom - top}
        return {"x": left, "y": top, "width": max(0.0, right), "height": max(0.0, bottom)}
    points = normalize_points(coordinate)
    if points is None:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}


def normalize_points(value: object) -> list[list[float]] | None:
    if not isinstance(value, (list, tuple)):
        return None
    points: list[list[float]] = []
    for point in value:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        x = number_value(point[0])
        y = number_value(point[1])
        if x is None or y is None:
            return None
        points.append([x, y])
    return points if points else None


def normalize_label(label: str) -> str:
    return label.strip().lower().replace(" ", "_").replace("-", "_")


def clamp_bbox(bbox: dict[str, float], page_width: float, page_height: float) -> dict[str, float]:
    x = max(0.0, min(float(bbox["x"]), page_width))
    y = max(0.0, min(float(bbox["y"]), page_height))
    width = max(0.0, min(float(bbox["width"]), page_width - x))
    height = max(0.0, min(float(bbox["height"]), page_height - y))
    return {"x": round(x, 3), "y": round(y, 3), "width": round(width, 3), "height": round(height, 3)}


def normalize_bbox(bbox: dict[str, float], page_width: float, page_height: float) -> dict[str, float]:
    return {
        "x": round(bbox["x"] / page_width, 6),
        "y": round(bbox["y"] / page_height, 6),
        "width": round(bbox["width"] / page_width, 6),
        "height": round(bbox["height"] / page_height, 6),
    }


def safe_raw_candidate(candidate: dict[str, object]) -> dict[str, object]:
    raw: dict[str, object] = {}
    for key in ("block_id", "block_order", "block_label", "label", "category", "score", "confidence"):
        value = candidate.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            raw[key] = value
    return raw


def number_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
