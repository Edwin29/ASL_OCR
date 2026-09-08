"""Bounded read-only camera probe. No image, URL, auth data or state is output."""
import importlib.util,json,pathlib
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('helper',HERE.parent/'software-diagnostic-20260908/collect_identity.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
stage=json.loads((HERE/'latest-stage.json').read_text())['root']
code=f'''import sys,pathlib,time,json,warnings,hashlib
root=pathlib.Path({stage!r})
sys.path[:0]=[str(root/p/'src') for p in ['device-runtime','book-scanner','document-parser']]
from asl_device.app_config import DeviceAppConfig
from book_scanner.video.runtime_composition import create_snapshot_source
config=DeviceAppConfig.from_toml(r'C:\\ASL_OCR_INTEGRATION_RUNTIME\\demo-20260905\\hardware-integration\\h1-20260907-231944\\config\\device-app.h1-camera-console.toml')
source=create_snapshot_source(config.scanner)
rows=[]
try:
    source.start()
    for i in range(3):
        before=time.monotonic()
        try:
            with warnings.catch_warnings(record=True) as warns:
                frame=source.read()
            row={{'attempt':i+1,'elapsed_seconds':round(time.monotonic()-before,3),'frame':frame is not None,'warning_types':list(set(type(w.message).__name__ for w in warns))}}
            if frame is not None:
                row.update({{'shape':list(frame.payload.shape),'frame_id':frame.frame_id.value,'sha256':hashlib.sha256(frame.payload.tobytes()).hexdigest()}})
            rows.append(row)
        except Exception as exc:
            rows.append({{'attempt':i+1,'elapsed_seconds':round(time.monotonic()-before,3),'error_class':type(exc).__name__,'retryable':getattr(exc,'retryable',None),'http_status':getattr(exc,'status_code',None)}})
            break
        time.sleep(0.6)
finally:
    source.stop()
result={{'kind':'read_only_snapshot_probe','staged_source':str(root),'profile':config.scanner.profile,'preview_enabled_in_H1_config':config.scanner.operator_preview_enabled,'source':type(source).__name__,'results':rows,'images_saved':0,'uploads':0,'serial_packets':0}}
(root/'live-snapshot-probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
'''
result=json.loads(helper.remote_python(code))
(HERE/'live-snapshot-probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
