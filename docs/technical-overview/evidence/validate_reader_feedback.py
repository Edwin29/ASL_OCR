"""Validate current reader revision without overwriting historical PASS6 evidence."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
root=Path(__file__).resolve().parents[3]
folder=root/'docs/technical-overview'
output=folder/'evidence/reader-feedback-validation.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
baseline=json.loads((folder/'baseline.json').read_text(encoding='utf-8-sig'))
changed=[item['path'] for item in baseline['files'] if sha(root/item['path'])!=item['sha256']]
paths=[root/'docs/ASL_OCR_TECHNICAL_OVERVIEW.md', folder/'README.md',
       folder/'READER_FEEDBACK_REVISION_20260910.md',folder/'CORE_PRINCIPLES_EXPANSION_PLAN_20260910.md']
errors=[]
count=0
for p in paths:
    for link in re.findall(r'\[[^\]\n]+\]\(([^)]+)\)',p.read_text(encoding='utf-8-sig')):
        if re.match(r'https?://|#',link):continue
        count+=1
        target=(p.parent/link.split('#')[0]).resolve()
        if target != output and not target.is_file(): errors.append({'from':p.name,'target':link})
doc=paths[0]
render=json.loads((folder/'evidence/reader-feedback-after/render-results.json').read_text(encoding='utf-8'))
render_current=render['sha256']==sha(doc)
render_passed=len(render['results'])==4 and all(r['passed'] for r in render['results'])
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
record={'scope':'reader feedback correction only; core-principle expansion remains planned',
        'head':head,'baseline_source_files_checked':len(baseline['files']),
        'source_hash_changes':changed,'product_source_modification_count':len(changed),
        'local_links_checked':count,'link_errors':errors,
        'mermaid_renderer':render['renderer'],'mermaid_render_passed':render_passed,
        'render_matches_current_document':render_current,
        'workflow_png_visually_inspected':True,
        'product_tests_rerun':False,'hardware_executed':False,
        'files':[{'path':str(p.relative_to(root)),'sha256':sha(p)} for p in paths],
        'renderer_library_sha256':sha(folder/'evidence/mermaid-11.12.0.min.js')}
record['passed']=not errors and not changed and render_current and render_passed and head==baseline['head']
output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False,indent=2))
raise SystemExit(0 if record['passed'] else 1)
