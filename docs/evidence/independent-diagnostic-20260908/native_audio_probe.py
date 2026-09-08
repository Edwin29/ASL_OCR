"""Silent, bounded native player-only supersession probe. No service/serial/camera."""
import io,wave,hashlib,threading,time,json,sys,os,ctypes
import sounddevice as sd
from asl_device.adapters.reading_audio import SoundDeviceWavPlayer,_validate_wav
from asl_device.reading_audio import AudioOperationCancelled
session=ctypes.c_ulong();ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(),ctypes.byref(session))
print(json.dumps(dict(kind='identity',pid=os.getpid(),session_id=session.value,python=sys.executable,sounddevice_version=sd.__version__,portaudio=sd.get_portaudio_version(),default_device=list(sd.default.device))),flush=True)
buf=io.BytesIO()
with wave.open(buf,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*16000)
raw=buf.getvalue();resource=_validate_wav(raw,hashlib.sha256(raw).hexdigest())
player=SoundDeviceWavPlayer();errors=[];completed=0
for i in range(100):
 cancel=threading.Event()
 def play():
  try:player.play(resource,cancel.is_set)
  except AudioOperationCancelled:pass
  except Exception as e:errors.append(type(e).__name__+': '+str(e))
 worker=threading.Thread(target=play,daemon=True);worker.start();time.sleep(.01+(i%4)*.005);cancel.set();player.stop();worker.join(1)
 if worker.is_alive():print(json.dumps(dict(kind='worker_stall',iteration=i)),flush=True);break
 completed+=1
 if errors:break
player.close()
print(json.dumps(dict(kind='result',iterations=completed,errors=errors,hardware='default native audio only; silent PCM',scope='SSH player-only; no S0 HTTPS, FRAME, catalog controller, or audible-noise assessment')),flush=True)
