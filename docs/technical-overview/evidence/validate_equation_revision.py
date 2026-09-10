"""Verify documentation artifacts without executing production or hardware IO."""
from pathlib import Path
import hashlib, json, re, subprocess

root = Path(__file__).resolve().parents[3]
folder = root / 'docs/technical-overview'
doc = root / 'docs/ASL_OCR_TECHNICAL_OVERVIEW.md'
read = lambda p: p.read_text(encoding='utf-8-sig')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
baseline = json.loads(read(folder/'baseline.json'))
changes = [r['path'] for r in baseline['files'] if sha(root/r['path']) != r['sha256']]
head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip()
render = json.loads(read(folder/'evidence/equation-render/render-results.json'))
examples = json.loads(read(folder/'evidence/equation-examples.json'))
windows = examples['equation_windows']
example_ok = ([x['status'] for x in examples['math']] == ['VALID','PARTIAL','INVALID']
              and [len(x['cells']) for x in windows] == [10,3]
              and [x['offset'] for x in windows] == [0,10]
              and all(x['total_cell_count'] == 13 for x in windows))
render_ok = render['sha256'] == sha(doc) and len(render['results']) == 5 and all(x['passed'] for x in render['results'])
paths = [doc] + [folder/x for x in ['TERMINOLOGY_CROSSWALK.md','README.md','EQUATION_AND_BILINGUAL_REVISION_20260910.md']]
out = folder/'evidence/equation-revision-validation.json'
errors = []
links = 0
for path in paths:
    for link in re.findall(r'\[[^\]\n]+\]\(([^)]+)\)', read(path)):
        if re.match(r'https?://|#',link): continue
        links += 1
        name,_,anchor = link.partition('#')
        dest = (path.parent/name).resolve()
        if dest != out and not dest.is_file(): errors.append([path.name,link,'missing'])
        elif re.fullmatch(r'L\d+',anchor) and int(anchor[1:]) > len(read(dest).splitlines()):
            errors.append([path.name,link,'line out of range'])
old_example_absent = all(x not in read(doc) for x in [r'\frac{1}{2}','분수½','2분의 1'])
record = dict(head=head, baseline_source_files_checked=len(baseline['files']),
              source_hash_changes=changes, product_source_modification_count=len(changes),
              local_links_checked=links, link_errors=errors, equation_example_verified=example_ok,
              old_fraction_example_absent=old_example_absent, mermaid_count=5,
              actual_render_passed_and_current=render_ok, document_sha256=sha(doc),
              physical_or_production_io_executed=False)
record['passed'] = not changes and head == baseline['head'] and not errors and example_ok and render_ok and old_example_absent
out.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False,indent=2))
raise SystemExit(0 if record['passed'] else 1)
