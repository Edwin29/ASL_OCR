import pathlib,json,hashlib,sys,importlib.metadata
root=pathlib.Path(r'C:\ASL_OCR_INTEGRATION')
manifest=json.loads(pathlib.Path(r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\integration-environment-manifest.json').read_text(encoding='utf-8-sig'))
rows=[]
for relative,entry in manifest['source']['transplant_hashes'].items():
 p=root/relative
 actual=hashlib.sha256(p.read_bytes()).hexdigest()
 rows.append({'path':relative,'expected':entry['expected'],'actual':actual,'match':actual==entry['expected']})
elf=root/'hardware/stm32/kitel2026final/Debug/kitel2026final.elf'
print(json.dumps({'baseline':rows,'interpreter_hash':hashlib.sha256(pathlib.Path(sys.executable).read_bytes()).hexdigest(),'versions':{n:importlib.metadata.version(n) for n in ['sounddevice','cffi','pyserial','requests','numpy','opencv-python']},'elf':{'exists':elf.is_file(),'sha256':hashlib.sha256(elf.read_bytes()).hexdigest() if elf.is_file() else None}},indent=2))
