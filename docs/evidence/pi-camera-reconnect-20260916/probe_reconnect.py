"""Pi deterministic probe: no camera, serial, server or state writes."""
import json
import cv2
import numpy as np
import requests
from book_scanner.video.sources import HttpSnapshotCameraSource, SnapshotTransportError

class Clock:
    now = 0.0
    def monotonic(self): return self.now

class Response:
    headers = {}
    def raise_for_status(self): pass
    def iter_content(self, chunk_size):
        yield cv2.imencode('.jpg', np.zeros((2, 3, 3), dtype=np.uint8))[1].tobytes()
    def close(self): pass

clock = Clock()
mode = 'offline'
calls = []
def fetch(*a, **k):
    calls.append(clock.now)
    if mode == 'offline': raise requests.exceptions.ConnectionError('test-only')
    if mode == 'tls': raise requests.exceptions.SSLError('test-only')
    return Response()

camera = HttpSnapshotCameraSource('https://camera.invalid/snapshot', fetcher=fetch, clock=clock, min_width=1, min_height=1)
camera.start()
try:
    for _ in range(40):
        clock.now = camera._retry_at
        assert camera.read() is None
        count = len(calls)
        assert camera.read() is None
        assert len(calls) == count
    assert clock.now > 150
    mode = 'online'
    clock.now = camera._retry_at
    assert camera.read().frame_id.value == 'phone-snapshot-00000001'
    assert camera.read().frame_id.value == 'phone-snapshot-00000002'
    mode = 'tls'
    try:
        camera.read()
        raise AssertionError('TLS failure must remain permanent')
    except SnapshotTransportError as error:
        assert not error.retryable
finally:
    camera.stop()
count = len(calls)
assert camera.read() is None and len(calls) == count
print(json.dumps(dict(result='PASS',offline_attempts=40,simulated_seconds=clock.now,recovery=True,stop=True,tls_permanent=True)))
