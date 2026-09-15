"""Read-only capture log, local outbox and authenticated server status audit."""
import json, sqlite3, statistics, time
from dataclasses import asdict
from pathlib import Path
from asl_device.app_config import DeviceAppConfig
from asl_device.adapters.http_s0 import S0HttpClient
root=Path(__file__).resolve().parent
cfg=DeviceAppConfig.from_toml('/home/user/ASL_OCR_PI/config/device-app.stm-capture-round2-20260915.toml')
rows=[]
for line in (root/'stdout.log').read_text(errors='replace').splitlines():
    try: r=json.loads(line)
    except ValueError: continue
    if isinstance(r,dict): rows.append(r)
started=next(r for r in rows if r.get('code')=='scan_started')
pack=started['details']['datapack_id']
candidate=next(r for r in rows if r.get('code')=='candidate_selected')
session=candidate['details']['spread_id'].split('-spread-')[0]
db=Path(cfg.delivery.outbox_db_path)
with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row
    outbox=[dict(r) for r in conn.execute('SELECT sequence,status,artifact_id,spread_id,source_frame_id,receipt_id,attempt_count,last_http_status,manifest_sha256,upload_digest,created_at,server_accepted_at FROM delivery_outbox WHERE scan_session_id=? ORDER BY sequence',(session,))]
api=S0HttpClient(cfg.connectivity.server_base_url,cfg.connectivity.load_api_key(),timeout_seconds=10)
status=api._call('GET',f'/api/v1/scan-sessions/{session}')
catalog=[asdict(r) for r in api.list_datapacks(cfg.connectivity.device_id) if r.datapack_id.value==pack]
sent=[dict(sequence=r['details']['sequence'],at_monotonic=r['at_monotonic'],seconds_after_scan_start=r['at_monotonic']-started['at_monotonic']) for r in rows if r.get('code')=='spread_sent']
decisions=[r for r in rows if r.get('code')=='identity_collection_decided']
progress=[r for r in rows if r.get('code')=='identity_collection_progress']
intervals=[r['details']['effective_interval_ms'] for r in progress if r['details'].get('effective_interval_ms') is not None]
starts={r['details'].get('spread_id'):r['at_monotonic'] for r in rows if r.get('code')=='identity_collection_started' and r['details'].get('spread_id') and r['details'].get('identity_role')=='candidate_verification'}
timings=[dict(spread_id=r['details'].get('spread_id'),decision=r['details']['decision'],valid_observations=r['details']['valid_observations'],timed_out=r['details']['timed_out'],seconds=r['at_monotonic']-starts[r['details']['spread_id']]) for r in decisions if r['details'].get('spread_id') in starts]
result=dict(scan_session_id=session,datapack_id=pack,scope='read-only log/outbox/server status snapshot; no physical content inference',
    outbox=outbox,server_status=status,catalog=catalog,spread_sent=sent,
    candidate_selected=sum(r.get('code')=='candidate_selected' for r in rows),
    identity_aborts=[r for r in rows if r.get('code')=='identity_collection_aborted'],
    decisions=decisions,candidate_collection_timings=timings,
    interval_median_ms=statistics.median(intervals) if intervals else None,
    finalization_events=[r for r in rows if r.get('code') in ('scan_stopping','finalizing','datapack_saved','fatal_error')])
path=root/f'capture-audit-{time.time_ns()}.json'
path.write_text(json.dumps(result,indent=2,default=str))
print(json.dumps(result,indent=2,default=str))
print(str(path))
