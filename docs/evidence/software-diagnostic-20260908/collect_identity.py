"""Read-only identity/evidence collection. Never visits Laptop D: or secrets."""
import base64, hashlib, json, pathlib, subprocess, sys

OUT = pathlib.Path(__file__).resolve().parent
REPO = OUT.parents[2]

def remote_python(code):
    ps = "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\ASL_OCR_INTEGRATION\\.venv-e0b\\Scripts\\python.exe' -B -c \"import sys;exec(sys.stdin.read())\""
    command = base64.b64encode(ps.encode('utf-16le')).decode()
    result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','user@100.106.45.8','powershell','-NoProfile','-EncodedCommand',command],input=code.encode('utf-8'),capture_output=True,timeout=55)
    if result.returncode: raise RuntimeError(result.stderr.decode('utf-8','replace'))
    return result.stdout.decode('utf-8-sig')

def source_hashes(root):
    files = []
    for sub in ['device-runtime/src','book-scanner/src','document-parser/src','hardware/stm32/kitel2026final/Core']:
        files.extend(p for p in (root/sub).rglob('*') if p.suffix in {'.py','.c','.h'})
    return {p.relative_to(root).as_posix():{'raw':hashlib.sha256(p.read_bytes()).hexdigest(),'lf':hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()} for p in sorted(files)}

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'identity':
        helper = pathlib.Path(__file__).read_text().split("if __name__")[0]
        # Remote executes only the hash function, no local-path expressions.
        fn = helper[helper.index('def source_hashes'):]
        code = "import pathlib,hashlib,json,sys,asl_device,book_scanner,document_parser\n"+fn+"\nprint(json.dumps({'interpreter':sys.executable,'imports':[m.__file__ for m in (asl_device,book_scanner,document_parser)],'hashes':source_hashes(pathlib.Path(r'C:\\ASL_OCR_INTEGRATION'))}))"
        laptop = json.loads(remote_python(code))
        local = source_hashes(REPO)
        result = {'desktop':local,'laptop':laptop,'mismatches':[k for k,v in local.items() if laptop['hashes'].get(k,{}).get('lf')!=v['lf']]}
        (OUT/(sys.argv[2] if len(sys.argv)>2 else 'source-identity-before.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({'files':len(local),'mismatches':result['mismatches'],'imports':laptop['imports']}))
    elif mode == 'inventory':
        code = """
import pathlib,hashlib,json,shutil,sys
root=pathlib.Path(r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905')
rows=[]
for run in sorted((root/'hardware-integration').iterdir()):
 if run.name.startswith(('h1-','h2-','h3-','h3r-')):
  for sub in ['logs','manifests','config']:
   for p in sorted((run/sub).rglob('*')):
    if p.is_file() and 'secrets' not in p.parts and p.suffix.lower() in {'.json','.jsonl','.log','.txt','.py','.ps1','.cmd','.toml','.xml'}:
     rows.append({'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
manifest=root/'integration-environment-manifest.json'
print(json.dumps({'files':rows,'environment_manifest_hash':hashlib.sha256(manifest.read_bytes()).hexdigest(),'environment_manifest':json.loads(manifest.read_text(encoding='utf-8-sig')),'debuggers':{n:shutil.which(n) for n in ['cdb','windbg','dumpchk','llvm-readobj']}}))
"""
        data=json.loads(remote_python(code))
        (OUT/'laptop-evidence-inventory.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
        print(json.dumps({'files':data['files'],'debuggers':data['debuggers']},indent=2))
    elif mode == 'remote':
        data=remote_python(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8'))
        (OUT/sys.argv[3]).write_text(data,encoding='utf-8')
        print(data[:int(sys.argv[4]) if len(sys.argv)>4 else 12000])
