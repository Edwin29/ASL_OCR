from __future__ import annotations

import importlib.metadata
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_HOME = PROJECT_ROOT / "data" / "debug" / "model_home"
DEFAULT_MODEL_NAME = "PP-FormulaNet_plus-M"
DEFAULT_MODEL_DIR = DEFAULT_MODEL_HOME / ".paddlex" / "official_models" / DEFAULT_MODEL_NAME


class FormulaOcrAdapter(Protocol):
    engine_id: str
    engine_version: str

    def recognize(self, image_path: Path) -> "FormulaRecognitionResult":
        """Run formula OCR on a crop and return raw LaTeX plus any issues."""


@dataclass(frozen=True)
class FormulaRecognitionResult:
    raw_latex: str
    issues: list[dict[str, Any]] = field(default_factory=list)


# A crop fed to a formula-only OCR model should never legitimately contain Hangul or
# CJK ideographs. A real observed failure mode (feeding a whole merged Korean+math
# line, since general OCR merged the line into a single un-splittable token) showed
# the model forcing Korean glyphs into nonsense LaTeX macros mixed with literal CJK
# characters. Any such character in the output is treated as a hard failure signal,
# not a usable formula.
UNEXPECTED_SCRIPT_PATTERN = re.compile(r"[가-힣一-鿿]")

# The same failure mode also produced runaway repeated-token output (e.g. the same
# ~10-character LaTeX fragment repeated hundreds of times), a classic degenerate
# generation collapse. A short substring repeating many times back-to-back is treated
# as a hard failure signal regardless of length.
DEGENERATE_REPETITION_PATTERN = re.compile(r"(.{3,20}?)\1{4,}")

MAX_PLAUSIBLE_LATEX_LENGTH = 300

# A recurring failure pattern found across multiple real crops: a very narrow
# formula region (a single italic variable sitting right against a Korean particle,
# e.g. the "n" in "n이") produces plausible-looking but meaningless LaTeX like
# "\mathcal{n}^{\circ}]" -- syntactically clean, so none of the other guards catch
# it. Every observed instance of this pattern came from a crop under ~70px wide;
# every genuine short-but-real formula (e.g. "a>=0") was comfortably wider. A
# single stray variable is not useful standalone content anyway (nothing to read
# aloud), so crops this narrow are held to a lower trust bar regardless of what the
# guards above find.
MIN_PLAUSIBLE_CROP_WIDTH_PX = 75


class PaddleFormulaOcrAdapter:
    """Formula OCR adapter backed by PaddleX PP-FormulaNet_plus-M."""

    engine_id = "paddlex-formula-recognition"

    def __init__(
        self,
        model_home: Path | None = None,
        model_name: str = "PP-FormulaNet_plus-M",
        model_dir: Path | None = None,
        device: str = "cpu",
        enable_mkldnn: bool = False,
        cpu_threads: int = 2,
        reader: Any | None = None,
    ) -> None:
        self.model_home = model_home
        self.model_name = model_name
        self.model_dir = model_dir
        self.device = device
        self.enable_mkldnn = enable_mkldnn
        self.cpu_threads = cpu_threads
        self._reader = reader

    @property
    def engine_version(self) -> str:
        try:
            return importlib.metadata.version("paddleocr")
        except importlib.metadata.PackageNotFoundError:
            return "not-installed"

    def recognize(self, image_path: Path) -> FormulaRecognitionResult:
        raw_results = self.reader.predict(str(image_path))
        raw_latex = ""
        for result in raw_results:
            payload = result.json if not callable(getattr(result, "json", None)) else result.json()
            res = payload.get("res") if isinstance(payload, dict) else None
            if isinstance(res, dict) and isinstance(res.get("rec_formula"), str):
                raw_latex = res["rec_formula"]
            break
        return FormulaRecognitionResult(raw_latex=raw_latex, issues=validate_formula_output(raw_latex))

    @property
    def reader(self) -> Any:
        if self._reader is None:
            configure_formula_ocr_home(self.model_home)
            from paddleocr import FormulaRecognition

            kwargs: dict[str, object] = {
                "model_name": self.model_name,
                "device": self.device,
                "enable_mkldnn": self.enable_mkldnn,
                "cpu_threads": self.cpu_threads,
            }
            if self.model_dir is not None:
                kwargs["model_dir"] = str(self.model_dir)
            self._reader = FormulaRecognition(**kwargs)
        return self._reader


def create_baseline_formula_ocr_adapter(
    model_home: Path = DEFAULT_MODEL_HOME,
    model_dir: Path = DEFAULT_MODEL_DIR,
    device: str = "cpu",
    enable_mkldnn: bool = False,
    cpu_threads: int = 2,
) -> PaddleFormulaOcrAdapter:
    """Return the project baseline formula OCR adapter (PP-FormulaNet_plus-M, Windows-safe CPU)."""

    return PaddleFormulaOcrAdapter(
        model_home=model_home,
        model_name=DEFAULT_MODEL_NAME,
        model_dir=model_dir,
        device=device,
        enable_mkldnn=enable_mkldnn,
        cpu_threads=cpu_threads,
    )


