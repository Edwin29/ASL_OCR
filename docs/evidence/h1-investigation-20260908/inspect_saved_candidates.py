"""Read-only trace of candidate rejection on saved source frames."""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import cv2
from asl_device.app_config import DeviceAppConfig
from book_scanner.video.runtime_composition import _effective_scanner_config
from book_scanner.video.candidate import OpenCVCandidateAnalyzer, _preview_image
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameId
from book_scanner.detect.contrast_spatial import ContrastSpatialPageSegmenter

config_path,root,output=map(Path,sys.argv[1:])
config=DeviceAppConfig.from_toml(config_path)
analyzer=OpenCVCandidateAnalyzer(_effective_scanner_config(config.scanner).candidate)
method=ContrastSpatialPageSegmenter.segment
lines,start=inspect.getsourcelines(method)
checklines={start+i for i,line in enumerate(lines) if 'if inside_mean <' in line}
trace_rows=[]
def trace(frame,event,arg):
    if frame.f_code is method.__code__ and event=='line' and frame.f_lineno in checklines:
        loc=frame.f_locals
        trace_rows.append({k:loc[k] for k in ('area_ratio','height_ratio','inside_mean','ring_mean','contrast_score')})
    return trace
results=[]
for phase in ('live-reference-02','live-query-01'):
    path=root/phase/'source-0.png'
    image=cv2.imread(str(path))
    if image is None: raise ValueError(path.name)
    observed=analyzer.analyze(FrameSample(FrameId(phase),1.,image))
    trace_rows.clear()
    sys.settrace(trace)
    try:
        pages=analyzer.mask_pipeline.process(_preview_image(image,analyzer.policy.preview_max_dimension))
    finally:
        sys.settrace(None)
    results.append(dict(phase=phase,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        retry_reasons=[r.value for r in observed.candidate.retry_reasons],metrics=dict(observed.candidate.metrics),
        sides={side.value:dict(mask_present=p.page_mask is not None,reject_reason=p.reject_reason,
                              segmentation_diagnostics=p.segmentation.diagnostics) for side,p in pages.items()},
        brightness_checks=list(trace_rows)))
output.write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
