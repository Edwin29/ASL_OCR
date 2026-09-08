"""Verify immutable inputs and build a diagnostic output manifest."""
import hashlib,json,pathlib,re
from collect_identity import remote_python,source_hashes
out=pathlib.Path(__file__).resolve().parent
repo=out.parents[2]
before=json.loads((out/'source-identity-before.json').read_text())
after=json.loads((out/'source-identity-after.json').read_text())
inventory=json.loads((out/'laptop-evidence-inventory.json').read_text())
raw_evidence=json.loads((out/'raw-evidence.json').read_text())
states=json.loads((out/'state-evidence.json').read_text())
dumps=json.loads((out/'dump-metadata.json').read_text())
expected={r['path']:r['sha256'] for r in inventory['files']}
expected.update({r['path']:r['sha256'] for r in raw_evidence['other_files']})
expected[r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\integration-environment-manifest.json']=inventory['environment_manifest_hash']
expected.update({r['path']:r['sha256'] for r in states['state'].values()})
expected.update({r['path']:r['sha256'] for r in dumps['dumps']})
code="import pathlib,hashlib,json\npaths="+repr(list(expected))+"\nassert all(p.startswith('C:\\\\') for p in paths)\nprint(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in paths}))"
actual=json.loads(remote_python(code))
report_files=[repo/'docs/H1_H2_H3_SOFTWARE_DIAGNOSTIC_RESULT_20260908.md',*sorted((repo/'docs/work-packets').glob('H123_DIAG_*_WORK_PACKET_20260908.md'))]
bad_links=[]
for p in report_files:
 text=p.read_text(encoding='utf-8')
 for link in re.findall(r'\]\(([^)]+)\)',text):
  if '://' not in link and not (p.parent/link).exists():bad_links.append({'file':str(p),'link':link})
result={'desktop_product_hash_changes':[k for k,v in before['desktop'].items() if after['desktop'].get(k)!=v],
 'laptop_product_hash_changes':[k for k,v in before['laptop']['hashes'].items() if after['laptop']['hashes'].get(k)!=v],
 'existing_laptop_evidence_checked':len(expected),'existing_laptop_evidence_hash_changes':[k for k,v in expected.items() if actual.get(k)!=v],
 'broken_report_links':bad_links,
 'new_files':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*report_files,*sorted(out.iterdir())] if p.is_file() and p.name not in {'final-integrity.json'}}}
(out/'final-integrity.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='new_files'},indent=2))
assert not any(result[k] for k in ['desktop_product_hash_changes','laptop_product_hash_changes','existing_laptop_evidence_hash_changes','broken_report_links'])
