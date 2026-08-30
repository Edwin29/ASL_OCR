"""Tests for test_client.py's pure orchestration logic (datapack selection,
console-mode turn reporting) -- against a fake remote session, not real
HTTP/upload. The multipart upload/poll helpers and the real hardware path
are thin I/O wrappers not covered here, same rationale as
test_pi_bridge.py's own scope note.

Run from the document-parser repo root with document_parser importable,
plus this folder itself on the path for `pi_bridge`/`test_client`:

    python -m pytest hardware/stm_pi_bridge/test_test_client.py -v
"""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_client import choose_book_id, describe_audio, run_console_test_mode


class FakeRemoteSession:
    def __init__(self, cells=None, audio=None):
        self.node_index = 0
        self.generation = 0
        self._cells = cells if cells is not None else [1, 2, 3]
        self._audio = audio
        self.send_command_calls: list[tuple[str, str]] = []

    def _snapshot(self):
        return {
            "state": {
                "document_id": "doc", "page_index": 0, "node_index": self.node_index,
                "mode": "DOCUMENT", "table_row": None, "table_column": None,
                "braille_offset": 0, "math_span_index": 0, "generation": self.generation,
            },
            "braille_frame": {"cells": self._cells, "has_previous": False, "has_next": False},
            "audio": self._audio,
        }

    def get_current(self):
        return self._snapshot()

    def send_command(self, button, action):
        self.send_command_calls.append((button, action))
        self.generation += 1
        if button == "DOWN":
            self.node_index += 1
        elif button == "UP":
            self.node_index -= 1
        return self._snapshot()


class FakeAudioPlayer:
    def __init__(self, fail_on=None):
        self.played: list[str] = []
        self._fail_on = fail_on or set()

    def play(self, wav_path):
        if wav_path in self._fail_on:
            raise RuntimeError("simulated failure")
        self.played.append(wav_path)


class ChooseBookIdTests(unittest.TestCase):
    def test_picks_by_number(self):
        self.assertEqual(choose_book_id(["a", "b", "c"], preselected=None, input_fn=lambda _: "2", log=lambda _: None), "b")

    def test_raises_on_empty_list(self):
        with self.assertRaises(ValueError):
            choose_book_id([], preselected=None, input_fn=lambda _: "1", log=lambda _: None)

    def test_raises_on_out_of_range_number(self):
        with self.assertRaises(ValueError):
            choose_book_id(["a"], preselected=None, input_fn=lambda _: "5", log=lambda _: None)

    def test_raises_on_non_numeric_input(self):
        with self.assertRaises(ValueError):
            choose_book_id(["a"], preselected=None, input_fn=lambda _: "abc", log=lambda _: None)

    def test_marks_the_preselected_book_id_in_the_printed_menu(self):
        logged = []
        choose_book_id(["a", "b"], preselected="b", input_fn=lambda _: "2", log=logged.append)
        self.assertTrue(any("방금 생성됨" in line and "b" in line for line in logged))


class DescribeAudioTests(unittest.TestCase):
    def test_none_is_silent_scroll_message(self):
        self.assertIn("무음", describe_audio(None))

    def test_present_audio_shows_text_and_ref(self):
        result = describe_audio({"text": "안녕", "audio_ref": "/x/y.wav", "duration_ms": 100, "sample_rate": 22050})
        self.assertIn("안녕", result)
        self.assertIn("/x/y.wav", result)


class RunConsoleTestModeTests(unittest.TestCase):
    def test_reports_initial_state_then_processes_commands(self):
        remote = FakeRemoteSession()
        stream = io.StringIO("down\nq\n")
        run_console_test_mode(remote, player=None, input_stream=stream)
        self.assertEqual(remote.send_command_calls, [("DOWN", "SHORT")])

    def test_page_turn_commands_are_recognized(self):
        remote = FakeRemoteSession()
        stream = io.StringIO("pn\npp\nq\n")
        run_console_test_mode(remote, player=None, input_stream=stream)
        self.assertEqual(remote.send_command_calls, [("PAGE_NEXT", "SHORT"), ("PAGE_PREVIOUS", "SHORT")])

    def test_unknown_command_is_reported_not_crashed_on(self):
        remote = FakeRemoteSession()
        stream = io.StringIO("garbage\ndown\nq\n")
        run_console_test_mode(remote, player=None, input_stream=stream)  # must not raise
        self.assertEqual(remote.send_command_calls, [("DOWN", "SHORT")])

    def test_audio_is_triggered_when_present(self):
        audio = {"text": "hi", "audio_ref": "/a.wav", "duration_ms": 1, "sample_rate": 1}
        remote = FakeRemoteSession(audio=audio)
        player = FakeAudioPlayer()
        stream = io.StringIO("down\nq\n")
        run_console_test_mode(remote, player=player, input_stream=stream)
        self.assertEqual(player.played, ["/a.wav", "/a.wav"])  # initial get_current + one command

    def test_playback_failure_is_logged_not_raised(self):
        audio = {"text": "hi", "audio_ref": "/bad.wav", "duration_ms": 1, "sample_rate": 1}
        remote = FakeRemoteSession(audio=audio)
        player = FakeAudioPlayer(fail_on={"/bad.wav"})
        stream = io.StringIO("q\n")
        run_console_test_mode(remote, player=player, input_stream=stream)  # must not raise

    def test_q_returns_quit(self):
        remote = FakeRemoteSession()
        stream = io.StringIO("q\n")
        self.assertEqual(run_console_test_mode(remote, player=None, input_stream=stream), "quit")

    def test_exhausted_input_stream_returns_quit(self):
        remote = FakeRemoteSession()
        stream = io.StringIO("down\n")  # no q -- just runs out
        self.assertEqual(run_console_test_mode(remote, player=None, input_stream=stream), "quit")

    def test_confirm_long_returns_selecting_without_forwarding_to_server(self):
        remote = FakeRemoteSession()
        stream = io.StringIO("cl\n")
        outcome = run_console_test_mode(remote, player=None, input_stream=stream)
        self.assertEqual(outcome, "selecting")
        self.assertEqual(remote.send_command_calls, [])

    def test_confirm_long_stops_processing_remaining_lines_in_this_call(self):
        # main() is expected to open a *new* remote session and call this
        # function again on "selecting" -- within one call, "cl" must exit
        # immediately, not keep consuming the rest of the stream.
        remote = FakeRemoteSession()
        stream = io.StringIO("cl\ndown\nq\n")
        run_console_test_mode(remote, player=None, input_stream=stream)
        self.assertEqual(remote.send_command_calls, [])

    def test_confirm_short_is_still_forwarded_to_the_server_as_a_replay(self):
        # Unlike CONFIRM LONG, CONFIRM SHORT has no local meaning here --
        # SpeechController handles it server-side (replay current focus).
        remote = FakeRemoteSession()
        stream = io.StringIO("c\nq\n")
        run_console_test_mode(remote, player=None, input_stream=stream)
        self.assertEqual(remote.send_command_calls, [("CONFIRM", "SHORT")])


if __name__ == "__main__":
    unittest.main()
