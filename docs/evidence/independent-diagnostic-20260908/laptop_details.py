import json,pathlib
from collect import remote,OUT
code=r'''
import json,pathlib,struct,hashlib,tomllib,dataclasses,subprocess
from asl_device.app_config import DeviceAppConfig
runtime=pathlib.Path(r'C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905')
configs=[]
for run in (runtime/'hardware-integration').iterdir():
 if not run.name.startswith(('h1-','h2-','h3-','h3r-')):continue
 for p in (run/'config').glob('device-app*.toml'):
  raw=p.read_bytes();data=tomllib.loads(raw.decode('utf-8-sig'))
  assert 'D:/' not in raw.decode() and 'D:\\' not in raw.decode()
  cfg=DeviceAppConfig.from_toml(p)
  scanner={k:v for k,v in dataclasses.asdict(cfg.scanner).items() if k in ('profile','camera_snapshot_url','camera_snapshot_timeout_seconds','camera_snapshot_allow_insecure_tls','camera_snapshot_min_width','camera_snapshot_min_height','sample_interval_ms','opaque_identity_max_collection_ms','camera_index','camera_backend')}
  configs.append(dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest(),parsed=True,controls=cfg.controls_mode,feedback=cfg.feedback_mode,scanner=scanner,audio=dataclasses.asdict(cfg.reading_audio),stm=dataclasses.asdict(cfg.stm_serial) if cfg.stm_serial else None,viewport=cfg.viewport_size,poll_interval=cfg.poll_interval_ms))
dumps=[]
for name in ('python.exe.27012.dmp','python.exe.31856.dmp'):
 p=pathlib.Path(r'C:\Users\user\AppData\Local\CrashDumps')/name
 b=p.read_bytes();assert b[:4]==b'MDMP'
 u32=lambda o:struct.unpack_from('<I',b,o)[0]
 u64=lambda o:struct.unpack_from('<Q',b,o)[0]
 streams={u32(u32(12)+i*12):(u32(u32(12)+i*12+4),u32(u32(12)+i*12+8)) for i in range(u32(8))}
 mods=[];modr=streams[4][1]
 for i in range(u32(modr)):
  o=modr+4+108*i;nr=u32(o+20);n=b[nr+4:nr+4+u32(nr)].decode('utf-16le')
  mods.append(dict(name=pathlib.PureWindowsPath(n).name,base=u64(o),size=u32(o+8)))
 er=streams[6][1];addr=u64(er+24);fault=next((dict(name=m['name'],offset=hex(addr-m['base'])) for m in mods if m['base']<=addr<m['base']+m['size']),None)
 ctx_size,ctx_rva=struct.unpack_from('<II',b,er+160)
 rip=u64(ctx_rva+248);rsp=u64(ctx_rva+152)
 dumps.append(dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),exception_code=hex(u32(er+8)),thread_id=u32(er),fault=fault,exception_address=hex(addr),context_rip=hex(rip),context_rsp=hex(rsp),exception_parameters=[hex(u64(er+40+8*i)) for i in range(min(u32(er+32),15))],thread_count=u32(streams[3][1]),audio_crypto_modules=[m for m in mods if any(x in m['name'].lower() for x in ('portaudio','sound','audio','crypto','ucrt','ssl','python'))],stack_status='not_unwound; exception context only; no cdb/WinDbg or symbols found'))
extra={}
h0=runtime/'hardware-integration/h0-20260907-205411'
for relative in ('manifests/stm32-build.json','reports/stm32-flash-verify.json','manifests/h0-current-invariants.py'):
 p=h0/relative
 if p.exists():extra[relative]=p.read_text(encoding='utf-8-sig')
manifest=json.loads((runtime/'integration-environment-manifest.json').read_text(encoding='utf-8-sig'))
print(json.dumps(dict(configs=configs,dumps=dumps,h0_build=extra,manifest_source=manifest.get('source')),default=str))
'''
data=json.loads(remote(code));(OUT/'laptop-details.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(data,ensure_ascii=False,indent=2))
