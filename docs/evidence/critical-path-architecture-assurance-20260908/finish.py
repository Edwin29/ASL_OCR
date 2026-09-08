"""Verify new assurance artifacts and unchanged product identities. No product writes."""
import hashlib,json,pathlib,re

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
before=json.loads((HERE/'source-identity-before.json').read_text())
after=json.loads((HERE/'source-identity-after.json').read_text())
docs=[ROOT/'docs/H123_CRITICAL_PATH_ARCHITECTURE_ASSURANCE_20260908.md',
      ROOT/'docs/work-packets/H123_ARCH_LOCAL_CORRECTIONS_20260908.md',
      ROOT/'docs/work-packets/H123_ARCH_DIAGNOSTIC_DESIGN_20260908.md',HERE/'README.md']
bad=[]
targets=set()
for doc in docs:
    for target in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
        target=target.split('#')[0]
        if not target or '://' in target:continue
        p=(doc.parent/target).resolve()
        if p==HERE/'integrity.json':continue
        if not p.is_file():bad.append({'doc':doc.name,'target':target})
        else:targets.add(p)
targets.update(docs)
targets.update(p for p in HERE.iterdir() if p.is_file() and p.name!='integrity.json')
out={
    'desktop_product_changes':[p for p in before['desktop'] if before['desktop'][p]!=after['desktop'].get(p)],
    'laptop_product_changes':[p for p in before['laptop']['hashes'] if before['laptop']['hashes'][p]!=after['laptop']['hashes'].get(p)],
    'desktop_changes_since_prior_diagnosis':after['desktop_changed_since_diagnosis'],
    'laptop_changes_since_prior_diagnosis':after['laptop_changed_since_diagnosis'],
    'source_files_per_host':len(after['desktop']),
    'broken_file_links':bad,
    'hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(targets)},
    'physical_io_performed':False,'product_source_modification_count':0,
    'claim_limit':'Identity comparison covers product sources. Historical logs/dumps/state are cited from preserved diagnosis, not recollected in this assurance pass.'}
assert not any(out[k] for k in ['desktop_product_changes','laptop_product_changes','broken_file_links'])
(HERE/'integrity.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k!='hashes'},indent=2))
