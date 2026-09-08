import json,base64
from collect import remote,OUT
payload=base64.b64encode((OUT/'native_audio_probe.py').read_bytes()).decode()
code=r'''
import pathlib,base64,subprocess,sys,json,datetime
root=pathlib.Path(r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics')/('independent-audio-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
root.mkdir(parents=True,exist_ok=False)
p=root/'native_audio_probe.py';p.write_bytes(base64.b64decode('PAYLOAD'))
try:
 run=subprocess.run([sys.executable,'-B',str(p)],cwd=root,capture_output=True,timeout=35)
 result=dict(root=str(root),returncode=run.returncode,stdout=run.stdout.decode('utf-8',errors='replace'),stderr=run.stderr.decode('utf-8',errors='replace'))
except subprocess.TimeoutExpired as e:
 result=dict(root=str(root),timeout=True,stdout=(e.stdout or b'').decode(errors='replace'),stderr=(e.stderr or b'').decode(errors='replace'),child_cleanup='subprocess.run killed and waited for its own child')
(root/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
'''.replace('PAYLOAD',payload)
result=json.loads(remote(code));(OUT/'native-audio-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
