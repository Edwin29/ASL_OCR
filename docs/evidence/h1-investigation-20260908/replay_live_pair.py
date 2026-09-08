"""Recorded live rows -> actual engine; counterfactuals are NOT acceptance."""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys

source, helper, ref_path, query_path, output = map(Path,sys.argv[1:])
os.chdir(source)
sys.path.insert(0,str(source/'book-scanner'))
tree=ast.parse(helper.read_text(encoding='utf-8-sig'))
nodes=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.ClassDef,ast.FunctionDef))]
ns={}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(helper),'exec'),ns)
ns['WATCH']={ns['VideoEventType'].OPAQUE_IDENTITY_DECIDED,ns['VideoEventType'].PAGE_CHANGED}
reference=json.loads(ref_path.read_text(encoding='utf-8-sig'))
query=json.loads(query_path.read_text(encoding='utf-8-sig'))
ref_rows=[r for r in reference['rows'] if r.get('pair')][:5]
assert len(ref_rows)==5 and all(r['pair']==['26','27'] for r in ref_rows)
# The preserved fixture constructs a synthetic accepted bank of the same five
# values. Frame hashes/receipt/state are NOT the historical production bank.
rows=[dict(r,t=r['t']) for r in query['rows']]
results=[]
def run(name,data,until):
    with contextlib.redirect_stdout(io.StringIO()):
        r=ns['replay'](name,data,until)
    results.append(r)
run('recorded_live_query_with_rejections',rows,33)
run('counterfactual_no_candidate_resets', [dict(r,candidate_retry_reasons=[]) for r in rows],33)
complete=[r for r in rows if r.get('pair')]
run('counterfactual_complete_pairs_compacted',
    [dict(r,t=.2+i,elapsed_ms=20,candidate_retry_reasons=[]) for i,r in enumerate(complete)],8)
import book_scanner.video.engine as engine
import book_scanner.video.opaque_identity as identity
out=dict(source_hashes={str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (engine.__file__,identity.__file__)},
         reference_input_sha256=hashlib.sha256(ref_path.read_bytes()).hexdigest(),
         query_input_sha256=hashlib.sha256(query_path.read_bytes()).hexdigest(),
         reference_rows=ref_rows,query_complete_count=len(complete),scenarios=results,
         fidelity='Actual engine with recorded raw/timing/rejection rows and fixture reference values from observed first five pairs. No original receipt, frame bank, real camera scheduler, or visual fingerprint restored. Counterfactuals isolate causes only; not proposed threshold changes.')
output.write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
