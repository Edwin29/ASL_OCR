"""Isolated H1 diagnostic; existing product files are never written.

Reuses only definitions from the preserved replay, not its top-level scenarios
or pre-fix assertions. A transparent collector subclass records delegations.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--replay', type=Path, required=True)
parser.add_argument('--native', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
os.chdir(args.source)
sys.path.insert(0, str(args.source / 'book-scanner'))
tree = ast.parse(args.replay.read_text(encoding='utf-8-sig'))
nodes = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef))]
ns = {'WATCH': set()}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(args.replay), 'exec'), ns)
ns['WATCH'] = {ns['VideoEventType'].OPAQUE_IDENTITY_DECIDED, ns['VideoEventType'].PAGE_CHANGED}
import book_scanner.video.engine as engine_module
import book_scanner.video.opaque_identity as identity_module

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

paths = [engine_module.__file__, identity_module.__file__,
         args.source / 'book-scanner/tests/unit/video/test_engine_v3a5.py',
         args.source / 'book-scanner/tests/unit/video/test_candidate.py']
before = {str(p): sha(p) for p in paths}
original_collector = engine_module.OpaqueQueryCollector
trace = []

class RecordingCollector(original_collector):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.diag_id = sum(row['op'] == 'new' for row in trace)
        trace.append(dict(op='new', epoch=self.diag_id, started_at=self.started_at,
                          references=[[list(o.value) for o in b.observations] for b in self.references]))

    def observe(self, pair):
        result = super().observe(pair)
        trace.append(dict(op='observe', epoch=self.diag_id, pair=list(pair.value),
                          frame=str(pair.source_frame_id), decision=result.kind.value,
                          n=result.valid_observations, consensus=result.novel_consensus_count,
                          matches=result.match_count))
        return result

    def decision(self, *, now=None):
        result = super().decision(now=now)
        if result.timed_out:
            trace.append(dict(op='timeout', epoch=self.diag_id, now=now,
                              started_at=self.started_at, n=result.valid_observations,
                              consensus=result.novel_consensus_count))
        return result

engine_module.OpaqueQueryCollector = RecordingCollector
results = []

def run(name, rows, until):
    trace.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        result = ns['replay'](name, rows, until)
    result['collector_trace'] = list(trace)
    results.append(result)
    return result

try:
    native = json.loads(args.native.read_text(encoding='utf-8-sig'))['rows']
    t0 = native[0]['observed_at_monotonic']
    run('recorded_native_clean_reference', [dict(r, t=r['observed_at_monotonic']-t0) for r in native], 33)
    for interval in (1.5, 1.8, 1.95, 2.0, 2.05, 2.2):
        run(f'exact_interval_{interval}', [dict(t=.2+i*interval, pair=['28','29'], elapsed_ms=20) for i in range(20)], 38)
    run('exact_slow_inference', [dict(t=.2+i*2.05, pair=['28','29'], elapsed_ms=800) for i in range(20)], 38)
    run('same_clean_reference', [dict(t=.2+i*1.7, pair=['26','27'], elapsed_ms=20) for i in range(8)], 14)
    run('five_conflicting_pairs', [dict(t=.2+i*.2, pair=[str(10+i),str(80+i)], elapsed_ms=20) for i in range(5)], 8.5)
    run('fifth_starts_before_deadline', [dict(t=t,pair=['28','29'],elapsed_ms=500 if i==4 else 20) for i,t in enumerate((.2,2.1,4.05,6,7.98))], 10)

    # Direct collector: query/reference contamination sensitivity, not incident attribution.
    pair_type = identity_module.OpaqueFooterTokenPair
    def pair(value, idx):
        return pair_type(*value, ns['FrameId'](f'diag-{idx}'), float(idx), 'diagnostic', 'fake', '0'*64, '1'*64)
    from book_scanner.video.types import ArtifactId
    bank = identity_module.OpaqueReferenceBank(ArtifactId('diag-reference'), 'diag-receipt', 'diag-pack',
        tuple(pair(v,i) for i,v in enumerate([('26','27')]*4+[('28','29')])), 'diagnostic')
    collector = original_collector(ns['_policy'](max_collection_ms=8000), (bank,), started_at=10.)
    contaminated = collector.observe(pair(('28','29'), 100))
    sensitivity = dict(reference_pairs=[list(o.value) for o in bank.observations],
                       query=['28','29'], decision=contaminated.kind.value,
                       n=contaminated.valid_observations, matches=contaminated.match_count,
                       limit='Synthetic reference bank; original accepted bank was not preserved.')
finally:
    engine_module.OpaqueQueryCollector = original_collector

after = {str(p): sha(p) for p in paths}
assert before == after, 'Existing source changed during diagnostic'
checks = {
    'slow_exact_stays_waiting': next(r for r in results if r['scenario']=='exact_interval_2.05')['state']=='waiting_for_page_change',
    'fast_exact_changes': next(r for r in results if r['scenario']=='exact_interval_1.5')['state']=='searching',
    'five_conflicting_unknown': next(r for r in results if r['scenario']=='five_conflicting_pairs')['decisions'][0]['decision']=='unknown',
    'contaminated_bank_same_n1': sensitivity['decision']=='same' and sensitivity['n']==1,
    'source_unchanged': before==after,
}
out = dict(python=sys.executable, source_hashes=before, replay_sha256=sha(args.replay),
           native_sha256=sha(args.native), policy=dict(n=5,k_same=1,k_different=0,max_collection_ms=8000),
           fidelity='Actual imported engine/collector with fixture source/provider/clock; collector subclass only delegates and records. No live camera, upload, audio, serial, production state.',
           checks=checks, scenarios=results, reference_sensitivity=sensitivity)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(dict(checks=checks, scenarios=[{k:v for k,v in r.items() if k!='collector_trace'} for r in results]), indent=2))
if not all(checks.values()):
    raise SystemExit(1)
