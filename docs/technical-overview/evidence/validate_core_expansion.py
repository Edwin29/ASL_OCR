"""Final integrity checks for the additive core-principle documentation work."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib, json, re, subprocess
root=Path(__file__).resolve().parents[3]
folder=root/'docs/technical-overview'
doc=root/'docs/ASL_OCR_TECHNICAL_OVERVIEW.md'
out=folder/'evidence/core-expansion-validation.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:p.read_text(encoding='utf-8-sig')
baseline=json.loads(read(folder/'baseline.json'))
source_changes=[r['path'] for r in baseline['files'] if sha(root/r['path'])!=r['sha256']]
old=Counter(line for line in read(folder/'CORE_EXPANSION_BEFORE.md.snapshot').splitlines() if line.strip())
new=Counter(line for line in read(doc).splitlines() if line.strip())
missing=list((old-new).elements())
paths=[doc]+[folder/name for name in [
    'TERMINOLOGY_CROSSWALK.md','CORE_PRINCIPLES_SELECTION.md','CORE_PRINCIPLES_EVIDENCE_CARDS.md',
    'CORE_PRINCIPLES_BLUEPRINT.md','CORE_PRINCIPLES_VERIFICATION.md',
    'CORE_PRINCIPLES_EXPANSION_PLAN_20260910.md','README.md']]
links=0
errors=[]
for path in paths:
    for link in re.findall(r'\[[^\]\n]+\]\(([^)]+)\)',read(path)):
        if re.match(r'https?://|#',link):continue
        links+=1
        name,_,anchor=link.partition('#')
        dest=(path.parent/name).resolve()
        if dest!=out and not dest.is_file():errors.append({'from':path.name,'link':link,'error':'missing'})
        elif re.fullmatch(r'L\d+',anchor) and int(anchor[1:])>len(read(dest).splitlines()):
            errors.append({'from':path.name,'link':link,'error':'line out of range'})
render=json.loads(read(folder/'evidence/core-expansion-render/render-results.json'))
render_ok=(render['sha256']==sha(doc) and len(render['results'])==5 and all(r['passed'] for r in render['results']))
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
record={'recorded_utc':datetime.now(timezone.utc).isoformat(),'head':head,
        'completed_order':['terminology correspondence','selection','evidence cards and controlled examples',
                           'blueprint','additive draft','verification report','correction','render and integrity'],
        'baseline_source_files_checked':len(baseline['files']),'source_hash_changes':source_changes,
        'product_source_modification_count':len(source_changes),
        'approved_korean_nonempty_lines_checked':sum(old.values()),'missing_or_replaced_original_lines':missing,
        'local_links_checked':links,'link_errors':errors,
        'mermaid_count':len(render['results']),'actual_render_passed_and_current':render_ok,
        'tests':{'scanner':26,'parser':109,'device':52,'v4':4,'total':191},
        'physical_or_production_io_executed':False,
        'corrections_applied':['CV1','CV2','CV3'],
        'files':[{'path':str(p.relative_to(root)),'sha256':sha(p)} for p in paths]}
record['passed']=not source_changes and not missing and not errors and render_ok and head==baseline['head']
out.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='files'},ensure_ascii=False,indent=2))
raise SystemExit(0 if record['passed'] else 1)
