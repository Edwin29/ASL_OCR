"""Compatibility gate for the accessibility layer's Page IR input.

The Page IR schema (`schemas/page-ir.schema.json`) has no `schema_version`
field (see the plan document's open decision #7). Rather than adding one as a
side effect of this work -- which would touch the shared schema and validator
the OCR pipeline itself depends on -- this module checks a shallow
"compatibility profile" using fields the baseline pipeline already writes to
`engine_manifest`. A real breaking field change downstream is caught by the
fixture-based contract tests, not by this check; this check only rejects
inputs from a generator this adapter was never built to read (e.g. the legacy
token pipeline's output, or a future pipeline mode).
"""

from __future__ import annotations

SUPPORTED_PIPELINE_MODES = {"paddleocr_vl_baseline"}


class PageIrCompatibilityError(ValueError):
    """Raised when a Page IR payload is not from a pipeline this adapter
    understands, or is missing structure the accessibility layer requires."""


def check_compatibility_profile(payload: dict[str, object]) -> None:
    """Raise `PageIrCompatibilityError` if `payload` is not a Page IR document
    this adapter can safely consume. Does not validate the full schema --
    call `document_parser.validation.validate_document_ir` for that.
    """
    engine_manifest = payload.get("engine_manifest")
    if not isinstance(engine_manifest, dict):
        raise PageIrCompatibilityError("Page IR payload is missing 'engine_manifest'.")

    pipeline = engine_manifest.get("pipeline")
    mode = pipeline.get("mode") if isinstance(pipeline, dict) else None
    if mode not in SUPPORTED_PIPELINE_MODES:
        raise PageIrCompatibilityError(
            f"Unsupported pipeline mode {mode!r}; expected one of {sorted(SUPPORTED_PIPELINE_MODES)}. "
            "This Page IR was not produced by the PaddleOCR-VL baseline this adapter was built against."
        )

    problem_unit_detection = engine_manifest.get("problem_unit_detection")
    if not isinstance(problem_unit_detection, dict) or not problem_unit_detection.get("engine_id"):
        raise PageIrCompatibilityError(
            "Page IR payload has no 'problem_unit_detection' manifest entry; "
            "PROBLEM_UNIT structure nodes were not promoted before this adapter runs."
        )

    if not isinstance(payload.get("pages"), list):
        raise PageIrCompatibilityError("Page IR payload is missing a 'pages' list.")
