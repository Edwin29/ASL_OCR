"""Preserve the approved working-tree baseline, including existing uncommitted work."""
import hashlib,json,pathlib,subprocess,zipfile
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
archive=HERE/'baseline-source-tests.zip'
if archive.exists():raise SystemExit('Baseline already preserved; refusing overwrite')
files=[]
for package in ['device-runtime','book-scanner','document-parser']:
    for sub in ['src','tests']:
        files.extend(p for p in (ROOT/package/sub).rglob('*.py'))
files.extend(p for p in (ROOT/'hardware/stm32/kitel2026final/Core').rglob('*') if p.suffix in {'.c','.h'})
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,p.relative_to(ROOT).as_posix())
(HERE/'baseline.json').write_text(json.dumps({
    'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'files':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
},indent=2),encoding='utf-8')
print(f'Preserved {len(files)} source/test files; no state/config/credentials included')
