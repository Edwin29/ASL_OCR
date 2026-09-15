"""Protect the ARM CPU workaround and unchanged non-ARM/accelerator settings."""
import hashlib
import sys
from types import SimpleNamespace

import pytest

from book_scanner.video import page_number_recognizer as recognizer_module


@pytest.mark.parametrize(
    ('machine', 'device', 'expected'),
    [
        ('aarch64', None, {'cpu_threads': 1}),
        ('aarch64', 'cpu', {'device': 'cpu', 'cpu_threads': 1}),
        ('ARM64', None, {'cpu_threads': 1}),
        ('AMD64', None, {}),
        ('x86_64', 'cpu', {'device': 'cpu'}),
        ('aarch64', 'gpu:0', {'device': 'gpu:0'}),
    ],
)
def test_paddle_platform_runtime_options(monkeypatch, tmp_path, machine, device, expected):
    hashes = {}
    for name in ('inference.json', 'inference.pdiparams', 'inference.yml'):
        content = name.encode('ascii')
        (tmp_path / name).write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    calls = []

    def model(**kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(recognizer_module.platform, 'machine', lambda: machine)
    monkeypatch.setitem(sys.modules, 'paddleocr', SimpleNamespace(TextRecognition=model))
    recognizer = recognizer_module.PaddleRoiDigitRecognizer(
        tmp_path, expected_file_hashes=hashes, device=device,
    )
    assert calls == [{
        'model_name': 'en_PP-OCRv5_mobile_rec',
        'model_dir': str(tmp_path.resolve()),
        **expected,
    }]
    assert recognizer.verified_file_hashes == hashes
    assert recognizer.load_count == 1
