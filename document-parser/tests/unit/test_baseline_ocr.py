import unittest

from document_parser.ocr.baseline import (
    DEFAULT_DETECTION_MODEL_NAME,
    DEFAULT_RECOGNITION_MODEL_NAME,
    create_baseline_ocr_adapter,
)


class BaselineOcrTests(unittest.TestCase):
    def test_baseline_ocr_is_paddleocr_v5(self):
        adapter = create_baseline_ocr_adapter()

        self.assertEqual(adapter.engine_id, "paddleocr-general-ocr")
        self.assertEqual(adapter.text_detection_model_name, DEFAULT_DETECTION_MODEL_NAME)
        self.assertEqual(adapter.text_recognition_model_name, DEFAULT_RECOGNITION_MODEL_NAME)
        self.assertEqual(adapter.text_detection_model_name, "PP-OCRv5_server_det")
        self.assertEqual(adapter.text_recognition_model_name, "korean_PP-OCRv5_mobile_rec")
        self.assertFalse(adapter.enable_mkldnn)
        self.assertEqual(adapter.cpu_threads, 2)
        self.assertEqual(adapter.text_det_limit_side_len, 1600)


if __name__ == "__main__":
    unittest.main()
