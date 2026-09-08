"""Guarded delta-only alignment of approved integration source; no state migration."""
import base64,hashlib,importlib.util,json,pathlib,sys,time,zipfile
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('helper',HERE.parent/'software-diagnostic-20260908/collect_identity.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
delta=json.loads((HERE/'implementation-delta.json').read_text())['files']
changes=[]
with zipfile.ZipFile(HERE/'baseline.zip') as z:
    for row in delta:
        relative=row['path']
        before=z.read(relative) if row['before_sha256'] else None
        after=(ROOT/relative).read_bytes()
        changes.append({'path':relative,'baseline_lf':None if before is None else hashlib.sha256(before.replace(b'\r\n',b'\n')).hexdigest(),'candidate_sha256':hashlib.sha256(after).hexdigest(),'data':base64.b64encode(after).decode()})
mode=sys.argv[1]
if mode not in {'inspect','apply'}:raise SystemExit('inspect or apply required')
code=f'''import pathlib,hashlib,base64,json,sys,subprocess,os
root=pathlib.Path(r'C:\\ASL_OCR_INTEGRATION')
changes={changes!r}
conflicts=[]
for row in changes:
    path=(root/row['path']).resolve()
    assert path.is_relative_to(root)
    actual=hashlib.sha256(path.read_bytes().replace(b'\\r\\n',b'\\n')).hexdigest() if path.exists() else None
    if actual!=row['baseline_lf']:conflicts.append(row['path'])
ps="Get-CimInstance Win32_Process | Where-Object {{ $_.Name -match '^python(w)?\\.exe$' }} | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress"
raw=subprocess.check_output(['powershell','-NoProfile','-Command',ps],text=True,encoding='utf-8-sig')
processes=json.loads(raw) if raw.strip() else []
if isinstance(processes,dict):processes=[processes]
others=[p for p in processes if p['ProcessId'] not in {{os.getpid(),os.getppid()}}]
result={{'mode':{mode!r},'root':str(root),'conflicts':conflicts,'other_python_processes':others,'changed_files':[r['path'] for r in changes]}}
if {mode!r}=='apply':
    if conflicts or others:raise RuntimeError('source alignment blocked by changed files or running Python processes')
    backup=pathlib.Path(r'C:\\ASL_OCR_INTEGRATION_RUNTIME\\demo-20260905\\diagnostics')/{('h123-followup-alignment-'+str(time.time_ns()))!r}
    backup.mkdir(exist_ok=False)
    # Preserve every current byte before the first product write.
    for row in changes:
        p=root/row['path']
        if p.exists():
            saved=backup/'before'/row['path'];saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(p.read_bytes())
    manifest={{'root':str(root),'backup':str(backup),'files':[{{k:v for k,v in r.items() if k!='data'}} for r in changes]}}
    (backup/'alignment-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    for row in changes:
        p=root/row['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(row['data']))
    result['backup']=str(backup)
    result['hashes_verified']=all(hashlib.sha256((root/r['path']).read_bytes()).hexdigest()==r['candidate_sha256'] for r in changes)
import asl_device,book_scanner,document_parser
result['interpreter']=sys.executable
result['imports']=[m.__file__ for m in (asl_device,book_scanner,document_parser)]
print(json.dumps(result))
'''
result=json.loads(helper.remote_python(code))
(HERE/('laptop-alignment-'+mode+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
