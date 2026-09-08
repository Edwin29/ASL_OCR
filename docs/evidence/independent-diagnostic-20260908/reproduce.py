"""Deterministic diagnostic probes; no network, audio device, serial or DB writes."""
import sys,pathlib,types,json,io,wave,hashlib,threading,importlib
from unittest.mock import patch
from dataclasses import replace
ROOT=pathlib.Path(__file__).resolve().parents[3]
OUT=pathlib.Path(__file__).resolve().parent
sys.dont_write_bytecode=True
for p in ('device-runtime/src','book-scanner/src','document-parser/src'):sys.path.insert(0,str(ROOT/p))
pkg=types.ModuleType('auditvideo');pkg.__path__=[str(ROOT/'book-scanner/tests/unit/video')];sys.modules['auditvideo']=pkg
f=importlib.import_module('auditvideo.test_engine_v3a5')
from book_scanner.video.sources import HttpSnapshotCameraSource,SnapshotTransportError,FrameDecodeError
from book_scanner.video.events import VideoEventType
from book_scanner.video.types import VideoSessionState
from asl_device.adapters.reading_audio import SoundDeviceWavPlayer,_validate_wav
from asl_device.application import DeviceApplication
results={}

def camera_probe():
 import numpy as np,cv2,requests
 jpeg=cv2.imencode('.jpg',np.zeros((8,8,3),dtype=np.uint8))[1].tobytes()
 class Response:
  headers={}
  def __init__(self,body,status=200):self.body=body;self.status=status;self.closed=False
  def raise_for_status(self):
   if self.status!=200:raise requests.HTTPError(str(self.status))
  def iter_content(self,chunk_size):yield self.body
  def close(self):self.closed=True
 rows=[]
 for kind in ('timeout','401','403','404','500','503','bad_jpeg_then_good','three_bad_jpeg'):
  calls=[]
  def fetch(*a,**kw):
   calls.append(kw)
   if kind=='timeout' and len(calls)==1:raise requests.ConnectTimeout('synthetic')
   if kind.isdigit() and len(calls)==1:return Response(jpeg,int(kind))
   if kind=='three_bad_jpeg' or (kind=='bad_jpeg_then_good' and len(calls)==1):return Response(b'broken')
   return Response(jpeg)
  source=HttpSnapshotCameraSource('https://example.invalid/snapshot',fetcher=fetch,min_width=1,min_height=1)
  source.start()
  try:source.read();outcome='frame'
  except Exception as e:outcome=type(e).__name__
  rows.append(dict(trigger=kind,calls=len(calls),outcome=outcome))
  source.stop()
 assert rows[0]['calls']==1 and rows[0]['outcome']=='SnapshotTransportError'
 assert rows[-2]['calls']==2 and rows[-2]['outcome']=='frame'
 results['http_taxonomy']=rows
 # Exercise real engine's read/error boundary with an independently supplied fault.
 engine,clock,cam,*_=f._engine()
 engine.start()
 def fail():raise SnapshotTransportError('synthetic')
 cam.read=fail
 events=engine.poll()
 results['engine_transport_fatal']=[dict(type=e.event_type.value,reason=getattr(e.reason,'value',None)) for e in events]
 assert engine.state is VideoSessionState.ERROR
 engine.close()

def liveness_probe(budget,cadence):
 provider=f._FakePageNumberProvider([],preview_labels=[('26','27')]*5+[('28','29')]*100)
 engine,clock,cam,*_=f._engine(frame_count=120,page_number_provider=provider,opaque_identity_policy=f._policy(max_collection_ms=budget))
 first=f._start_and_reach_ready(engine,clock)
 engine.delivery_confirmed(f._artifact_id(first),'independent-receipt')
 original_read=cam.read
 def delayed_read():
  clock.advance(cadence)
  sample=original_read()
  return replace(sample,captured_at_monotonic=clock.monotonic()) if sample else None
 cam.read=delayed_read
 events=[]
 for _ in range(14):
  events.extend(engine.poll())
  if engine.state is VideoSessionState.SEARCHING:break
  clock.advance(.025)
 decisions=[dict(e.details) for e in events if e.event_type is VideoEventType.OPAQUE_IDENTITY_DECIDED]
 row=dict(budget_ms=budget,cadence_seconds=cadence,state=engine.state.value,decisions=decisions,guidance_events=sum(e.event_type is VideoEventType.GUIDANCE_REQUESTED for e in events))
 engine.close();return row

