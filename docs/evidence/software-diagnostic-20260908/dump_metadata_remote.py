"""Minidump metadata only, originals mapped read-only; no stack attribution."""
import pathlib,struct,mmap,hashlib,json,shutil,subprocess
out={'tool':'Python 3.11 stdlib struct/mmap; metadata parser v1','symbols':'not loaded; no debugger stack available','dumps':[]}
for name in ['python.exe.27012.dmp','python.exe.31856.dmp']:
 p=pathlib.Path(r'C:\Users\user\AppData\Local\CrashDumps')/name
 row={'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 with p.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as m:
  signature,version,count,directory=struct.unpack_from('<4sIII',m,0)
  assert signature==b'MDMP'
  streams={}
  for i in range(count):
   kind,size,rva=struct.unpack_from('<III',m,directory+i*12);streams[kind]=(size,rva)
  modules=[]
  if 4 in streams:
   _,r=streams[4];n=struct.unpack_from('<I',m,r)[0]
   for i in range(n):
    pos=r+4+108*i;base,size,checksum,stamp,name_rva=struct.unpack_from('<QIIII',m,pos)
    length=struct.unpack_from('<I',m,name_rva)[0];module=m[name_rva+4:name_rva+4+length].decode('utf-16le')
    modules.append({'name':module,'base':base,'size':size})
  if 6 in streams:
   _,r=streams[6]
   tid=struct.unpack_from('<I',m,r)[0];code=struct.unpack_from('<I',m,r+8)[0];address=struct.unpack_from('<Q',m,r+24)[0]
   params=struct.unpack_from('<I',m,r+32)[0];info=struct.unpack_from('<15Q',m,r+40)[:params]
   owner=next((x for x in modules if x['base']<=address<x['base']+x['size']),None)
   row['exception']={'thread_id':tid,'code':hex(code),'address':hex(address),'parameters':[hex(v) for v in info],'module':owner,'module_offset':hex(address-owner['base']) if owner else None}
  row['relevant_modules']=[x for x in modules if any(k in x['name'].lower() for k in ['sounddevice','portaudio','ucrtbase','libcrypto','audioses','python3','libssl','_ssl','_cffi'])]
  row['stack_status']='not_unwound; no native call attribution'
  row['stream_types']=sorted(streams)
 out['dumps'].append(row)
out['debugger_candidates']={str(p):p.is_file() for p in [pathlib.Path(r'C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe'),pathlib.Path(r'C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\windbg.exe')]}
print(json.dumps(out,indent=2))
