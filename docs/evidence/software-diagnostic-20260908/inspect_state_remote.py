import pathlib,json,sqlite3,hashlib
root=pathlib.Path(r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration')
out={'state':{},'additional_evidence':[]}
for run in sorted(root.iterdir()):
 if not run.name.startswith(('h1-','h2-','h3-','h3r-')):continue
 for p in run.rglob('*'):
  if not p.is_file() or 'secrets' in p.parts:continue
  if p.suffix in {'.json','.jsonl','.log','.txt'} and not any(x in p.relative_to(run).parts for x in ['logs','manifests','config']):
   out['additional_evidence'].append({'path':str(p),'size':p.stat().st_size})
  if p.name=='delivery.sqlite3':
   wal=pathlib.Path(str(p)+'-wal')
   row={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'wal_bytes':wal.stat().st_size if wal.exists() else 0}
   if row['wal_bytes']:row['skipped']='nonempty WAL: immutable snapshot not sufficient'
   else:
    with sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True) as db:
     db.row_factory=sqlite3.Row
     tables=[r[0] for r in db.execute("select name from sqlite_master where type='table'")]
     row['tables']={t:[dict(x) for x in db.execute('select * from "'+t.replace('"','""')+'" limit 3')] for t in tables}
   out['state'][run.name]=row
print(json.dumps(out,ensure_ascii=True,default=str))
