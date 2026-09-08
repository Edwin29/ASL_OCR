"""Bounded read-only camera/identity phase; no upload, STM, audio or app state.

Uses production snapshot/threaded source and native preview ROI/provider.
Does not claim to run DeviceApplication or the production engine scheduler.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
from asl_device.app_config import DeviceAppConfig
from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.composition import PaddleOpaqueIdentityBackendConfig, compose_m1_page_number_provider
from book_scanner.video.engine import _page_number_preview_inputs
from book_scanner.video.opaque_identity import token_pair_from_page_observation
from book_scanner.video.operator_preview import ThreadedPreviewCameraSource
from book_scanner.video.runtime_composition import _effective_scanner_config, _model_hashes, create_snapshot_source

class NullPreview:
    def start(self): pass
    def show(self, frame): pass
    def stop(self): pass

p = argparse.ArgumentParser()
p.add_argument('--config',type=Path,required=True)
p.add_argument('--phase',choices=['reference-26-27','query-28-29'],required=True)
p.add_argument('--output',type=Path,required=True)
a = p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
config = DeviceAppConfig.from_toml(a.config)
scanner = _effective_scanner_config(config.scanner)
policy = scanner.opaque_footer_identity
assert config.scanner.profile == 'android_ip_camera'
assert policy.query_sample_count == 5 and policy.max_collection_ms == 8000
analyzer = OpenCVCandidateAnalyzer(scanner.candidate)
provider = compose_m1_page_number_provider(scanner,PaddleOpaqueIdentityBackendConfig(
    model_dir=config.scanner.m1_model_dir,expected_file_hashes=_model_hashes(config.scanner.m1_model_manifest)))
camera = ThreadedPreviewCameraSource(create_snapshot_source(config.scanner),NullPreview(),source_label='android_ip_camera:snapshot:diagnostic')
result = dict(phase=a.phase,python=sys.executable,config_sha256=hashlib.sha256(a.config.read_bytes()).hexdigest(),
              model_hashes=_model_hashes(config.scanner.m1_model_manifest),
              started_at_utc=datetime.now(timezone.utc).isoformat(),duration_budget_seconds=30,
              interval_ms=policy.observation_interval_ms,n=5,collection_ms=8000,
              input_stage=scanner.opaque_footer_identity.input_stage.value,
              uploads=0,frames_sent_to_stm=0,production_state_changes=0,
              fidelity='Read-only phase with native preview provider and threaded Android source; no GUI rendering, application, engine gate, receipt or reference acceptance.',rows=[])
exit_code=0
try:
    camera.start()
    base=time.monotonic()
    deadline=base+30
    next_sample=base
    saved=0
    while time.monotonic()<deadline:
        now=time.monotonic()
        if now<next_sample:
            time.sleep(min(.01,next_sample-now))
            continue
        sample=camera.read()
        if sample is None:
            time.sleep(.01)
            continue
        start=time.monotonic()
        next_sample=start+policy.observation_interval_ms/1000
        analyzed=analyzer.analyze(sample)
        row=dict(source_frame_id=sample.frame_id.value,captured_at_monotonic=sample.captured_at_monotonic,
                 observed_at_monotonic=start,t=start-base,source_shape=list(sample.payload.shape),
                 analyzer_ms=(time.monotonic()-start)*1000,
                 candidate_retry_reasons=[x.value for x in analyzed.candidate.retry_reasons])
        if not analyzed.candidate.retry_reasons:
            maximum=max(sample.payload.shape[:2])
            gray,mask=_page_number_preview_inputs(sample.payload,analyzed.mask_preview,maximum)
            observation=provider.observe_preview(gray,mask,analyzed.seam_proxy_fraction,sample.frame_id,'diagnostic-only')
            pair=token_pair_from_page_observation(observation,captured_at_monotonic=sample.captured_at_monotonic,recognition_stage=scanner.opaque_footer_identity.input_stage.value)
            row.update(maximum_dimension_argument=maximum,left_raw=observation.left.raw_text,right_raw=observation.right.raw_text,
                       left_status=observation.left.status.value,right_status=observation.right.status.value,
                       pair=list(pair.value) if pair else None,recognition_processing_ms=observation.processing_ms,
                       left_roi_sha256=observation.left.roi_sha256,right_roi_sha256=observation.right.roi_sha256)
        row['elapsed_ms']=(time.monotonic()-start)*1000
        if saved<3:
            path=a.output/f'source-{saved}.png'
            if not cv2.imwrite(str(path),sample.payload): raise RuntimeError('Diagnostic frame write failed')
            row['saved_source']=path.name
            row['saved_source_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            saved+=1
        result['rows'].append(row)
except Exception as exc:
    result['error_class']=type(exc).__name__  # Do not print URLs/credential-bearing exception text.
    exit_code=1
finally:
    try:
        camera.stop()
    except Exception as exc:
        result['stop_error_class']=type(exc).__name__
        exit_code=1
    result['completed_at_utc']=datetime.now(timezone.utc).isoformat()
    (a.output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(phase=a.phase,sample_count=len(result['rows']),exit_code=exit_code)))
raise SystemExit(exit_code)
