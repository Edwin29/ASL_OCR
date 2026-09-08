from types import SimpleNamespace as NS

import pytest

from asl_device.application import DeviceApplication
from asl_device.adapters.stm_serial import StmSerialControlSource
from asl_device.types import DeviceFlowState
from .test_h123_boundaries import coordinator
from .test_stm_serial import FakeSerial, _config, _wait_until


@pytest.mark.parametrize('fatal', [None, 'original incident'])
def test_cleanup_failures_keep_first_cause_and_attempt_every_resource(fatal):
    calls = []
    first = OSError('cancel failure')

    def cancel():
        calls.append('cancel')
        raise first

    def disconnect():
        calls.append('disconnect')
        raise RuntimeError('disconnect failure')

    coord = coordinator(scanner=NS(cancel=cancel, close=lambda: calls.append('scanner.close')),
                        connectivity=NS(stop=disconnect))
    coord.scan_session = NS()
    coord.state = DeviceFlowState.SCANNING
    if fatal:
        coord._fatal(fatal, [])
    app = DeviceApplication(coord, NS(close=lambda: calls.append('controls.close')),
                            poll_interval_seconds=.02)
    app._started = True
    app.stop()
    app.stop()
    assert calls == ['cancel', 'disconnect', 'scanner.close', 'controls.close']
    assert app.exit_code == 2
    assert coord.fatal_reason == fatal
    assert coord.cleanup_failures == ('scanner.cancel:OSError', 'connectivity.stop:RuntimeError')
    assert app.cleanup_failures == ('coordinator:OSError',)
    assert coord.state is DeviceFlowState.STOPPED


def test_direct_coordinator_stop_raises_original_cleanup_exception_once():
    first = OSError('first cleanup')
    coord = coordinator(connectivity=NS(stop=lambda: (_ for _ in ()).throw(first)))
    with pytest.raises(OSError) as failure:
        coord.stop()
    assert failure.value is first
    assert coord.state is DeviceFlowState.STOPPED
    assert coord.stop() == ()


def test_worker_requests_deadline_and_size_bounded_pyserial_operation():
    class BoundedSerial(FakeSerial):
        def __init__(self):
            super().__init__([b'HELLO,3\n', b'NAV,D,A,7', b'8\n'])
            self.bounds = []

        def read_until(self, expected=b'\n', size=None):
            self.bounds.append((expected, size))
            return super().readline()

    serial = BoundedSerial()
    source = StmSerialControlSource(_config(), serial_factory=lambda _: serial)
    try:
        source.present(None)
        _wait_until(lambda: b'ACK,78\n' in serial.written())
        assert serial.bounds and set(serial.bounds) == {(b'\n', 256)}
        assert b'ACK,7\n' not in serial.written()
    finally:
        source.close()
    assert not source._thread.is_alive()
