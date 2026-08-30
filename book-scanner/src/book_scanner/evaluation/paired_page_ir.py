"""Page IR execution and same-source comparison for paired OCR inputs."""

from __future__ import annotations

import json
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Iterable

from book_scanner.evaluation.document_parser_braille import evaluate_page_ir_braille, page_ir_sha256
from book_scanner.evaluation.paired_ocr_inputs import sha256_file


def node_type_sequence(page_ir: dict[str, object]) -> list[str]:
    sequence: list[str] = []
    for page in page_ir.get("pages", []):
        if not isinstance(page, dict):
            continue
        for node in page.get("nodes", []):
            if isinstance(node, dict):
                sequence.append(str(node.get("content_type") or "UNKNOWN"))
    return sequence


def evaluate_paired_page_ir(page_ir: dict[str, object]) -> dict[str, object]:
    result = evaluate_page_ir_braille(page_ir)
    sequence = node_type_sequence(page_ir)
    result["node_type_sequence"] = sequence
    result["node_count"] = len(sequence)
    result["page_ir_sha256"] = page_ir_sha256(page_ir)
    return result


def sequence_similarity(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def compare_same_source(anchor: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    anchor_chars = int(anchor.get("preserved_text_character_count", 0))
    candidate_chars = int(candidate.get("preserved_text_character_count", 0))
    anchor_counts = Counter({str(k): int(v) for k, v in dict(anchor.get("node_type_counts", {})).items()})
    candidate_counts = Counter({str(k): int(v) for k, v in dict(candidate.get("node_type_counts", {})).items()})
    keys = sorted(set(anchor_counts) | set(candidate_counts))
    return {
        "schema_valid": bool(candidate.get("schema_valid")),
        "anchor_schema_valid": bool(anchor.get("schema_valid")),
        "text_similarity": SequenceMatcher(
            None,
            str(anchor.get("normalized_content_text", "")),
            str(candidate.get("normalized_content_text", "")),
        ).ratio(),
        "character_count": candidate_chars,
        "anchor_character_count": anchor_chars,
        "character_count_ratio": candidate_chars / anchor_chars if anchor_chars else None,
        "character_count_drop_fraction": (anchor_chars - candidate_chars) / anchor_chars if anchor_chars else None,
        "node_sequence_similarity": sequence_similarity(
            list(anchor.get("node_type_sequence", [])), list(candidate.get("node_type_sequence", []))
        ),
        "node_type_count_delta": {key: candidate_counts[key] - anchor_counts[key] for key in keys},
        "parse_issue_count_delta": int(candidate.get("parse_issue_count", 0)) - int(anchor.get("parse_issue_count", 0)),
        "braille_opportunity_delta": int(candidate.get("braille_opportunity_count", 0))
        - int(anchor.get("braille_opportunity_count", 0)),
        "braille_error_delta": int(candidate.get("braille_error_count", 0))
        - int(anchor.get("braille_error_count", 0)),
        "accuracy_claim_allowed": False,
    }


def cache_key_matches(record: dict[str, object], image_sha256: str, engine_signature: str) -> bool:
    return record.get("image_sha256") == image_sha256 and record.get("engine_signature") == engine_signature


def _read_cached_record(path: Path, image_sha256: str, engine_signature: str) -> dict[str, object] | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict) or not cache_key_matches(record, image_sha256, engine_signature):
        return None
    return record if isinstance(record.get("page_ir"), dict) else None


def find_cached_record(
    record_path: Path,
    cache_roots: Iterable[Path],
    image_sha256: str,
    engine_signature: str,
) -> tuple[dict[str, object] | None, str | None]:
    direct = _read_cached_record(record_path, image_sha256, engine_signature) if record_path.is_file() else None
    if direct is not None:
        return direct, str(record_path.resolve())
    for root in cache_roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in root.rglob("*.json"):
            if path.name == "summary.json":
                continue
            cached = _read_cached_record(path, image_sha256, engine_signature)
            if cached is not None:
                return cached, str(path.resolve())
    return None, None


def run_ocr_batch(
    artifacts: Iterable[dict[str, object]],
    output_dir: Path,
    *,
    adapter,
    engine_signature: str,
    build_page_ir: Callable,
    cache_roots: Iterable[Path] = (),
) -> list[dict[str, object]]:
    """Run one reusable adapter over READY artifacts; isolate per-item failures."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, object]] = []
    for artifact in artifacts:
        identifier = str(artifact.get("artifact_id") or "unknown")
        if artifact.get("status") != "READY":
            summaries.append({"artifact_id": identifier, "status": str(artifact.get("status") or "SKIPPED")})
            continue
        image_path = Path(str(artifact["image_path"]))
        image_sha = sha256_file(image_path)
        record_path = output_dir / f"{identifier}.json"
        cached, cache_source = find_cached_record(
            record_path, cache_roots, image_sha, engine_signature
        )
        try:
            page_ir = cached["page_ir"] if cached is not None else build_page_ir(
                [image_path], adapter=adapter, book_id=identifier
            )
            evaluation = evaluate_paired_page_ir(page_ir)
            record = {
                "artifact_id": identifier,
                "image_path": str(image_path.resolve()),
                "image_sha256": image_sha,
                "engine_signature": engine_signature,
                "cache_hit": cached is not None,
                "cache_source": cache_source,
                "page_ir": page_ir,
                "evaluation": evaluation,
            }
            record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            summaries.append({
                "artifact_id": identifier,
                "status": "COMPLETE",
                "record_path": str(record_path.resolve()),
                "cache_hit": cached is not None,
                "schema_valid": evaluation["schema_valid"],
                "character_count": evaluation["preserved_text_character_count"],
                "node_count": evaluation["node_count"],
                "braille_opportunity_count": evaluation["braille_opportunity_count"],
                "braille_error_count": evaluation["braille_error_count"],
            })
        except Exception as exc:  # One failed variant must not abort the batch.
            failure = {
                "artifact_id": identifier,
                "image_path": str(image_path.resolve()),
                "image_sha256": image_sha,
                "engine_signature": engine_signature,
                "status": "OCR_FAILED",
                "error": f"{type(exc).__name__}: {exc}",
            }
            record_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            summaries.append({**failure, "record_path": str(record_path.resolve())})
    return summaries


def build_phase_comparisons(records: Iterable[dict[str, object]], anchor_selector: Callable[[str], str]) -> list[dict[str, object]]:
    """Compare records grouped by capture/side using a caller-selected anchor id."""
    by_id = {str(record.get("artifact_id")): record for record in records if record.get("status") == "COMPLETE"}
    results: list[dict[str, object]] = []
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for record in by_id.values():
        parts = str(record["artifact_id"]).split("_")
        # Capture itself has a date and time separated by one underscore.
        if len(parts) < 7:
            continue
        groups.setdefault(("_".join(parts[:2]), parts[2]), []).append(record)
    for (capture, side), group in groups.items():
        anchor_id = anchor_selector(f"{capture}_{side}")
        anchor_record = by_id.get(anchor_id)
        if anchor_record is None:
            continue
        anchor_payload = json.loads(Path(anchor_record["record_path"]).read_text(encoding="utf-8"))
        for candidate in group:
            payload = json.loads(Path(candidate["record_path"]).read_text(encoding="utf-8"))
            results.append({
                "capture": capture,
                "side": side,
                "anchor_artifact_id": anchor_id,
                "candidate_artifact_id": candidate["artifact_id"],
                "comparison": compare_same_source(anchor_payload["evaluation"], payload["evaluation"]),
            })
    return results


def extraction_screening_verdict(comparisons: Iterable[dict[str, object]]) -> str:
    relevant = [item["comparison"] for item in comparisons if "seam_conservative" in item["candidate_artifact_id"]]
    if len(relevant) != 8:
        return "EXTRACTION_INCONCLUSIVE"
    if any(not item["schema_valid"] for item in relevant):
        return "OVERLAP_FALLBACK"
    if any((item["character_count_drop_fraction"] or 0.0) > 0.20 for item in relevant):
        return "OVERLAP_FALLBACK"
    # Opposite-page inclusion and manual golden checks are outside Page IR and
    # must be supplied before a positive candidate verdict is asserted.
    return "EXTRACTION_INCONCLUSIVE_PENDING_GOLDEN_AND_MASK_METRICS"


def select_postprocess_screening(geometry_summary: dict[str, object]) -> dict[str, object]:
    """Gate Phase C without changing its criteria after observing results."""
    if geometry_summary.get("status") != "COMPLETE":
        return {
            "status": "BLOCKED_PREREQUISITE",
            "reason": f"Phase B status is {geometry_summary.get('status')!r}, not COMPLETE",
            "selected_artifacts": [],
            "full_batch_allowed": False,
        }
    regressions: list[tuple[float, dict[str, object]]] = []
    for item in geometry_summary.get("comparisons", []):
        if not isinstance(item, dict) or item.get("geometry") == "none":
            continue
        comparison = item.get("comparison")
        if not isinstance(comparison, dict):
            continue
        drop = comparison.get("character_count_drop_fraction")
        drop_value = float(drop) if drop is not None else 0.0
        structural = float(comparison.get("node_sequence_similarity", 1.0)) < 0.8
        if not comparison.get("schema_valid") or drop_value > 0.20 or structural:
            regressions.append((drop_value, item))
    if not regressions:
        return {
            "status": "NO_POSTPROCESS_EVIDENCE",
            "reason": "No geometry variant met the predeclared OCR-regression screening trigger.",
            "selected_artifacts": [],
            "full_batch_allowed": False,
        }
    regressions.sort(key=lambda pair: pair[0], reverse=True)
    selected: list[str] = []
    preferred = [
        item for _drop, item in regressions
        if item.get("capture") == "20260826_174958" and item.get("side") == "right"
    ]
    if preferred:
        selected.append(str(preferred[0]["candidate_artifact_id"]))
    for _drop, item in regressions:
        identifier = str(item["candidate_artifact_id"])
        if identifier not in selected:
            selected.append(identifier)
        if len(selected) == 2:
            break
    return {
        "status": "SCREENING_REQUIRED",
        "reason": "At least one fixed Phase B regression trigger was observed.",
        "selected_artifacts": selected,
        "full_batch_allowed": False,
        "manual_golden_status": "MANUAL_GOLDEN_NOT_VERIFIED",
    }


def compare_repeated_captures(records: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Compare 174943/174953 variants as repeat stability, never accuracy."""
    results: list[dict[str, object]] = []
    prefix_a, prefix_b = "20260826_174943_", "20260826_174953_"
    for identifier, first in records.items():
        if not identifier.startswith(prefix_a):
            continue
        second_id = prefix_b + identifier[len(prefix_a):]
        second = records.get(second_id)
        if second is None:
            continue
        results.append({
            "first_artifact_id": identifier,
            "second_artifact_id": second_id,
            "comparison": compare_same_source(first["evaluation"], second["evaluation"]),
            "interpretation": "repeat_stability_only_not_accuracy",
        })
    return results


def select_ready_artifacts(
    manifest: dict[str, object],
    *,
    artifact_ids: Iterable[str] = (),
    capture_sides: Iterable[tuple[str, str]] = (),
) -> list[dict[str, object]]:
    """Select an exact resumable OCR queue without regenerating variant IDs."""
    ready = [item for item in manifest.get("artifacts", []) if item.get("status") == "READY"]
    requested_ids = set(artifact_ids)
    requested_sides = set(capture_sides)
    if not requested_ids and not requested_sides:
        return ready
    selected = [
        item for item in ready
        if item.get("artifact_id") in requested_ids
        or (str(item.get("capture")), str(item.get("side"))) in requested_sides
    ]
    found_ids = {str(item.get("artifact_id")) for item in selected}
    found_sides = {(str(item.get("capture")), str(item.get("side"))) for item in selected}
    missing_ids = sorted(requested_ids - found_ids)
    missing_sides = sorted(requested_sides - found_sides)
    if missing_ids or missing_sides:
        raise ValueError(f"requested READY artifacts not found: ids={missing_ids}, capture_sides={missing_sides}")
    return selected
