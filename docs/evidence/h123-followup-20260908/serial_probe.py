"""Actual installed pyserial, loop:// only; no COM or physical packets."""
import importlib.util,pathlib,json
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('helper',HERE.parent/'software-diagnostic-20260908/collect_identity.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
code='''import serial,inspect,time,threading,json,hashlib
rows=[]
for method in ['readline','read_until']:
    port=serial.serial_for_url('loop://',timeout=.05)
    def writer():
        for _ in range(80):
            port.write(b'x');time.sleep(.005)
    thread=threading.Thread(target=writer);thread.start()
    start=time.monotonic()
    data=port.readline() if method=='readline' else port.read_until(size=256)
    elapsed=time.monotonic()-start
    thread.join();port.close()
    rows.append({'method':method,'bytes':len(data),'elapsed_seconds':elapsed})
source=inspect.getsource(serial.SerialBase.read_until)
print(json.dumps({'version':serial.__version__,'module':serial.__file__,'read_until_source':source,'read_until_sha256':hashlib.sha256(source.encode()).hexdigest(),'timeout_seconds':.05,'producer_bytes':80,'producer_spacing_seconds':.005,'physical_packets':0,'results':rows}))
'''
result=json.loads(helper.remote_python(code))
(HERE/'serial-probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
