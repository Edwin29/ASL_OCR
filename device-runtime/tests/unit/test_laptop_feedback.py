from __future__ import annotations

import io

from asl_device.adapters.local_feedback import JsonLineReadingPresenter
from asl_device.adapters.local_feedback import WindowsAudioFeedbackSink
from asl_device.app_config import LaptopAudioConfig
from asl_device.events import FeedbackCode, FeedbackEvent
from asl_device.types import DatapackId, ReadingSessionId, ReadingSnapshot


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
    assert backend.calls[1] == (
        "speak",
        "페이지 전송이 완료되었습니다. 다음 페이지로 넘겨 주세요.",
    )
    assert backend.calls[2][0] == "beep"
    assert backend.calls[3] == ("speak", "데이터팩 저장이 완료되었습니다.")


def test_laptop_feedback_announces_each_screen_with_operating_mode_context() -> None:
    backend = RecordingAudio()
    sink = WindowsAudioFeedbackSink(
        LaptopAudioConfig(jsonl_trace=False),
        backend=backend,
    )

    sink.emit(
        FeedbackEvent(
            FeedbackCode.SCREEN_CHANGED,
            1.0,
            (("screen", "datapack_selection"), ("mode", "capture")),
        )
    )
    sink.emit(
        FeedbackEvent(
            FeedbackCode.SCREEN_CHANGED,
            2.0,
            (("screen", "reading"), ("mode", "reading")),
        )
    )
    sink.close()

    assert backend.calls == [
        ("speak", "캡처 모드 데이터팩 선택 화면입니다."),
        ("speak", "리딩 화면입니다."),
    ]


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


def test_laptop_feedback_speaks_reason_specific_scanner_guidance() -> None:
    backend = RecordingAudio()
    sink = WindowsAudioFeedbackSink(
        LaptopAudioConfig(jsonl_trace=False),
        backend=backend,
    )
    sink.emit(
        FeedbackEvent(
            FeedbackCode.SCANNER_GUIDANCE,
            1.0,
            (("guidance_code", "content_occluded"),),
        )
    )
    sink.close()

    assert backend.calls == [("speak", "페이지를 가리는 손이나 물체를 치워 주세요.")]


def _snapshot(*, cells: tuple[int, ...] = (1, 2, 3), generation: int = 1) -> ReadingSnapshot:
    return ReadingSnapshot(
        ReadingSessionId("reading-1"),
        DatapackId("datapack-1"),
        (("page_index", 0), ("node_index", 0), ("generation", generation)),
        braille_cells=cells,
        audio_ref="audio:item-1",
        source_text="x≤1",
        spoken_text="엑스는 1보다 작거나 같다",
    )


def test_jsonline_reading_presenter_emits_changed_server_payload_once() -> None:
    output = io.StringIO()
    presenter = JsonLineReadingPresenter(output)
    initial = _snapshot()

    presenter.present(None)
    presenter.present(initial)
    presenter.present(initial)
    presenter.present(_snapshot(cells=(4, 5), generation=2))

    assert output.getvalue().splitlines() == [
        '{"type":"reading_snapshot","reading_session_id":"reading-1",'
        '"datapack_id":"datapack-1","cursor":{"page_index":0,"node_index":0,'
        '"generation":1},"source_text":"x≤1","spoken_text":"엑스는 1보다 작거나 같다",'
        '"braille_cells":[1,2,3],"audio_ref":"audio:item-1"}',
        '{"type":"reading_snapshot","reading_session_id":"reading-1",'
        '"datapack_id":"datapack-1","cursor":{"page_index":0,"node_index":0,'
        '"generation":2},"source_text":"x≤1","spoken_text":"엑스는 1보다 작거나 같다",'
        '"braille_cells":[4,5],"audio_ref":"audio:item-1"}',
    ]


def test_jsonline_reading_presenter_failure_is_best_effort() -> None:
    class BrokenStream:
        def write(self, _text: str) -> None:
            raise OSError("closed")

        def flush(self) -> None:
            raise AssertionError("flush must not follow a failed write")

    presenter = JsonLineReadingPresenter(BrokenStream())

    assert presenter.present(_snapshot()) is None
