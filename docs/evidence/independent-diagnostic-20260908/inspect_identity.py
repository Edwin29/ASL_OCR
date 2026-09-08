import json,pathlib,hashlib
from collect import remote,OUT,ROOT
code=r'''
import pathlib,hashlib,json,shutil,os
root=pathlib.Path(r'C:\ASL_OCR_INTEGRATION')
paths=[p for folder in ('device-runtime/src','book-scanner/src','document-parser/src','hardware/stm32/kitel2026final/Core','tools/windows') for p in (root/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.c','.h','.ps1','.bat')]
norm={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in paths}
debuggers=[str(p) for base in (r'C:\Program Files (x86)\Windows Kits\10\Debuggers',r'C:\Program Files\WindowsApps',r'C:\Program Files\Windows Kits\10\Debuggers') if pathlib.Path(base).exists() for p in pathlib.Path(base).glob('**/cdb.exe')]
manifest=pathlib.Path(r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\integration-environment-manifest.json')
m=json.loads(manifest.read_text(encoding='utf-8-sig'))
print(json.dumps(dict(normalized=norm,debuggers=debuggers,which={x:shutil.which(x) for x in ('cdb','windbg','dumpchk','llvm-readobj','clang','gcc')},manifest_keys=list(m),symbol_path=os.environ.get('_NT_SYMBOL_PATH'))))
'''
result=json.loads(remote(code))
result['normalized_mismatches']=[p for p,h in result['normalized'].items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=h]
(OUT/'identity-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='normalized'},indent=2))
data=json.loads((OUT/'laptop-evidence.json').read_text(encoding='utf-8'))
for rec in data['records']:
 if rec['content'] is not None:
  dest=OUT/'raw'/pathlib.PureWindowsPath(rec['path']).parent.parent.name/pathlib.PureWindowsPath(rec['path']).parent.name/pathlib.PureWindowsPath(rec['path']).name
  dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_text(rec['content'],encoding='utf-8')
print('Extracted sanitized text evidence; original hashes remain in laptop-evidence.json')
