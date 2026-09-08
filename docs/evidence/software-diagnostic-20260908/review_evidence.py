import pathlib,json,hashlib,re
root=pathlib.Path(__file__).resolve().parent
data=json.loads((root/'raw-evidence.json').read_text())
inventory=json.loads((root/'laptop-evidence-inventory.json').read_text())
out={'preserved_copy_comparison':[],'reported_hash_checks':[],'h1_events':{},'h3_v3_packets':[],'h3r_audio_tail':[]}
for folder in ['pipeline-fidelity-audit-20260908','h3r-physical-down-20260908']:
 for p in (root.parent/folder).iterdir():
  if not p.is_file():continue
  matches=[x for x in inventory['files'] if x['path'].endswith('\\'+p.name)]
  digest=hashlib.sha256(p.read_bytes()).hexdigest()
  out['preserved_copy_comparison'].append({'file':folder+'/'+p.name,'sha256':digest,'matches':[x['path'] for x in matches if x['sha256']==digest]})
for report in ['HARDWARE_INTEGRATION_H2_STATUS_20260908.md','HARDWARE_INTEGRATION_H3_READING_OUTPUT_STATUS_20260908.md']:
 text=(root.parents[1]/report).read_text(encoding='utf-8')
 for digest in re.findall(r'\b[0-9a-fA-F]{64}\b',text):
  matches=[x['path'] for x in inventory['files'] if x['sha256'].lower()==digest.lower()]
  out['reported_hash_checks'].append({'report':report,'sha256':digest.lower(),'matches':matches})
for name,text in data['logs'].items():
 if name.startswith('h1-'):
  # Reassemble only visibly wrapped JSON fragments; preserve raw bundle separately.
  joined=''.join(text.splitlines());events=[]
  for match in re.finditer(r'\{"type":"feedback"',joined):
   try:e,_=json.JSONDecoder().raw_decode(joined[match.start():]);events.append(e)
   except json.JSONDecodeError:pass
  out['h1_events'][name]=events
 if name.startswith('h3-') and name.endswith('stm-com5-trace.log'):
  out['h3_v3_packets']=[line for line in text.splitlines() if any(x in line for x in ['NAV,D,A,44','NAV,D,R,45','HOST CONNECTED','NACK,47','NAV,V,R,1'])]
 if name.endswith('h3r-events.jsonl'):
  events=[]
  for line in text.splitlines():
   try:events.append(json.loads(line))
   except json.JSONDecodeError:pass
  out['h3r_audio_tail']=events[-4:]
(root/'evidence-review.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'reported_hashes':len(out['reported_hash_checks']),'reported_hashes_matched':sum(bool(x['matches']) for x in out['reported_hash_checks']),'h1_tail_events':{k:len(v) for k,v in out['h1_events'].items()},'v3_packets':out['h3_v3_packets'],'unmatched_copies':[x['file'] for x in out['preserved_copy_comparison'] if not x['matches']]},indent=2))
