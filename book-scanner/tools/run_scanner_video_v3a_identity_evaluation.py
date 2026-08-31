"""Evaluate V3-A identity on committed V2 artifact bundles."""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from itertools import combinations
from pathlib import Path

from book_scanner.video.config import IdentityPolicy
from book_scanner.video.identity import OpenCVIdentityFingerprinter, compare_spread_identities
from book_scanner.video.types import (
    ArtifactId,
    FrameId,
    PageArtifactRef,
    PageSide,
    SpreadArtifactRef,
    SpreadId,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--same-ready-dir", type=Path, required=True)
    parser.add_argument("--diagnostic-ready-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    policy = IdentityPolicy()
    provider = OpenCVIdentityFingerprinter(policy)
    same_artifacts = _load_ready(args.same_ready_dir)
    diagnostic_artifacts = _load_ready(args.diagnostic_ready_dir) if args.diagnostic_ready_dir else []
    tracemalloc.start()
    started = time.perf_counter()
    identities = []
    per_artifact_ms = []
    for label, artifact in same_artifacts + diagnostic_artifacts:
        item_started = time.perf_counter()
        identities.append((label, artifact, provider.fingerprint_artifact(artifact)))
        per_artifact_ms.append(round((time.perf_counter() - item_started) * 1000.0, 3))
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    _current, peak_python_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    same_ids = identities[: len(same_artifacts)]
    diagnostic_ids = identities[len(same_artifacts) :]
    same_results = [
        _comparison(left[0], right[0], compare_spread_identities(left[2], right[2], policy))
        for left, right in combinations(same_ids, 2)
    ]
    diagnostic_results = [
        _comparison(left[0], right[0], compare_spread_identities(left[2], right[2], policy))
        for left, right in combinations(diagnostic_ids, 2)
    ]
    same_pass = bool(same_results) and all(
        item["match_kind"] in {"exact_duplicate", "visual_duplicate"}
        for item in same_results
    )
    payload = {
        "schema_version": 1,
        "status": "COMPLETE" if same_pass else "PROVISIONAL_THRESHOLD_NOT_VALIDATED",
        "algorithm_version": policy.algorithm_version,
        "policy": {
            "visual_hamming_max": policy.visual_hamming_max,
            "visual_projection_mae_max": policy.visual_projection_mae_max,
            "visual_feature_match_min": policy.visual_feature_match_min,
            "visual_hamming_relaxed_max": policy.visual_hamming_relaxed_max,
            "different_hamming_min": policy.different_hamming_min,
            "different_projection_mae_min": policy.different_projection_mae_min,
            "different_feature_match_max": policy.different_feature_match_max,
            "validated": policy.validated,
            "provenance": policy.provenance,
        },
        "same_page_positive": {
            "label_source": "user_confirmed_p30_captures",
            "artifact_count": len(same_artifacts),
            "pair_count": len(same_results),
            "all_pairs_duplicate_candidate": same_pass,
            "comparisons": same_results,
        },
        "diagnostic_unlabeled": {
            "ground_truth_verified": False,
            "note": "These comparisons are diagnostic only and are not counted as different-page accuracy.",
            "comparisons": diagnostic_results,
        },
        "pc_performance": {
            "artifact_count": len(identities),
            "total_fingerprint_ms": elapsed_ms,
            "per_artifact_ms": per_artifact_ms,
            "python_tracemalloc_peak_bytes": peak_python_bytes,
            "memory_scope_note": "Python-tracked allocations only; not process RSS or Raspberry Pi evidence.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _load_ready(path: Path | None) -> list[tuple[str, SpreadArtifactRef]]:
    if path is None:
        return []
    manifests = sorted(path.resolve().glob("*/manifest.json"))
    return [(manifest.parent.name, _artifact_ref(manifest)) for manifest in manifests]


def _artifact_ref(manifest_path: Path) -> SpreadArtifactRef:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    frame_id = FrameId(str(payload["source_frame_id"]))
    pages = payload["pages"]
    return SpreadArtifactRef(
        ArtifactId(str(payload["artifact_id"])),
        SpreadId(str(payload["spread_id"])),
        frame_id,
        _page_ref(PageSide.LEFT, frame_id, manifest_path.parent, pages["left"]),
        _page_ref(PageSide.RIGHT, frame_id, manifest_path.parent, pages["right"]),
        str(manifest_path),
        _sha256(manifest_path),
        str(payload["pipeline"]["evaluator_version"]),
    )


def _page_ref(side: PageSide, frame_id: FrameId, root: Path, payload: dict) -> PageArtifactRef:
    record = payload["files"]["uvdoc"]
    return PageArtifactRef(
        side,
        frame_id,
        str(root / record["path"]),
        str(record["sha256"]),
        int(record["width"]),
        int(record["height"]),
    )


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _comparison(left: str, right: str, comparison) -> dict[str, object]:
    return {
        "left_artifact": left,
        "right_artifact": right,
        "match_kind": comparison.kind.value,
        "compatible": comparison.compatible,
        "left_hamming": comparison.left_hamming,
        "right_hamming": comparison.right_hamming,
        "left_projection_mae": comparison.left_projection_mae,
        "right_projection_mae": comparison.right_projection_mae,
        "left_feature_match": comparison.left_feature_match,
        "right_feature_match": comparison.right_feature_match,
        "left_agrees": comparison.left_agrees,
        "right_agrees": comparison.right_agrees,
    }


if __name__ == "__main__":
    raise SystemExit(main())
