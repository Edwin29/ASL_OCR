"""Profile actual native recognizer on preserved native-input ROIs only."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from dataclasses import asdict

import cv2
from asl_device.app_config import DeviceAppConfig
from book_scanner.video.runtime_composition import _effective_scanner_config, _model_hashes
from book_scanner.video.page_number_recognizer import PaddleRoiDigitRecognizer, _candidate_regions
from book_scanner.video.types import PageSide
import book_scanner.video.page_number_recognizer as module

p = argparse.ArgumentParser()
p.add_argument('--config', type=Path, required=True)
p.add_argument('--rois', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
before = digest(module.__file__)
config = DeviceAppConfig.from_toml(a.config)
policy = _effective_scanner_config(config.scanner).page_number
recognizer = PaddleRoiDigitRecognizer(config.scanner.m1_model_dir, policy,
                                     expected_file_hashes=_model_hashes(config.scanner.m1_model_manifest))
original = recognizer._predict
calls = []
def timed_predict(image):
    start = time.perf_counter()
    result = original(image)
    calls.append(dict(text=result[0],score=result[1],ms=(time.perf_counter()-start)*1000))
    return result
recognizer._predict = timed_predict
rows = []
for repeat in range(2):
    for phase in ('reference','query'):
        for side in (PageSide.LEFT, PageSide.RIGHT):
            path = a.rois / f'{phase}-{side.value}-footer-roi.png'
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise ValueError(f'Cannot decode saved ROI: {path.name}')
            regions = _candidate_regions(image, side, policy.max_digits)[:4]
            calls.clear()
            start = time.perf_counter()
            result = recognizer.recognize(image, side)
            elapsed = (time.perf_counter()-start)*1000
            # Counterfactual accounting only: never skip a native call.
            first_valid = None
            for i in range(0,len(calls),2):
                if any(c['text'].isdigit() and policy.min_digits <= len(c['text']) <= policy.max_digits for c in calls[i:i+2]):
                    first_valid = i+2
                    break
            rows.append(dict(repeat=repeat,phase=phase,side=side.value,roi_sha256=digest(path),
                             regions=regions,recognition=asdict(result),elapsed_ms=elapsed,
                             calls=list(calls),first_valid_call_count=first_valid,
                             unused_tail_predict_ms=sum(c['ms'] for c in calls[first_valid:]) if first_valid else 0))
recognizer._predict = original
assert digest(module.__file__) == before
out = dict(source_sha256=before,config_sha256=digest(a.config),model_hashes=_model_hashes(config.scanner.m1_model_manifest),
           existing_source_unchanged=True,uploads=0,camera_requests=0,
           scope='Two repetitions of four preserved production-native ROIs. Tail savings are measured accounting, not an implemented optimization or live cadence claim.',rows=rows)
a.output.write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(dict(rows=[{k:v for k,v in r.items() if k not in ('calls','regions')} for r in rows]),indent=2))
