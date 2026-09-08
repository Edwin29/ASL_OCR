import pathlib,json,hashlib,tomllib,subprocess,importlib.metadata
from asl_device.app_config import DeviceAppConfig
root=pathlib.Path(r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905')
result={'logs':{},'configs':{},'launchers':{},'run_manifests':{},'reports':{},'other_files':[]}
for run in sorted((root/'hardware-integration').iterdir()):
 if not run.name.startswith(('h1-','h2-','h3-','h3r-')): continue
 for sub in ['logs','manifests','reports']:
  for p in sorted((run/sub).glob('*')):
   if not p.is_file(): continue
   key=run.name+'/'+sub+'/'+p.name
   raw=p.read_bytes()
   result['other_files'].append({'path':str(p),'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
   if sub=='logs' and p.suffix in {'.log','.json','.jsonl','.txt'}:
    encoding='utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
    result['logs'][key]=raw.decode(encoding,errors='replace')
   elif sub=='manifests' and p.suffix=='.ps1' and any(x in p.name for x in ['runtime','start-h','start-interactive']):
    result['launchers'][key]=raw.decode('utf-8-sig',errors='replace')
   elif sub=='manifests' and p.suffix=='.json':
    result['run_manifests'][key]=raw.decode('utf-8-sig',errors='replace')
   elif sub=='reports' and p.suffix in {'.json','.txt'}:
    result['reports'][key]=raw.decode('utf-8-sig',errors='replace')
 for p in (run/'config').glob('device-app*.toml'):
  cfg=DeviceAppConfig.from_toml(p)
  raw=tomllib.loads(p.read_text(encoding='utf-8-sig'))
  result['configs'][run.name+'/'+p.name]={'parsed':True,'config':raw,'config_class':type(cfg).__name__}
print(json.dumps(result,ensure_ascii=True))
