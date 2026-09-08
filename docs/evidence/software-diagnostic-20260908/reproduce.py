"""Bounded diagnostic probes against unchanged production objects; no real I/O.

Fake boundary injection is explicit. These assertions reproduce current defects,
not replacement acceptance tests. Run with -B. No camera, serial, audio or HTTP I/O.
"""
import io,json,pathlib,sys,threading,time,wave,queue
from types import SimpleNamespace as NS
from unittest.mock import patch

if '__file__' in globals():
    root=pathlib.Path(__file__).resolve().parents[3]
    for package in ['device-runtime','book-scanner','document-parser']:
        sys.path.insert(0,str(root/package/'src'))

import numpy as np
from book_scanner.video.engine import SampledFrameEngine
from book_scanner.video.events import VideoEventType
from book_scanner.video.config import OpaqueFooterIdentityPolicy
from book_scanner.video.opaque_identity import OpaqueFooterTokenPair,OpaqueReferenceBank
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameId,ArtifactId,VideoSessionState
from book_scanner.video.sources import HttpSnapshotCameraSource,SnapshotTransportError,FrameDecodeError
from asl_device.adapters.reading_audio import SoundDeviceWavPlayer,_validate_wav
from asl_device.reading_audio import AudioOperationCancelled
from asl_device.adapters.stm_serial import StmSerialControlSource
from asl_device.app_config import StmSerialConfig
from asl_device.types import DeviceInputEvent,DeviceControl,InputAction
from asl_device.hold_repeat import HoldRepeatController

results={}
class Clock:
    now=0.
    def monotonic(self): return self.now

def pair(index,clock,left='28',right='29'):
    return OpaqueFooterTokenPair(left,right,FrameId('q'+str(index)),clock.now,'fake-recognizer','diagnostic','0'*64,'1'*64)

def page_change_case(latency,steps=20,missing=False,budget=8000):
    clock=Clock()
    class Camera:
        exhausted=False
        n=0
        def read(self):
            self.n+=1; clock.now+=latency
            return FrameSample(FrameId('q'+str(self.n)),clock.now,np.zeros((2,2,3),dtype=np.uint8))
        def stop(self): pass
    cam=Camera()
    analyzed=NS(candidate=NS(retry_reasons=()),gray_preview=None,mask_preview=None,seam_proxy_fraction=.5)
    gate=NS(observe=lambda *a,**k:NS(eligible=True,stable_count=3,motion_seen=False,comparison=None,changed=False),reset=lambda:None)
    policy=OpaqueFooterIdentityPolicy(observation_interval_ms=750,max_collection_ms=budget)
    eng=SampledFrameEngine(cam,NS(analyze=lambda f:analyzed),NS(),NS(),session_id='diag',clock=clock,
        opaque_identity_policy=policy,page_number_provider=NS(),page_change_gate=gate,
        identity_provider=NS(fingerprint_preview=lambda *a:None))
    eng.state=VideoSessionState.WAITING_FOR_PAGE_CHANGE
    eng._opaque_waiting_reference=OpaqueReferenceBank(ArtifactId('accepted'),'receipt','diag',(pair(-1,clock,'26','27'),),'diagnostic')
    # Inject only completed recognizer result, retaining production engine/collector/reset/guidance.
    eng._observe_opaque_pair=lambda f,a,e: None if missing else pair(cam.n,clock)
    events=[]
    for _ in range(steps):
        eng._poll_opaque_page_change(events)
        if eng.state is VideoSessionState.SEARCHING: break
        clock.now+=.02
    out={'latency_per_observation':latency,'budget_ms':budget,'elapsed_ms':clock.now*1000,'N':policy.query_sample_count,'state':eng.state.value,'observations':cam.n,
         'decisions':[dict(e.details) for e in events if e.event_type.value=='opaque_identity_decided'],
         'event_types':sorted(set(e.event_type.value for e in events))}
    eng.close()
    return out

results['liveness_fast']=page_change_case(1.9)
results['liveness_slow']=page_change_case(2.5)
results['liveness_missing']=page_change_case(2.5,missing=True)
results['liveness_slow_30s']=page_change_case(2.5,budget=30000)
assert results['liveness_fast']['state']=='searching'
assert results['liveness_slow']['state']=='waiting_for_page_change'
assert results['liveness_slow_30s']['state']=='searching'
assert VideoEventType.GUIDANCE_REQUESTED.value not in results['liveness_slow']['event_types']
assert VideoEventType.GUIDANCE_REQUESTED.value not in results['liveness_missing']['event_types']

