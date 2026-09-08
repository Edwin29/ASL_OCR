"""Demonstrate the error-contract cost of a proposed first-valid early return."""
import json
from pathlib import Path
import cv2
from book_scanner.video.page_number_recognizer import PaddleRoiDigitRecognizer, _candidate_regions
from book_scanner.video.config import PageNumberPolicy
from book_scanner.video.types import PageSide

roi = cv2.imread('docs/evidence/h1-camera-fresh-20260908-101447/footer-saved-production-native-02/query-left-footer-roi.png', cv2.IMREAD_GRAYSCALE)
assert roi is not None
recognizer = PaddleRoiDigitRecognizer.__new__(PaddleRoiDigitRecognizer)
recognizer.policy = PageNumberPolicy()
recognizer.calls = 0
assert len(_candidate_regions(roi, PageSide.LEFT, recognizer.policy.max_digits)) >= 2
calls = []
def predict(image):
    calls.append(len(calls)+1)
    if len(calls) == 3:
        raise RuntimeError('diagnostic late native inference error')
    return '28', .99
recognizer._predict = predict
try:
    recognizer.recognize(roi, PageSide.LEFT)
except RuntimeError as exc:
    result = dict(calls=calls,first_candidate_valid=True,production_result='raises RuntimeError',
                  exception=str(exc),early_return_would_skip_error=True,
                  conclusion='First-valid early return is not exception-equivalent; no optimization applied.')
else:
    raise AssertionError('Expected late error to propagate')
Path('docs/evidence/h1-investigation-20260908/late-exception-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