def validate_formula_output(raw_latex: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not raw_latex.strip():
        issues.append({
            "code": "FORMULA_OCR_EMPTY_OUTPUT",
            "severity": "warning",
            "message": "Formula OCR returned no LaTeX output.",
        })
        return issues

    if UNEXPECTED_SCRIPT_PATTERN.search(raw_latex):
        issues.append({
            "code": "FORMULA_OCR_UNEXPECTED_SCRIPT",
            "severity": "error",
            "message": (
                "Formula OCR output contains Hangul/CJK characters, which never belong in a real "
                "formula. This is a known failure signal for crops with mixed Korean/math content "
                "(the model force-fits Korean glyphs into bogus LaTeX tokens)."
            ),
        })

    if DEGENERATE_REPETITION_PATTERN.search(raw_latex):
        issues.append({
            "code": "FORMULA_OCR_DEGENERATE_REPETITION",
            "severity": "error",
            "message": "Formula OCR output contains a runaway repeated fragment (generation collapse).",
        })

    if len(raw_latex) > MAX_PLAUSIBLE_LATEX_LENGTH:
        issues.append({
            "code": "FORMULA_OCR_OUTPUT_TOO_LONG",
            "severity": "warning",
            "message": (
                f"Formula OCR output is {len(raw_latex)} characters, over the "
                f"{MAX_PLAUSIBLE_LATEX_LENGTH}-character plausibility limit for a single crop."
            ),
        })

    return issues


def configure_formula_ocr_home(model_home: Path | None) -> None:
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


def recognize_math_candidate_crops(
    crop_manifest: dict[str, Any],
    adapter: FormulaOcrAdapter,
    path_base: Path,
) -> dict[str, Any]:
    pages = crop_manifest.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Crop manifest must contain a pages list.")

    recognized_pages = []
    total_crops = 0
    trusted_crops = 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("page_id")
        crops = page.get("crops")
        if not isinstance(crops, list):
            crops = []

        recognized_crops = []
        for crop in crops:
            if not isinstance(crop, dict):
                continue
            crop_path = resolve_crop_path(crop.get("crop_path"), path_base)
            result = adapter.recognize(crop_path)
            issues = list(result.issues)
            narrow_issue = narrow_crop_issue(crop)
            if narrow_issue is not None:
                issues.append(narrow_issue)
            is_trusted = not any(issue.get("severity") == "error" for issue in issues)
            total_crops += 1
            trusted_crops += 1 if is_trusted else 0
            recognized_crops.append({
                **crop,
                "crop_path": str(crop_path),
                "recognized_formula": result.raw_latex,
                "formula_ocr_trusted": is_trusted,
                "formula_ocr_issues": issues,
            })

        recognized_pages.append({
            "page_id": page_id,
            "crop_count": len(recognized_crops),
            "crops": recognized_crops,
        })

    return {
        "formula_ocr_manifest_version": 1,
        "mode": "math_candidate_crop_formula_ocr",
        "source_crop_manifest_mode": crop_manifest.get("mode"),
        "engine_manifest": {
            "formula_ocr_engine": adapter.engine_id,
            "formula_ocr_engine_version": adapter.engine_version,
        },
        "page_count": len(recognized_pages),
        "crop_count": total_crops,
        "trusted_crop_count": trusted_crops,
        "untrusted_crop_count": total_crops - trusted_crops,
        "pages": recognized_pages,
    }


def narrow_crop_issue(crop: dict[str, Any]) -> dict[str, Any] | None:
    box = crop.get("bbox")
    if not isinstance(box, dict):
        return None
    width = box.get("width")
    if not isinstance(width, (int, float)) or isinstance(width, bool):
        return None
    if width >= MIN_PLAUSIBLE_CROP_WIDTH_PX:
        return None
    return {
        "code": "FORMULA_OCR_CROP_TOO_NARROW",
        "severity": "error",
        "message": (
            f"Crop is {width:.0f}px wide, under the {MIN_PLAUSIBLE_CROP_WIDTH_PX}px plausibility floor. "
            "Narrow single-variable regions have repeatedly produced syntactically clean but meaningless "
            "LaTeX (e.g. a stray variable glued to an adjacent Korean particle)."
        ),
    }


def resolve_crop_path(raw_path: object, path_base: Path) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("Crop manifest entry is missing crop_path.")
    crop_path = Path(raw_path)
    if not crop_path.is_absolute():
        crop_path = path_base / crop_path
    return crop_path.resolve()
