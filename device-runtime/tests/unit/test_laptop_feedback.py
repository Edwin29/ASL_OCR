from __future__ import annotations

from asl_device.adapters.local_feedback import WindowsAudioFeedbackSink
from asl_device.app_config import LaptopAudioConfig
from asl_device.events import FeedbackCode, FeedbackEvent


class RecordingAudio:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def beep(self, pattern) -> None:
        self.calls.append(("beep", pattern))

    def speak(self, text: str) -> None:
        self.calls.append(("speak", text))


def test_laptop_feedback_renders_ack_and_ready_as_distinct_patterns() -> None:
    backend = RecordingAudio()
    sink = WindowsAudioFeedbackSink(
        LaptopAudioConfig(jsonl_trace=False),
        backend=backend,
    )

    sink.emit(FeedbackEvent(FeedbackCode.SPREAD_SENT, 1.0, (("sequence", 1),)))
    sink.emit(FeedbackEvent(FeedbackCode.DATAPACK_SAVED, 2.0))
    sink.close()

    assert backend.calls[0][0] == "beep"
    assert backend.calls[1][0] == "beep"
    assert backend.calls[2] == ("speak", "데이터팩 저장이 완료되었습니다.")


def test_laptop_feedback_speaks_only_the_catalog_title_detail() -> None:
    backend = RecordingAudio()
    sink = WindowsAudioFeedbackSink(
        LaptopAudioConfig(jsonl_trace=False),
        backend=backend,
    )
    sink.emit(
        FeedbackEvent(
            FeedbackCode.SPEAK_CATALOG_TITLE,
            1.0,
            (("title", "수학 교재"), ("datapack_secret", "must-not-speak")),
        )
    )
    sink.close()

    assert backend.calls == [("speak", "수학 교재")]
