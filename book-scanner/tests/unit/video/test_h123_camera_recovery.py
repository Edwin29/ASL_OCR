import threading
import time
from types import SimpleNamespace as NS

import cv2
import numpy as np
import pytest
import requests

from book_scanner.video.engine import SampledFrameEngine
from book_scanner.video.events import VideoEventType
from book_scanner.video.sources import HttpSnapshotCameraSource, SnapshotTransportError
from book_scanner.video.operator_preview import ThreadedPreviewCameraSource
from book_scanner.video.types import VideoSessionState, ReadinessReason
from .test_engine_v3a5 import _FakePageNumberProvider, _engine, _policy, _artifact_id, _start_and_reach_ready


class Clock:
    now = 0.
    def monotonic(self): return self.now


class Response:
    headers = {}
    def raise_for_status(self): pass
    def iter_content(self, chunk_size):
        yield cv2.imencode('.jpg', np.zeros((2, 3, 3), dtype=np.uint8))[1].tobytes()
    def close(self): pass


def source(fetcher, clock=None):
    return HttpSnapshotCameraSource('https://camera.invalid/snapshot', min_width=1, min_height=1,
                                    fetcher=fetcher, clock=clock)


def test_transient_uses_separate_pulls_and_exhausts_without_retry_storm():
    clock = Clock()
    calls = []
    def fetch(*a, **k):
        calls.append(clock.now)
        raise requests.exceptions.Timeout('untrusted transport detail')
    camera = source(fetch, clock)
    camera.start()
    try:
        assert camera.read() is None
        assert camera.read() is None
        assert calls == [0.]
        clock.now = .25
        assert camera.read() is None
        clock.now = .75
        with pytest.raises(SnapshotTransportError) as error:
            camera.read()
        assert error.value.retryable
        assert 'untrusted' not in str(error.value)
        with pytest.raises(SnapshotTransportError): camera.read()
        assert calls == [0., .25, .75]
    finally:
        camera.stop()


@pytest.mark.parametrize('status,retryable', [(401,False),(403,False),(408,True),(429,True),(500,True),(503,True),(404,False)])
def test_http_status_taxonomy_preserves_permanent_auth(status, retryable):
    def fetch(*a, **k):
        raise requests.exceptions.HTTPError(response=NS(status_code=status))
    camera = source(fetch)
    camera.start()
    try:
        if retryable:
            assert camera.read() is None
        else:
            with pytest.raises(SnapshotTransportError) as exc: camera.read()
            assert exc.value.status_code == status
            assert not exc.value.retryable
    finally: camera.stop()


def test_tls_error_is_permanent_and_engine_preserves_stage():
    def fetch(*a, **k): raise requests.exceptions.SSLError('certificate failed')
    camera = source(fetch)
    engine = SampledFrameEngine(camera, NS(), NS(), NS(), session_id='h123')
    try:
        engine.start()
        events = engine.poll()
        event = next(e for e in events if e.event_type is VideoEventType.SESSION_ERROR)
        assert event.reason is ReadinessReason.CAMERA_UNAVAILABLE
        assert dict(event.details)['stage'] == 'http_snapshot'
        assert dict(event.details)['retryable'] is False
    finally: engine.close()


def test_preview_capture_worker_survives_transient_and_delivers_real_frame():
    calls = []
    def fetch(*a, **k):
        calls.append(1)
        if len(calls) == 1: raise requests.exceptions.Timeout()
        time.sleep(.005)
        return Response()
    camera = source(fetch)
    wrapped = ThreadedPreviewCameraSource(camera, NS(start=lambda:None, stop=lambda:None))
    wrapped.start()
    try:
        end = time.monotonic() + 2
        sample = None
        while sample is None and time.monotonic() < end:
            sample = wrapped.read()
            time.sleep(.005)
        assert sample is not None
        assert sample.frame_id.value == 'phone-snapshot-00000001'
        assert wrapped._thread.is_alive()
    finally: wrapped.stop()


def test_stop_during_read_does_not_publish_late_frame():
    entered, release = threading.Event(), threading.Event()
    def fetch(*a, **k):
        entered.set()
        assert release.wait(1)
        return Response()
    camera = source(fetch)
    camera.start()
    result = []
    worker = threading.Thread(target=lambda: result.append(camera.read()))
    worker.start()
    assert entered.wait(1)
    camera.stop()
    release.set()
    worker.join(1)
    assert not worker.is_alive()
    assert result == [None]


def test_missing_footer_after_receipt_emits_rate_limited_guidance_without_page_change():
    provider = _FakePageNumberProvider([], preview_labels=[('26','27')]*5+[None]*500)
    engine, clock, _, preparer, _, _ = _engine(frame_count=500, page_number_provider=provider,
                                             opaque_identity_policy=_policy(max_collection_ms=8000))
    try:
        artifact = _artifact_id(_start_and_reach_ready(engine, clock))
        engine.delivery_confirmed(artifact, 'receipt-h123')
        events = []
        for _ in range(180):
            clock.advance(.1)
            events.extend(engine.poll())
        cues = [e for e in events if e.event_type is VideoEventType.GUIDANCE_REQUESTED]
        assert cues
        assert len(cues) <= 2  # Existing 15s cooldown, not one cue per frame/reset.
        assert all(e.reason is ReadinessReason.FOOTER_IDENTITY_UNAVAILABLE for e in cues)
        assert not any(e.event_type is VideoEventType.PAGE_CHANGED for e in events)
        assert engine.state is VideoSessionState.WAITING_FOR_PAGE_CHANGE
        assert len(preparer.calls) == 1
    finally: engine.close()
