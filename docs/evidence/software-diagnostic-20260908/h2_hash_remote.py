import pathlib,hashlib,json
p=pathlib.Path(r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h2-20260907-234639\logs\h2-events.jsonl')
raw=p.read_bytes();expected='cee1fbfc22e3742f00f31cc2e5630ae5ca5aede42dce831e1e77f4db38d66929'
matches=[i for i in range(len(raw)+1) if hashlib.sha256(raw[:i]).hexdigest()==expected]
print(json.dumps({'path':str(p),'actual':hashlib.sha256(raw).hexdigest(),'expected_report_hash':expected,'prefix_match_bytes':matches,'appended_text':raw[matches[0]:].decode('utf-8') if matches else None},indent=2))