def snapshot_error(exc):
    calls=[]
    def fetch(*a,**k): calls.append(k); raise exc
    camera=HttpSnapshotCameraSource('https://camera.invalid/snapshot',fetcher=fetch,min_width=1,min_height=1)
    camera.start()
    eng=SampledFrameEngine(camera,NS(),NS(),NS(),session_id='fatal')
    eng._camera_started=True
    events=[]; eng._read_frame_for_opaque(events)
    result={'calls':len(calls),'state':eng.state.value,'events':[(e.event_type.value,e.reason.value if e.reason else None) for e in events]}
    eng.close();return result

import requests
results['snapshot_taxonomy']={}
for name,exception in [('timeout',requests.exceptions.Timeout()),('401',requests.exceptions.HTTPError(response=NS(status_code=401))),('503',requests.exceptions.HTTPError(response=NS(status_code=503)))]:
    results['snapshot_taxonomy'][name]=snapshot_error(exception)
assert all(r['state']=='error' and r['calls']==1 for r in results['snapshot_taxonomy'].values())

# A bad JPEG already has three bounded decode attempts, unlike transport errors.
import cv2
jpeg=cv2.imencode('.jpg',np.zeros((2,2,3),dtype=np.uint8))[1].tobytes()
def decode_sequence(payloads):
    calls=[]
    class Response:
        headers={}
        def __init__(self,payload):self.payload=payload
        def raise_for_status(self):pass
        def iter_content(self,chunk_size):yield self.payload
        def close(self):pass
    def fetch(*a,**kw):
        calls.append(1);return Response(payloads[min(len(calls)-1,len(payloads)-1)])
    camera=HttpSnapshotCameraSource('https://camera.invalid/snapshot',fetcher=fetch,min_width=1,min_height=1)
    camera.start()
    try:
        frame=camera.read();state='success'
    except FrameDecodeError:state='FrameDecodeError'
    finally:camera.stop()
    return {'calls':len(calls),'result':state}
results['decode_once_then_good']=decode_sequence([b'not-a-jpeg',jpeg])
results['decode_persistent']=decode_sequence([b'not-a-jpeg'])
assert results['decode_once_then_good']=={'calls':2,'result':'success'}
assert results['decode_persistent']=={'calls':3,'result':'FrameDecodeError'}

# Positive downstream control: actual guidance maps to a system cue.
from asl_device.reading_audio import _system_audio_request
from asl_device.events import FeedbackCode,FeedbackEvent
results['guidance_mapper_positive_control']=_system_audio_request(FeedbackEvent(FeedbackCode.SCANNER_GUIDANCE,0.,(('guidance_code','footer_identity_unavailable'),)))
assert results['guidance_mapper_positive_control'][0]=='s0-system-cue:scan.guidance'

# Actual native player lifecycle with a controllable stand-in for PortAudio.
buf=io.BytesIO()
with wave.open(buf,'wb') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\x00\x00'*64)
resource=_validate_wav(buf.getvalue(),'0'*64)
def audio_overlap():
    entered=threading.Event();abort_entered=threading.Event();allow_write=threading.Event();allow_abort=threading.Event();closed=threading.Event();cancel=threading.Event()
    observations=[]
    class Stream:
        writing=False;aborting=False
        def start(self): pass
        def write(self,data):
            self.writing=True;entered.set();assert allow_write.wait(3);self.writing=False
        def abort(self):
            self.aborting=True;observations.append({'abort_overlaps_write':self.writing});abort_entered.set();assert allow_abort.wait(3);self.aborting=False
        def stop(self): observations.append({'stop_overlaps_abort':self.aborting})
        def close(self): observations.append({'close_overlaps_abort':self.aborting});closed.set()
    stream=Stream();player=SoundDeviceWavPlayer(sounddevice_module=NS(RawOutputStream=lambda **k:stream))
    def play():
        try: player.play(resource,cancel.is_set)
        except AudioOperationCancelled: pass
    worker=threading.Thread(target=play);worker.start();assert entered.wait(3)
    cancel.set();stopper=threading.Thread(target=player.stop);stopper.start();assert abort_entered.wait(3)
    allow_write.set();assert closed.wait(3);allow_abort.set()
    worker.join(3);stopper.join(3);player.close()
    assert not worker.is_alive() and not stopper.is_alive()
    assert observations==[{'abort_overlaps_write':True},{'stop_overlaps_abort':True},{'close_overlaps_abort':True}]
    return observations
results['native_call_overlap']=[audio_overlap() for _ in range(10)]