def audio_probe():
 wav=io.BytesIO()
 with wave.open(wav,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*8192)
 raw=wav.getvalue();resource=_validate_wav(raw,hashlib.sha256(raw).hexdigest())
 writing=threading.Event();release_write=threading.Event();abort_entered=threading.Event();release_abort=threading.Event();cancel=threading.Event()
 history=[]
 class Stream:
  closed=False
  def start(self):history.append('start')
  def write(self,b):history.append('write-enter');writing.set();assert release_write.wait(3);history.append('write-exit')
  def abort(self):
   history.append('abort-enter-during-write');abort_entered.set();assert release_abort.wait(3);history.append('abort-after-close' if self.closed else 'abort-before-close')
  def stop(self):history.append('stop')
  def close(self):self.closed=True;history.append('close')
 stream=Stream();player=SoundDeviceWavPlayer(sounddevice_module=types.SimpleNamespace(RawOutputStream=lambda **kw:stream))
 def work():
  try:player.play(resource,cancel.is_set)
  except Exception as e:history.append(type(e).__name__)
 worker=threading.Thread(target=work);worker.start();assert writing.wait(3)
 stopper=threading.Thread(target=player.stop);stopper.start();assert abort_entered.wait(3)
 cancel.set();release_write.set();worker.join(3);assert not worker.is_alive()
 release_abort.set();stopper.join(3);assert not stopper.is_alive();player.close()
 assert 'abort-after-close' in history
 results['audio_native_operation_overlap']=history

def adjacent_cleanup_probe():
 calls=[]
 class Resource:
  def __init__(self,name,fail=False):self.name=name;self.fail=fail
  def close(self):
   calls.append(self.name)
   if self.fail:raise OSError('synthetic close error')
 app=DeviceApplication(types.SimpleNamespace(),Resource('controls',True),poll_interval_seconds=.01,presenter=Resource('presenter'),audio_presenter=Resource('audio'))
 try:app.stop()
 except OSError:pass
 app.stop()
 assert calls==['controls']
 results['shutdown_error_skips_audio_and_retry']=calls

def tooling_probe():
 import asl_device.laptop_acceptance as pre
 import asl_device.__main__ as cli
 cfg=types.SimpleNamespace(scanner=types.SimpleNamespace(profile='android_ip_camera',camera_backend='auto',camera_index=0,camera_width=640,camera_height=480,camera_fps=30))
 observed=[]
 class Camera:
  def __init__(self,*a,**kw):observed.append('OpenCVCameraSource')
  def start(self):pass
  def read(self):
   import numpy as np
   return types.SimpleNamespace(payload=np.zeros((480,640,3)),frame_id=types.SimpleNamespace(value='fake'))
  def stop(self):pass
 with patch('book_scanner.video.sources.OpenCVCameraSource',Camera):result=pre._probe_camera(cfg)
 try:pre._probe_e0b_profile(cfg)
 except ValueError as e:profile_error=str(e)
 results['android_preflight']=dict(selected=list(observed),result=result,profile_error=profile_error)
 # Actual DeviceApplication run stops on coordinator STOPPED; CLI drops terminal outcome.
 from asl_device.types import DeviceFlowState
 class Coordinator:
  state=DeviceFlowState.READING;reading_snapshot=None;scanner=types.SimpleNamespace()
  def start(self):return ()
  def poll(self):self.state=DeviceFlowState.STOPPED;observed.append('fatal_error');return ()
  def stop(self):return ()
 app=DeviceApplication(Coordinator(),types.SimpleNamespace(poll=lambda:(),close=lambda:None),poll_interval_seconds=.001,sleeper=lambda _:None)
 with patch.object(cli,'build_local_device',return_value=types.SimpleNamespace(application=app)),patch.object(sys,'argv',['asl_device','--config','unused']):code=cli.main()
 assert code==0 and 'fatal_error' in observed
 results['fatal_cli_return']=dict(return_code=code,limitation='fake coordinator terminal state; actual fatal propagation separately source-inspected')

if __name__=='__main__':
 for name,call in [('camera',camera_probe),('liveness',lambda:results.update(liveness=[liveness_probe(8000,1.6),liveness_probe(8000,2.5),liveness_probe(30000,2.5)])),('audio',audio_probe),('cleanup',adjacent_cleanup_probe),('tooling',tooling_probe)]:
  try:call()
  except Exception as e:
   import traceback
   results[name+'_probe_error']=traceback.format_exc()
 (OUT/'reproduction-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
 print(json.dumps(results,indent=2))
