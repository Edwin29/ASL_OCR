"""Compare baseline/candidate worker close with actual pyserial loopback traffic."""
import importlib.util,pathlib,json,base64,zipfile
HERE=pathlib.Path(__file__).resolve().parent
OLD=HERE.parent/'h123-implementation-20260908'
spec=importlib.util.spec_from_file_location('helper',HERE.parent/'software-diagnostic-20260908/collect_identity.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
stage=json.loads((OLD/'latest-stage.json').read_text())
(HERE/'staged-tests.json').write_text(json.dumps(stage,indent=2),encoding='utf-8')
with zipfile.ZipFile(HERE/'baseline.zip') as z:
    baseline=base64.b64encode(z.read('device-runtime/src/asl_device/adapters/stm_serial.py')).decode()
code=f'''import sys,pathlib,types,base64,serial,time,threading,json
root=pathlib.Path({stage['root']!r})
sys.path[:0]=[str(root/p/'src') for p in ['device-runtime','book-scanner','document-parser']]
from asl_device.adapters import stm_serial as candidate
from asl_device.app_config import StmSerialConfig
baseline=types.ModuleType('probe_baseline')
exec(base64.b64decode({baseline!r}),baseline.__dict__)
rows=[]
for label,module in [('baseline',baseline),('candidate',candidate)]:
    port=serial.serial_for_url('loop://',timeout=.05)
    bounds=[]
    class Connection:
        def readline(self):return port.readline()
        def read_until(self,expected=b'\\n',size=None):
            bounds.append(size);return port.read_until(expected,size)
        def write(self,data):return len(data)
        def close(self):port.close()
    source=module.StmSerialControlSource(StmSerialConfig(port='VIRTUAL-ONLY',read_timeout_ms=50),serial_factory=lambda _:Connection())
    stop=threading.Event()
    def writer():
        while not stop.is_set():
            port.write(b'x');stop.wait(.003)
    thread=threading.Thread(target=writer)
    source.present(None);thread.start();time.sleep(.12)
    alive_before=source._thread.is_alive()
    started=time.monotonic();source.close();elapsed=time.monotonic()-started
    alive=source._thread.is_alive()
    stop.set();thread.join(2);source._thread.join(2)
    rows.append({{'source':label,'close_seconds':elapsed,'worker_alive_before_close':alive_before,'worker_error_class':None if source._worker_error is None else type(source._worker_error).__name__,'worker_alive_at_close_return':alive,'worker_alive_after_probe_cleanup':source._thread.is_alive(),'read_bounds':sorted(set(bounds))}})
    if port.is_open:port.close()
port=serial.serial_for_url('loop://',timeout=.05)
port.write(b'x'*1024);size=len(port.read_until(size=256));port.close()
print(json.dumps({{'kind':'pyserial_loopback_worker','physical_packets':0,'burst_read_bytes':size,'results':rows}}))
'''
result=json.loads(helper.remote_python(code))
(HERE/'worker-probe-final.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
