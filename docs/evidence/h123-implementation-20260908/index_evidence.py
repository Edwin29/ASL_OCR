"""Index explicit diagnostics only; no state, credentials or pytest temp trees."""
import hashlib,json,pathlib,re
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
report=ROOT/'docs/H123_IMPLEMENTATION_RESULT_20260908.md'
files=[p for p in HERE.iterdir() if p.is_file() and p.name!='evidence-index.json' and p.suffix in {'.json','.py','.md','.diff','.zip','.log'}]
for name in ['g3a-evidence','firmware-before-03','firmware-after-final']:
    files.extend(p for p in (HERE/name).iterdir() if p.is_file() and p.suffix in {'.json','.log','.txt','.c'})
missing=[]
for target in re.findall(r'\]\(([^)]+)\)',report.read_text(encoding='utf-8')):
    if '://' not in target and target!='evidence/h123-implementation-20260908/evidence-index.json':
        if not (report.parent/target).exists():missing.append(target)
validation=json.loads((HERE/'final-validation.json').read_text())
index={'report':str(report),'report_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),'product_identity_files':len(validation['hashes']),'missing_report_links':missing,'evidence':{p.relative_to(HERE).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(files)}}
(HERE/'evidence-index.json').write_text(json.dumps(index,indent=2),encoding='utf-8')
print(json.dumps({'files_indexed':len(files),'product_identity_files':index['product_identity_files'],'missing_report_links':missing}))
assert not missing
