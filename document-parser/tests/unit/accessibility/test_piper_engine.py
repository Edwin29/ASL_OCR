import os
import unittest
from pathlib import Path

from document_parser.accessibility.adapters.tts_engine import PiperTtsEngineAdapter

MODEL_PATH = os.environ.get("PIPER_KOREAN_MODEL_PATH", "")
ESPEAK_DATA_DIR = os.environ.get("PIPER_ESPEAK_DATA_DIR", "")

_MODEL_AVAILABLE = bool(MODEL_PATH) and bool(ESPEAK_DATA_DIR) and Path(MODEL_PATH).is_file() and Path(ESPEAK_DATA_DIR).is_dir()


class PiperAdapterAsciiPathGuardTests(unittest.TestCase):
    """Regression test for a verified-real bug: the Windows piper-tts wheel's
    bundled espeak-ng crashes the whole process (not a catchable Python
    exception) when its data directory path contains non-ASCII characters --
    which a Korean Windows username guarantees by default. This check runs
    unconditionally: it must reject the bad path before ever importing
    `piper`, so it needs neither the optional dependency nor a model file.
    """

    def test_rejects_non_ascii_espeak_data_dir_before_touching_piper(self):
        with self.assertRaises(ValueError):
            PiperTtsEngineAdapter("model.onnx", espeak_data_dir="C:/Users/왕원철/espeak-ng-data")


@unittest.skipUnless(
    _MODEL_AVAILABLE,
    "Set PIPER_KOREAN_MODEL_PATH (to ko_KR-kss-medium.onnx) and PIPER_ESPEAK_DATA_DIR "
    "(an ASCII-only copy of piper's espeak-ng-data) to run the real Piper integration test.",
)
class PiperKoreanVoiceIntegrationTests(unittest.TestCase):
    """Real, non-mocked verification that the official rhasspy/piper-voices
    Korean model (ko/ko_KR/kss/medium/ko_KR-kss-medium.onnx) actually loads
    and synthesizes through the standard Python piper-tts package -- this is
    the risk gate the Phase 2 plan required before building anything else on
    top of Piper."""

    def test_loads_and_synthesizes_korean_audio(self):
        from piper.voice import PiperVoice

        voice = PiperVoice.load(MODEL_PATH, espeak_data_dir=ESPEAK_DATA_DIR)
        chunks = list(voice.synthesize("안녕하세요. 다음 조건을 만족시키는 두 양수."))
        self.assertTrue(chunks)
        total_bytes = sum(len(chunk.audio_int16_bytes) for chunk in chunks)
        self.assertGreater(total_bytes, 0)

    def test_adapter_loads_with_ascii_espeak_data_dir(self):
        adapter = PiperTtsEngineAdapter(MODEL_PATH, espeak_data_dir=ESPEAK_DATA_DIR)
        self.assertIsNotNone(adapter)


if __name__ == "__main__":
    unittest.main()
