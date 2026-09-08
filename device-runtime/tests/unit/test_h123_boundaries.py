from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest

from asl_device.application import DeviceApplication
from asl_device.coordinator import DeviceFlowCoordinator
from asl_device.protocols import FatalPortError
from asl_device.types import DeviceControl, DeviceFlowState, DeviceId, InputAction
from asl_device.hold_repeat import HoldRepeatController
from asl_device.adapters.stm_serial import StmSerialControlSource, _SerialLineFramer
from asl_device.laptop_acceptance import _probe_camera, _probe_e0b_profile
from asl_device.app_config import DeviceAppConfig
from .test_laptop_acceptance import _write_laptop_config
from .test_stm_serial import FakeSerial, _config, _wait_until


def coordinator(*, catalog=None, connectivity=None, scanner=None):
    return DeviceFlowCoordinator(
        device_id=DeviceId('h123-test'), viewport_size=10,
        clock=NS(monotonic=lambda: 0.), catalog_port=catalog or NS(),
        scan_session_port=NS(), scanner=scanner or NS(close=lambda: None),
        delivery=NS(), reading=NS(), feedback=NS(emit=lambda _: None),
        connectivity=connectivity,
    )


def test_fatal_cli_returns_nonzero_and_preserves_first_reason(monkeypatch):
    import asl_device.__main__ as cli

    def fail(*_):
        raise FatalPortError('catalog failure')

    coord = coordinator(catalog=NS(list_datapacks=fail))
    app = DeviceApplication(coord, NS(close=lambda: None), poll_interval_seconds=.02)
    monkeypatch.setattr(cli, 'build_local_device', lambda *a, **k: NS(application=app))
    monkeypatch.setattr(sys, 'argv', ['asl_device', '--config', 'unused.toml'])
    assert cli.main() == 2
    assert coord.fatal_reason == 'catalog failure'
    coord._fatal('later error', [])
    assert coord.fatal_reason == 'catalog failure'


def test_fatal_shutdown_disconnects_once_and_continues_after_close_failure():
    calls = []

    def broken_close():
        calls.append('scanner')
        raise OSError('close failed')

    coord = coordinator(
        scanner=NS(close=broken_close),
        connectivity=NS(stop=lambda: calls.append('disconnect') or ()),
    )
    coord._fatal('first failure', [])
    app = DeviceApplication(coord, NS(close=lambda: calls.append('controls')),
                            poll_interval_seconds=.02,
                            audio_presenter=NS(close=lambda: calls.append('audio')))
    app._started = True
    app.stop()
    app.stop()
    assert calls == ['disconnect', 'scanner', 'controls', 'audio']
    assert app.cleanup_failures == ('SimpleNamespace:OSError',)
    assert app.exit_code == 2


def test_partial_start_failure_still_closes_connectivity():
    calls = []
    coord = coordinator(connectivity=NS(
        start=lambda: (_ for _ in ()).throw(OSError('startup failure')),
        stop=lambda: calls.append('disconnect') or (),
    ))
    app = DeviceApplication(coord, NS(close=lambda: calls.append('controls')), poll_interval_seconds=.02)
    with pytest.raises(OSError, match='startup failure'):
        app.start()
    assert calls == ['disconnect', 'controls']
    assert coord.state is DeviceFlowState.STOPPED


def test_ip_preflight_uses_shared_strict_factory_and_closes_on_failure(tmp_path, monkeypatch):
    from book_scanner.video import runtime_composition as runtime
    from book_scanner.video import sources

    base = DeviceAppConfig.from_toml(_write_laptop_config(tmp_path))
    scanner = replace(base.scanner, profile='android_ip_camera', camera_width=None,
                      camera_height=None, camera_snapshot_url='https://camera.invalid/snapshot')
    config = replace(base, scanner=scanner)
    assert _probe_e0b_profile(config)['source_transport'] == 'http_snapshot'
    calls = []

    class Source:
        fail = False
        def __init__(self, url, **kwargs): calls.append((url, kwargs))
        def start(self): pass
        def read(self):
            if self.fail: raise RuntimeError('snapshot unavailable')
            return NS(payload=np.zeros((2, 3, 3)), frame_id=NS(value='ip-frame'))
        def stop(self): calls.append('closed')

    monkeypatch.setattr(runtime, 'HttpSnapshotCameraSource', Source)
    monkeypatch.setattr(sources, 'OpenCVCameraSource', lambda *a, **k: pytest.fail('webcam fallback'))
    assert _probe_camera(config)['source_profile'] == 'android_ip_camera'
    assert calls[0][1]['allow_insecure_tls'] is False
    Source.fail = True
    with pytest.raises(RuntimeError, match='snapshot unavailable'):
        _probe_camera(config)
    assert calls.count('closed') == 2


@pytest.mark.parametrize('split', range(1, len(b'NAV,D,A,78\n')))
def test_partial_nav_never_reaches_acceptance_before_delimiter(split):
    framer = _SerialLineFramer()
    packet = b'NAV,D,A,78\n'
    assert list(framer.feed(packet[:split])) == []
    assert list(framer.feed(packet[split:])) == [packet[:-1]]


def test_overflow_discards_entire_record_then_recovers():
    framer = _SerialLineFramer()
    assert list(framer.feed(b'x'*256 + b'NAV,D,A,78\nHELLO,3\r\n')) == [b'HELLO,3\r']


def test_real_worker_does_not_ack_partial_sequence():
    serial = FakeSerial([b'HELLO,3\n', b'NAV,D,A,7', b'8\n'])
    source = StmSerialControlSource(_config(), serial_factory=lambda _: serial)
    try:
        source.present(None)
        _wait_until(lambda: source._events.qsize() == 1)
        assert b'ACK,78\n' in serial.written()
        assert b'ACK,7\n' not in serial.written()
        assert [e.hardware_sequence for e in source.poll()] == [78]
    finally:
        source.close()


def test_cross_batch_urgent_release_keeps_initial_step_without_restarting_hold():
    lines = [b'HELLO,3\n'] + [f'NAV,U,S,{n}\n'.encode() for n in range(1, 17)]
    lines += [b'NAV,D,A,17\n', b'NAV,D,R,18\n']
    serial = FakeSerial(lines)
    source = StmSerialControlSource(replace(_config(), debounce_ms=0), serial_factory=lambda _: serial)
    hold = HoldRepeatController()
    try:
        source.present(None)
        _wait_until(lambda: source._events.qsize() == 17 and not source._release_events.empty())
        batches = [source.poll(), source.poll()]
        assert any(e.action is InputAction.RELEASED for e in batches[0])
        commands = []
        for batch in batches:
            for e in batch:
                if e.control is DeviceControl.DOWN:
                    commands.extend(hold.apply_edge(e))
                else:
                    hold.cancel()
        assert len(commands) == 1  # Preserve the accepted press, in FIFO command order.
        assert not hold.active
        assert hold.due() == ()
    finally:
        source.close()


def test_mode_release_does_not_overtake_prior_accepted_commands():
    serial = FakeSerial([b'HELLO,3\n', b'NAV,C,S,1\n', b'NAV,V,R,2\n'])
    source = StmSerialControlSource(_config(), serial_factory=lambda _: serial)
    try:
        source.present(None)
        _wait_until(lambda: source._events.qsize() == 2)
        assert [e.hardware_sequence for e in source.poll()] == [1, 2]
    finally:
        source.close()
