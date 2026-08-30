from __future__ import annotations

import sys
from pathlib import Path


TOOLS_ROOT = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from audit_paired_ocr_environment import classify_environment  # noqa: E402
from prepare_paired_golden_roi import unverified_checklist  # noqa: E402


def test_environment_classification_requires_gpu_paddle_and_assets():
    assets = {"PaddleOCR-VL-1.6": True, "PP-DocLayoutV3": True}
    assert classify_environment(False, [], assets) == "GPU_NOT_AVAILABLE"
    assert classify_environment(True, [{"gpu_ready": False}], assets) == "GPU_PRESENT_ENV_MISSING"
    assert classify_environment(
        True, [{"gpu_ready": True}], {**assets, "PP-DocLayoutV3": False}
    ) == "MODEL_ASSETS_INCOMPLETE"
    assert classify_environment(True, [{"gpu_ready": True}], assets) == "GPU_ENV_READY"


def test_golden_checklist_cannot_start_as_verified():
    checklist = unverified_checklist()
    assert {"giyeok_item", "table_structure", "important_formula"} <= set(checklist)
    assert all(item["verified_presence"] is None for item in checklist.values())
    assert all(item["verified_transcription"] is None for item in checklist.values())
    assert all(item["reviewer"] is None and item["reviewed_at"] is None for item in checklist.values())
