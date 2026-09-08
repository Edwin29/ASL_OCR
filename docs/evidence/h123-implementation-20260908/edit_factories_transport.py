"""Apply bounded exact replacements; preserve unrelated working-tree content."""
from pathlib import Path
root=Path(__file__).resolve().parents[3]
p=root/'book-scanner/src/book_scanner/video/runtime_composition.py'
s=p.read_text(encoding='utf-8')
start=s.index('            assert self.config.camera_snapshot_url is not None',s.index('if self.config.profile == "android_ip_camera":'))
end=s.index('            return self._with_operator_preview(',start)
block=s[start:end]
helper=block.replace('            assert','    assert').replace('            source =','    return')
helper='\n\ndef create_snapshot_source(config) -> HttpSnapshotCameraSource:\n    """Share strict IP source configuration between production and preflight."""\n'+''.join(line[8:] if line.startswith('                ') or line=='            )\n' else line for line in helper.splitlines(keepends=True))
helper=helper.replace('self.config','config')
s=s[:start]+'            source = create_snapshot_source(self.config)\n'+s[end:]
s+=helper
p.write_text(s,encoding='utf-8')
p=root/'device-runtime/src/asl_device/adapters/stm_serial.py'
s=p.read_text(encoding='utf-8')
s=s.replace('        down_active = False\n\n        try:', '        down_active = False\n        framer = _SerialLineFramer()\n\n        try:',1)
s=s.replace('                    connection_epoch += 1\n                    event_counter = 0', '                    framer = _SerialLineFramer()\n                    connection_epoch += 1\n                    event_counter = 0',1)
s=s.replace('                    if raw:\n                        line = raw.decode("ascii", errors="strict").strip()', '                    for record in framer.feed(raw):\n                        line = record.decode("ascii", errors="strict").strip()',1)
s=s.replace('and action is not InputAction.RELEASED\n', 'and not (control is DeviceControl.DOWN and action is InputAction.RELEASED)\n',1)
s=s.replace('                                    if action is InputAction.RELEASED:\n', '                                    if control is DeviceControl.DOWN and action is InputAction.RELEASED:\n',1)
s+='''\n\nclass _SerialLineFramer:
    """Only complete records reach ACK/dedupe; oversize tails are never packets."""

    def __init__(self) -> None:
        self._line = bytearray()
        self._discarding = False

    def feed(self, raw: bytes):
        for byte in raw:
            if byte == 10:
                record = bytes(self._line)
                self._line.clear()
                discard, self._discarding = self._discarding, False
                if not discard:
                    yield record
            elif not self._discarding:
                if len(self._line) >= 255:
                    self._line.clear()
                    self._discarding = True
                else:
                    self._line.append(byte)
'''
p.write_text(s,encoding='utf-8')
