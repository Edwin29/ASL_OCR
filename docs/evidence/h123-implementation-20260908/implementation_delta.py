"""Compare to the preserved working tree, never to a bare commit."""
import difflib,hashlib,json,pathlib,zipfile
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
baseline=json.loads((HERE/'baseline.json').read_text())
rows=[]
diff=[]
with zipfile.ZipFile(HERE/'baseline-source-tests.zip') as z:
    for relative,before_sha in baseline['files'].items():
        after=(ROOT/relative).read_bytes()
        if hashlib.sha256(after).hexdigest()==before_sha:continue
        before=z.read(relative)
        rows.append({'path':relative,'kind':'product' if '/src/' in relative or relative.startswith('hardware/') else 'test','before_sha256':before_sha,'after_sha256':hashlib.sha256(after).hexdigest()})
        diff.extend(difflib.unified_diff(before.decode('utf-8-sig').replace('\r\n','\n').splitlines(True),after.decode('utf-8-sig').replace('\r\n','\n').splitlines(True),fromfile='baseline/'+relative,tofile='candidate/'+relative))
for package in ['device-runtime','book-scanner','document-parser']:
    for p in (ROOT/package/'tests').rglob('*.py'):
        relative=p.relative_to(ROOT).as_posix()
        if relative not in baseline['files']:
            rows.append({'path':relative,'kind':'test','before_sha256':None,'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(HERE/'implementation-delta.json').write_text(json.dumps({'baseline_head':baseline['head'],'product_count':sum(r['kind']=='product' for r in rows),'files':rows},indent=2),encoding='utf-8')
(HERE/'implementation.diff').write_text(''.join(diff),encoding='utf-8')
print(json.dumps({'product_count':sum(r['kind']=='product' for r in rows),'files':[r['path'] for r in rows]},indent=2))
