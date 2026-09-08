import threading
from types import SimpleNamespace as NS

import pytest

from asl_device.adapters.reading_audio import SoundDeviceWavPlayer, _validate_wav
from asl_device.reading_audio import AudioOperationCancelled, AudioResourceCache, ReadingAudioController
from .test_reading_audio_adapters import _wav
from .test_reading_audio import Player, ResourcePort, Sink, _snapshot


class StopCallback(Exception): pass
class AbortCallback(Exception): pass


def resource():
    import hashlib
    raw = _wav()
    return _validate_wav(raw, hashlib.sha256(raw).hexdigest())


def test_interrupt_never_calls_native_from_input_thread_and_close_is_once():
    started = threading.Event()
    calls = []
    class Stream:
        def __init__(self, **kwargs): calls.append(('create', threading.get_ident()))
        def start(self):
            calls.append(('start', threading.get_ident()))
            started.set()
        def abort(self): calls.append(('abort', threading.get_ident()))
        def close(self): calls.append(('close', threading.get_ident()))

    player = SoundDeviceWavPlayer(sounddevice_module=NS(RawOutputStream=Stream))
    outcomes = []
    def run():
        try: player.play(resource(), lambda: False)
        except AudioOperationCancelled: outcomes.append('cancelled')
    worker = threading.Thread(target=run)
    worker.start()
    assert started.wait(1)
    player.stop()
    worker.join(1)
    assert not worker.is_alive()
    player.close()
    assert outcomes == ['cancelled']
    assert [name for name, _ in calls] == ['create', 'start', 'abort', 'close']
    assert {owner for _, owner in calls} == {worker.ident}


@pytest.mark.parametrize('status', [False, True])
def test_callback_finish_and_underrun_have_distinct_outcomes(status):
    calls = []
    class Stream:
        def __init__(self, **kwargs): self.kwargs = kwargs
        def start(self):
            try:
                self.kwargs['callback'](bytearray(4096), 2048, None, status)
            except (StopCallback, AbortCallback):
                self.kwargs['finished_callback']()
        def close(self): calls.append('close')

    player = SoundDeviceWavPlayer(sounddevice_module=NS(
        RawOutputStream=Stream, CallbackStop=StopCallback, CallbackAbort=AbortCallback))
    if status:
        with pytest.raises(RuntimeError, match='underrun'):
            player.play(resource(), lambda: False)
    else:
        player.play(resource(), lambda: False)
    assert calls == ['close']
    player.close()


def test_replacement_is_not_runnable_until_old_stop_has_targeted_old_job():
    in_stop, release_stop, started = [threading.Event() for _ in range(3)]
    class OrderedPlayer(Player):
        gate = True
        def stop(self):
            if self.gate:
                in_stop.set()
                assert release_stop.wait(1)
            super().stop()
        def play(self, value, cancelled):
            started.set()
            super().play(value, cancelled)
    player = OrderedPlayer()
    sink = Sink()
    controller = ReadingAudioController(ResourcePort(), player, AudioResourceCache(max_bytes=100, max_entries=4), feedback=sink)
    submit = threading.Thread(target=lambda: controller.present(_snapshot(1, 's0-audio:'+'a'*32)))
    try:
        submit.start()
        assert in_stop.wait(1)
        assert not started.wait(.05)
        release_stop.set()
        submit.join(1)
        assert controller.wait_idle(1)
        assert len(player.played) == 1
        assert not any(e.code.value == 'reading_audio_failed' for e in sink.events)
    finally:
        player.gate = False
        release_stop.set()
        submit.join(1)
        controller.close()


def test_join_timeout_is_failure_and_can_be_cleaned_up_later():
    player = Player()
    controller = ReadingAudioController(ResourcePort(), player, AudioResourceCache(max_bytes=100, max_entries=4))
    worker = controller._worker
    # Simulate the join outcome, not a 30.5s elapsed-time measurement.
    controller._worker = NS(join=lambda **kw: None, is_alive=lambda: True)
    with pytest.raises(RuntimeError, match='did not terminate'):
        controller.close()
    assert player.closed == 0
    controller._worker = worker
    controller.close()
    assert not worker.is_alive()
    assert player.closed == 1
