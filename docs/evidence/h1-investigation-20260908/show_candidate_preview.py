"""Interactive diagnostic reusing production preview, camera and analyzer."""
import ctypes
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parent
RUN=ROOT/'candidate-preview-01'
RUN.mkdir(exist_ok=False)
sys.stdout=open(RUN/'stdout.txt','w',encoding='utf-8',buffering=1)
sys.stderr=open(RUN/'stderr.txt','w',encoding='utf-8',buffering=1)
from asl_device.app_config import DeviceAppConfig
from book_scanner.video.runtime_composition import _effective_scanner_config,create_snapshot_source
from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.operator_preview import OpenCVOperatorPreview,ThreadedPreviewCameraSource,OperatorPreviewDiagnostics,_annotate_preview

class NullPreview:
    def start(self): pass
    def show(self,frame): pass
    def stop(self): pass

config=DeviceAppConfig.from_toml(Path(r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447\config\device-app.h1-camera-console.toml'))
analyzer=OpenCVCandidateAnalyzer(_effective_scanner_config(config.scanner).candidate)
screen_w=ctypes.windll.user32.GetSystemMetrics(0)
screen_h=ctypes.windll.user32.GetSystemMetrics(1)
width=max(320,min(1280,int(screen_w*.85),int(screen_h*.78*4/3)))
preview=OpenCVOperatorPreview(window_name='ASL H1 - Full snapshot 4:3 - Green=detected - Q=close',max_width=width)
camera=ThreadedPreviewCameraSource(create_snapshot_source(config.scanner),NullPreview(),source_label='android_ip_camera:snapshot')
result=dict(pid=os.getpid(),screen=[screen_w,screen_h],display_max_width=width,
            started_at_utc=datetime.now(timezone.utc).isoformat(),uploads=0,stm_frames=0,ocr_inference=False,
            rendering='Production annotation on the exact analyzed source frame; proportional downscale only',samples=0)
log=open(RUN/'frames.jsonl','w',encoding='utf-8',buffering=1)
try:
    camera.start()
    preview.start()
    deadline=time.monotonic()+600
    while time.monotonic()<deadline and not (RUN/'stop').exists():
        sample=camera.read()
        if sample is None:
            time.sleep(.02)
            continue
        observation=analyzer.analyze(sample)
        reasons=observation.candidate.retry_reasons
        diagnostics=OperatorPreviewDiagnostics('candidate diagnostic (not capture acceptance)',reasons[0].value if reasons else None,dict(observation.candidate.metrics),observation.mask_preview)
        annotated=_annotate_preview(sample.payload,diagnostics,source_label='Android actual snapshot',effective_mode=None)
        preview.show(annotated)
        result['samples']+=1
        result['source_shape']=list(sample.payload.shape)
        log.write(json.dumps(dict(at_utc=datetime.now(timezone.utc).isoformat(),frame=sample.frame_id.value,reasons=[r.value for r in reasons],metrics=dict(observation.candidate.metrics)))+'\n')
        if result['samples']==1:
            (RUN/'ready.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        if not preview._active:
            result['stop_reason']='window_closed_or_gui_error'
            break
    else:
        result['stop_reason']='stop_marker_or_600_second_budget'
except Exception as exc:
    result['error_class']=type(exc).__name__
finally:
    camera.stop()
    preview.stop()
    log.close()
    result['completed_at_utc']=datetime.now(timezone.utc).isoformat()
    (RUN/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
