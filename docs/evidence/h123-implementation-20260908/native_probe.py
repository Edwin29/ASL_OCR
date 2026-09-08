"""Bounded actual-speaker probe; no HTTP, COM, camera, credentials or state."""
import ctypes,hashlib,io,json,math,os,pathlib,struct,sys,threading,time,wave
ROOT=pathlib.Path(__file__).resolve().parent
for package in ['device-runtime','book-scanner','document-parser']:
    sys.path.insert(0,str(ROOT/package/'src'))
import sounddevice as sd
from asl_device.adapters.reading_audio import SoundDeviceWavPlayer,_validate_wav
from asl_device.reading_audio import AudioResourceCache,ReadingAudioController
from asl_device.types import ReadingSessionId,DatapackId,ReadingSnapshot

result={'status':'running','interpreter':sys.executable,'source_root':str(ROOT),'physical_serial_packets':0,
        'sounddevice':sd.__version__,'output_device':dict(sd.query_devices(kind='output')),
        'heard_by_human':'not_observed'}
sid=ctypes.c_ulong()
ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(),ctypes.byref(sid))
result['windows_session_id']=sid.value
(ROOT/'native-start.json').write_text(json.dumps(result,indent=2),encoding='utf-8')

def wav_resource():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as writer:
        writer.setparams((1,2,16000,0,'NONE','not compressed'))
        writer.writeframes(b''.join(struct.pack('<h',round(500*math.sin(2*math.pi*440*n/16000))) for n in range(9600)))
    raw=stream.getvalue()
    return _validate_wav(raw,hashlib.sha256(raw).hexdigest())

class Port:
    def fetch(self,session,ref,cancelled):return resource
class Sink:
    def __init__(self):self.events=[]
    def emit(self,event):self.events.append({'code':event.code.value,'details':dict(event.details)})

resource=wav_resource()
sink=Sink()
controller=None
try:
    controller=ReadingAudioController(Port(),SoundDeviceWavPlayer(),AudioResourceCache(max_bytes=262144,max_entries=4),feedback=sink)
    for generation in range(1,21):
        controller.present(ReadingSnapshot(ReadingSessionId('native-diagnostic'),DatapackId('native-diagnostic'),
                           (('generation',generation),),(),'s0-audio:'+f'{generation:032x}'))
        time.sleep(.045)
        if any(e['code']=='reading_audio_failed' for e in sink.events):raise RuntimeError('audio playback failed')
    if not controller.wait_idle(5):raise RuntimeError('latest audio did not complete')
    controller.close()
    result['events']=sink.events
    result['worker_alive']=controller._worker.is_alive()
    completed=[e for e in sink.events if e['code']=='reading_audio_playback_completed']
    if not completed or completed[-1]['details'].get('generation')!=20:raise RuntimeError('latest generation completion missing')
    if any(e['code']=='reading_audio_failed' for e in sink.events):raise RuntimeError('audio playback failed')
    result['status']='passed'
except Exception as exc:
    result['status']='failed'
    result['error_class']=type(exc).__name__
    result['error']=str(exc)
    result['events']=sink.events
finally:
    if controller is not None:
        try:controller.close()
        except Exception as exc:result['close_error']=type(exc).__name__
    (ROOT/'native-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