# Notify-before-stop lets the replacement itself become the stop target.
from asl_device.reading_audio import ReadingAudioController,AudioResourceCache
from asl_device.types import ReadingSnapshot,ReadingSessionId,DatapackId
started=threading.Event();aborted=threading.Event();audio_events=[]
class LateStopPlayer:
    def play(self,resource,cancelled):
        started.set();assert aborted.wait(3)
        if not cancelled():raise OSError('current generation was aborted')
    def stop(self):
        assert started.wait(3);aborted.set()
    def close(self):pass
controller=ReadingAudioController(NS(fetch=lambda *a:resource),LateStopPlayer(),AudioResourceCache(max_bytes=10000,max_entries=2),feedback=NS(emit=lambda e:audio_events.append({'code':e.code.value,**dict(e.details)})))
controller.present(ReadingSnapshot(ReadingSessionId('diag'),DatapackId('diag'),(('generation',1),),(),'s0-audio:'+'a'*32))
assert controller.wait_idle(3)
controller.close()
results['notify_before_stop_current_generation_failure']=audio_events
assert any(e['code']=='reading_audio_failed' and e['generation']==1 for e in audio_events)

# Reproduce priority release overtaking an activation across the 16-event poll limit.
class Serial:
    def __init__(self):
        self.lines=queue.Queue();self.writes=[]
        for line in [b'HELLO,3\n']+[f'NAV,U,S,{n}\n'.encode() for n in range(1,17)]+[b'NAV,D,A,17\n',b'NAV,D,R,18\n']:self.lines.put(line)
    def readline(self):
        try:return self.lines.get(timeout=.002)
        except queue.Empty:return b''
    def write(self,payload):self.writes.append(payload.decode().strip());return len(payload)
    def close(self):pass
serial=Serial()
serial_time=[0.]
def serial_clock():serial_time[0]+=.1;return serial_time[0]
stm=StmSerialControlSource(StmSerialConfig(port='FAKE'),event_namespace='diagnostic',serial_factory=lambda c:serial,monotonic=serial_clock)
stm.present(None)
deadline=time.monotonic()+3
while stm._release_events.empty() and time.monotonic()<deadline:time.sleep(.002)
assert not stm._release_events.empty()
clock=Clock();hold=HoldRepeatController(monotonic=clock.monotonic)
batches=[]
for _ in range(2):
    batch=stm.poll();batches.append([e.event_id for e in batch])
    for e in batch:
        if e.control is DeviceControl.DOWN: hold.apply_edge(e)
        else: hold.cancel()
clock.now=1.
repeats=hold.due()
results['release_overtakes_activation']={'batches':batches,'host_writes':serial.writes,'hold_active_after_physical_release':hold.active,'late_repeat_count':len(repeats)}
assert hold.active and len(repeats)==1
stm.close()

# Real preflight function, fake OpenCV source; production camera must not open.
from asl_device.laptop_acceptance import _probe_camera,_probe_e0b_profile
cfg=NS(scanner=NS(profile='android_ip_camera',camera_index=0,camera_width=None,camera_height=None,camera_fps=None,camera_backend='auto'))
opened=[]
class FakeWebcam:
    def __init__(self,index,**kw): opened.append(index)
    def start(self):pass
    def stop(self):pass
    def read(self):return NS(payload=np.zeros((480,640,3)),frame_id=FrameId('webcam'))
with patch('book_scanner.video.sources.OpenCVCameraSource',FakeWebcam):
    results['android_preflight_wrong_source']=_probe_camera(cfg)
try:_probe_e0b_profile(cfg)
except ValueError as e:results['android_preflight_profile_rejection']=str(e)
assert opened==[0]

# Real coordinator fatal + application loop, replacing external ports only.
import asl_device.__main__ as cli
from asl_device.coordinator import DeviceFlowCoordinator
from asl_device.application import DeviceApplication
from asl_device.types import DeviceId
from asl_device.protocols import FatalPortError
feedback=[]
class FatalCatalog:
    def list_datapacks(self,*a,**k):raise FatalPortError('diagnostic startup fatal')
coord=DeviceFlowCoordinator(device_id=DeviceId('diagnostic'),viewport_size=10,clock=Clock(),catalog_port=FatalCatalog(),scan_session_port=NS(),scanner=NS(close=lambda:None),delivery=NS(),reading=NS(),feedback=NS(emit=lambda e:feedback.append(e.code.value)))
app=DeviceApplication(coord,NS(poll=lambda:(),close=lambda:None),poll_interval_seconds=.02)
with patch.object(cli,'build_local_device',return_value=NS(application=app)),patch.object(sys,'argv',['asl_device','--config','fake.toml']):
    results['cli_return_after_handled_fatal']=cli.main()
assert results['cli_return_after_handled_fatal']==0
results['cli_feedback']=feedback
assert 'fatal_error' in feedback
print(json.dumps({'python':sys.version,'results':results},indent=2))
