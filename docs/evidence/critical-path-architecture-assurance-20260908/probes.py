"""Actual production objects with explicitly fake boundaries; no physical I/O.

Assertion success proves current behavior, not product acceptance.
Executed on Laptop via stdin with -B; no Laptop files are created.
"""
import inspect, json, queue, sys, threading, time
from types import SimpleNamespace as NS
from asl_device.application import DeviceApplication
from asl_device.coordinator import DeviceFlowCoordinator
from asl_device.app_config import StmSerialConfig
from asl_device.adapters.stm_serial import StmSerialControlSource
from asl_device.types import DeviceControl,DeviceFlowState,DeviceId,DeviceInputEvent,InputAction
from book_scanner.video.engine import SampledFrameEngine
from book_scanner.video.types import VideoSessionState

results = {}
def wait_for(predicate):
    end = time.monotonic()+2
    while not predicate() and time.monotonic()<end:
        time.sleep(.002)
    assert predicate()

# CP-I1: acquisition blocks the actual application step and the engine cancel lock.
entered, release, cancel_attempt, cancelled = [threading.Event() for _ in range(4)]
class Camera:
    exhausted=False
    def read(self):
        entered.set()
        assert release.wait(2)
        return None
    def stop(self): pass
engine=SampledFrameEngine(Camera(),NS(),NS(),NS(),session_id='assurance')
engine.state=VideoSessionState.SEARCHING
inputs=[]
coord=NS(state=DeviceFlowState.SCANNING,reading_snapshot=None,scanner=engine,
         poll=engine.poll,handle_input=lambda e: inputs.append(e.event_id) or (),stop=lambda:())
app=DeviceApplication(coord,NS(poll=lambda:(),close=lambda:None),poll_interval_seconds=.02)
app._started=True
def attempt_cancel():
    cancel_attempt.set()
    engine.cancel()
    cancelled.set()
step=threading.Thread(target=app.step)
stop=threading.Thread(target=attempt_cancel)
step.start()
assert entered.wait(2)
app.submit_input(DeviceInputEvent('queued-confirm',DeviceControl.CONFIRM,InputAction.LONG,time.monotonic()))
stop.start()
assert cancel_attempt.wait(2)
try:
    cancel_blocked=not cancelled.wait(.05)
    results['CP-I1']={'input_processed_during_block':bool(inputs),'cancel_blocked_on_engine_lock':cancel_blocked,
                      'measurement':'50ms barrier observation, not live-camera latency or an SLA'}
    assert not inputs and cancel_blocked
finally:
    release.set(); step.join(2); stop.join(2)
app.step()
assert inputs==['queued-confirm']
app.stop()
results['CP-I1']['threads_cleaned']=not step.is_alive() and not stop.is_alive()

# CP-H1: pyserial readline can return a timed-out partial line. No byte corruption
# is injected: the intended input is NAV,D,A,78\n, delivered in two read results.
class Serial:
    def __init__(self): self.lines=queue.Queue(); self.writes=[]; self.closed=False
    def readline(self):
        try:return self.lines.get(timeout=.005)
        except queue.Empty:return b''
    def write(self,data):self.writes.append(data.decode('ascii'));return len(data)
    def close(self):self.closed=True
serial=Serial()
cfg=StmSerialConfig(port='FAKE',read_timeout_ms=20)
stm=StmSerialControlSource(cfg,serial_factory=lambda _:serial,event_namespace='assurance')
stm.poll()
serial.lines.put(b'HELLO,3\n')
wait_for(lambda:'ACK,HELLO,3\n' in serial.writes)
serial.lines.put(b'NAV,D,A,7')
wait_for(lambda:'ACK,7\n' in serial.writes)
serial.lines.put(b'8\n')
wait_for(lambda:serial.lines.empty())
events=stm.poll()
stm.close()
results['CP-H1']={'intended_packet':'NAV,D,A,78\\n','read_results':['NAV,D,A,7','8\\n'],
                  'acks':[s.strip() for s in serial.writes if s.startswith('ACK')],
                  'accepted_sequences':[e.hardware_sequence for e in events],
                  'connection_closed':serial.closed}
assert results['CP-H1']['accepted_sequences']==[7]
# Record installed low-level Windows read implementation, not guessed API behavior.
import serial.serialwin32
results['serial_read_source']={'file':serial.serialwin32.__file__,
                               'read':inspect.getsource(serial.serialwin32.Serial.read)}

# CP-T1: fatal terminal state skips the existing presence disconnect lifecycle.
calls=[]
coordinator=DeviceFlowCoordinator(device_id=DeviceId('assurance'),viewport_size=10,
    clock=NS(monotonic=lambda:0.),catalog_port=NS(),scan_session_port=NS(),
    scanner=NS(close=lambda:calls.append('scanner.close')),delivery=NS(),reading=NS(),
    feedback=NS(emit=lambda _:None),connectivity=NS(stop=lambda:calls.append('connectivity.stop') or ()))
coordinator.state=DeviceFlowState.SCANNING
coordinator._fatal('injected scanner fatal',[])
app=DeviceApplication(coordinator,NS(close=lambda:calls.append('controls.close')),poll_interval_seconds=.02)
app._started=True
app.stop()
results['CP-T1']={'calls':calls,'coordinator_state':coordinator.state.value,
                 'scope':'actual fatal/stop code; fake connectivity spy, not a live C0 leak claim'}
assert 'connectivity.stop' not in calls and 'scanner.close' in calls

print(json.dumps({'python':sys.version,'results':results},indent=2))
