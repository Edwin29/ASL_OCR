"""Read-only evidence collector. Never touches Laptop D: or credentials."""
import base64, hashlib, json, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
def remote(code):
    encoded = base64.b64encode(code.encode()).decode()
    ps = "$ProgressPreference='SilentlyContinue'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); Set-Location -LiteralPath C:\\ASL_OCR_INTEGRATION; $env:PYTHONDONTWRITEBYTECODE='1'; & C:\\ASL_OCR_INTEGRATION\\.venv-e0b\\Scripts\\python.exe -B -c \"import base64; exec(base64.b64decode('" + encoded + "'))\""
    command = ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','user@100.106.45.8','powershell','-NoProfile','-NonInteractive','-Command','-']
    p = subprocess.run(command,input=(ps+'\n').encode(),capture_output=True,timeout=90)
    if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace'))
    return p.stdout.decode('utf-8-sig')
def source_hashes(root):
    paths = [p for base in ('device-runtime/src','book-scanner/src','document-parser/src','hardware/stm32/kitel2026final/Core','tools/windows') for p in (root/base).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    return {str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
if __name__ == '__main__':
    baseline = {'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'status':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'source_hashes':source_hashes(ROOT)}
    (OUT/'desktop-before.json').write_text(json.dumps(baseline,indent=2),encoding='utf-8')
    code = '''
import pathlib,hashlib,json,sys,subprocess,asl_device,book_scanner,document_parser
root=pathlib.Path(r'C:\\ASL_OCR_INTEGRATION')
runtime=pathlib.Path(r'C:\\ASL_OCR_INTEGRATION_RUNTIME\\demo-20260905')
files={}
for folder in ('device-runtime/src','book-scanner/src','document-parser/src','hardware/stm32/kitel2026final/Core','tools/windows'):
 for p in (root/folder).rglob('*'):
  if p.is_file() and '__pycache__' not in str(p): files[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
records=[]
for run in (runtime/'hardware-integration').iterdir():
 if not run.name.startswith(('h1-','h2-','h3-','h3r-')): continue
 for folder in ('logs','reports','manifests','config'):
  for p in (run/folder).glob('*'):
   if not p.is_file() or p.suffix not in ('.txt','.log','.json','.jsonl','.ps1','.py','.toml'): continue
   b=p.read_bytes()
   # Reports/logs and launchers only; config and other scripts get identity only.
   content=None
   if folder in ('logs','reports') or (folder=='manifests' and ('identity' in p.name or 'manifest' in p.name or 'runtime.ps1' in p.name or p.name.startswith('start-'))):
    content=b.decode('utf-8-sig',errors='replace')
    if '\\x00' in content: content=b.decode('utf-16',errors='replace')
    import re
    content=re.sub(r'(?im)^.*(?:password\\s*[:=]|X-API-Key\\s*[:=]|Authorization\\s*[:=]).*$', '[REDACTED]',content)
   records.append(dict(path=str(p),size=len(b),sha256=hashlib.sha256(b).hexdigest(),content=content))
manifest=runtime/'integration-environment-manifest.json'
dumps=[]
for name in ('python.exe.27012.dmp','python.exe.31856.dmp'):
 p=pathlib.Path(r'C:\\Users\\user\\AppData\\Local\\CrashDumps')/name
 dumps.append(dict(path=str(p),size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
print(json.dumps(dict(executable=sys.executable,imports=[m.__file__ for m in (asl_device,book_scanner,document_parser)],head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),status=subprocess.check_output(['git','status','--porcelain'],text=True),source_hashes=files,manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),records=records,dumps=dumps)))
'''
    data=json.loads(remote(code))
    (OUT/'laptop-evidence.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    mismatches=[k for k,v in baseline['source_hashes'].items() if data['source_hashes'].get(k)!=v]
    print(json.dumps(dict(records=len(data['records']),source_files=len(data['source_hashes']),mismatches=mismatches,dumps=data['dumps']),indent=2))
