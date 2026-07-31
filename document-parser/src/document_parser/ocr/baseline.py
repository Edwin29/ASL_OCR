from __future__ import annotations

from pathlib import Path

from document_parser.ocr.paddleocr_adapter import PaddleOcrGeneralAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_HOME = PROJECT_ROOT / "data" / "debug" / "model_home"
DEFAULT_DETECTION_MODEL_NAME = "PP-OCRv5_server_det"
DEFAULT_RECOGNITION_MODEL_NAME = "korean_PP-OCRv5_mobile_rec"
DEFAULT_DETECTION_MODEL_DIR = DEFAULT_MODEL_HOME / ".paddlex" / "official_models" / DEFAULT_DETECTION_MODEL_NAME
DEFAULT_RECOGNITION_MODEL_DIR = DEFAULT_MODEL_HOME / ".paddlex" / "official_models" / DEFAULT_RECOGNITION_MODEL_NAME


def create_baseline_ocr_adapter(
    model_home: Path = DEFAULT_MODEL_HOME,
    text_detection_model_dir: Path = DEFAULT_DETECTION_MODEL_DIR,
    text_recognition_model_dir: Path = DEFAULT_RECOGNITION_MODEL_DIR,
    text_det_limit_side_len: int = 1600,
    text_det_limit_type: str = "max",
    enable_mkldnn: bool = False,
    cpu_threads: int = 2,
    device: str = "cpu",
) -> PaddleOcrGeneralAdapter:
    """Return the project baseline OCR adapter.

    The current baseline is PaddleOCR PP-OCRv5 with Windows-safe CPU defaults.
    Higher-level structure analysis remains a separate pipeline concern.
    """

    return PaddleOcrGeneralAdapter(
        model_home=model_home,
        text_detection_model_name=DEFAULT_DETECTION_MODEL_NAME,
        text_recognition_model_name=DEFAULT_RECOGNITION_MODEL_NAME,
        text_detection_model_dir=text_detection_model_dir,
        text_recognition_model_dir=text_recognition_model_dir,
        text_det_limit_side_len=text_det_limit_side_len,
        text_det_limit_type=text_det_limit_type,
        enable_mkldnn=enable_mkldnn,
        cpu_threads=cpu_threads,
        device=device,
    )
