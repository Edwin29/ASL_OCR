"""Tests for pi_bridge.py's pure protocol logic (line formatting/parsing,
the HELLO/NAV dispatch loop) against a FakeRemoteSession -- pi_bridge.py
itself holds no session/navigation state anymore (see its module
docstring), so these tests only need to verify it calls the remote
session correctly and formats its JSON responses into the right FRAME
line shape. The *real* session/navigation behavior behind that JSON is
covered by tests/unit/test_server_http.py (against a real fixture-built
datapack), not duplicated here.

What is NOT tested here, because there is no physical STM32 board,
Bluetooth link, or real HTTP server attached to the machine this was
written on: SerialLineTransport and HttpRemoteSession themselves (the
real I/O), and anything on the STM32/main.c side. Run from the
document-parser repo root with document_parser importable, plus this
folder itself on the path for `pi_bridge`:

    python -m pytest hardware/stm_pi_bridge/test_pi_bridge.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for `import pi_bridge`

from pi_bridge import BRAILLE_CELL_COUNT, format_frame_line, parse_nav_line, run_bridge

from document_parser.accessibility import NavigationCommand


class FakeTransport:
    """Queues lines to "receive" in order; records every line "sent". A
    `None` appended to the receive queue simulates the transport closing."""

    def __init__(self, incoming):
        self._incoming = list(incoming)
        self.sent: list[str] = []

    def read_line(self):
        if not self._incoming:
            return None
        return self._incoming.pop(0)

    def write_line(self, line):
        self.sent.append(line)


class FakeRemoteSession:
    """Stands in for HttpRemoteSession -- no real HTTP call, just an
    in-memory node_index that increments on DOWN/decrements on UP, and a
    fixed-size cell list, enough to exercise run_bridge's dispatch logic
    without needing a real server or a real fixture-built datapack."""

    def __init__(self, cells=None, audio=None):
        self.node_index = 0
        self.generation = 0
        self._cells = cells if cells is not None else [1, 2, 3]
        self._audio = audio  # None by default, matching a silent braille-only scroll
        self.get_current_calls = 0
        self.send_command_calls: list[tuple[str, str]] = []

    def _snapshot(self):
        return {
            "state": {
                "page_index": 0, "node_index": self.node_index, "math_span_index": 0,
                "braille_offset": 0, "generation": self.generation,
            },
            "braille_frame": {"cells": self._cells, "total_cell_count": len(self._cells)},
            "audio": self._audio,
        }

    def get_current(self):
        self.get_current_calls += 1
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
    """Stands in for WinsoundAudioPlayer -- records every path it was asked
    to play instead of touching a real sound device."""

    def __init__(self, fail_on: set[str] | None = None):
        self.played: list[str] = []
        self._fail_on = fail_on or set()

    def play(self, wav_path):
        if wav_path in self._fail_on:
            raise RuntimeError(f"simulated playback failure for {wav_path!r}")
        self.played.append(wav_path)


class FormatFrameLineTests(unittest.TestCase):
    def test_pads_short_cell_lists_to_exactly_braille_cell_count(self):
        state = {"page_index": 0, "node_index": 1, "math_span_index": 0, "braille_offset": 0, "generation": 3}
        line = format_frame_line(state, {"cells": [1, 2, 3]})

        fields = line.split(",")
        self.assertEqual(fields[0], "FRAME")
        self.assertEqual(len(fields), 1 + 5 + BRAILLE_CELL_COUNT)  # matches main.c's 5 + BRAILLE_CELL_COUNT exactly
        self.assertEqual(fields[6:], ["1", "2", "3"] + ["0"] * 7)

    def test_truncates_cell_lists_longer_than_braille_cell_count(self):
        # Defensive only -- should never happen once the session was
        # created with viewport_size=10, but format_frame_line must never
        # emit a line main.c's fixed-width parser would reject.
        state = {"page_index": 0, "node_index": 0, "math_span_index": 0, "braille_offset": 0, "generation": 0}
        line = format_frame_line(state, {"cells": list(range(20))})

        fields = line.split(",")
        self.assertEqual(len(fields), 1 + 5 + BRAILLE_CELL_COUNT)

    def test_state_fields_in_expected_order(self):
        state = {"page_index": 2, "node_index": 5, "math_span_index": 1, "braille_offset": 7, "generation": 9}
        line = format_frame_line(state, {"cells": []})

        fields = line.split(",")
        self.assertEqual(fields[1:6], ["2", "5", "1", "7", "9"])


class ParseNavLineTests(unittest.TestCase):
    def test_parses_all_valid_combinations(self):
        expected = {"U": "UP", "D": "DOWN", "L": "LEFT", "R": "RIGHT"}
        for direction, button in expected.items():
            for length, action in (("S", "SHORT"), ("L", "LONG")):
                with self.subTest(direction=direction, length=length):
                    command = parse_nav_line(f"NAV,{direction},{length}")
                    self.assertEqual(command, NavigationCommand(button=button, action=action))

    def test_rejects_wrong_prefix(self):
        self.assertIsNone(parse_nav_line("HELLO"))
        self.assertIsNone(parse_nav_line("FRAME,0,0,0,0,0"))

    def test_rejects_unknown_direction_or_length(self):
        self.assertIsNone(parse_nav_line("NAV,X,S"))
        self.assertIsNone(parse_nav_line("NAV,U,X"))

    def test_rejects_wrong_field_count(self):
        self.assertIsNone(parse_nav_line("NAV,U"))
        self.assertIsNone(parse_nav_line("NAV,U,S,extra"))


class RunBridgeTests(unittest.TestCase):
    def test_hello_fetches_current_state_without_sending_a_command(self):
        remote = FakeRemoteSession()
        transport = FakeTransport(["HELLO", None])

        run_bridge(remote, transport, log=lambda msg: None)

        self.assertEqual(remote.get_current_calls, 1)
        self.assertEqual(remote.send_command_calls, [])
        self.assertEqual(len(transport.sent), 1)
        self.assertTrue(transport.sent[0].startswith("FRAME,"))

    def test_nav_line_sends_command_and_replies_with_new_frame(self):
        remote = FakeRemoteSession()
        transport = FakeTransport(["NAV,D,S", None])

        run_bridge(remote, transport, log=lambda msg: None)

        self.assertEqual(remote.send_command_calls, [("DOWN", "SHORT")])
        fields = transport.sent[0].split(",")
        self.assertEqual(int(fields[2]), 1)  # node_index advanced by one DOWN SHORT

    def test_long_press_is_forwarded_with_the_right_action(self):
        remote = FakeRemoteSession()
        transport = FakeTransport(["NAV,R,L", None])

        run_bridge(remote, transport, log=lambda msg: None)

        self.assertEqual(remote.send_command_calls, [("RIGHT", "LONG")])

    def test_every_frame_line_has_exactly_braille_cell_count_cells(self):
        remote = FakeRemoteSession(cells=[1, 2])  # shorter than BRAILLE_CELL_COUNT -- must still pad to 10
        transport = FakeTransport(["NAV,D,S", "NAV,U,S", "HELLO", None])

        run_bridge(remote, transport, log=lambda msg: None)

        for line in transport.sent:
            fields = line.split(",")
            self.assertEqual(len(fields), 1 + 5 + BRAILLE_CELL_COUNT, line)

    def test_unrecognized_line_is_ignored_not_crashed_on(self):
        remote = FakeRemoteSession()
        transport = FakeTransport(["GARBAGE", "", "NAV,D,S", None])

        run_bridge(remote, transport, log=lambda msg: None)  # must not raise

        self.assertEqual(len(transport.sent), 1)  # only the valid NAV line got a reply


class AudioTriggerTests(unittest.TestCase):
    """Q2 solution: whatever audio the server's response says corresponds to
    this exact braille frame is triggered from that same response, right
    alongside the FRAME line -- never from a separate/later lookup."""

    def test_triggers_playback_from_the_same_response_as_the_frame_line(self):
        audio = {"text": "문제 1", "audio_ref": "/datapacks/book/audio/p1.wav", "duration_ms": 900, "sample_rate": 22050}
        remote = FakeRemoteSession(audio=audio)
        transport = FakeTransport(["NAV,D,S", None])
        player = FakeAudioPlayer()

        run_bridge(remote, transport, log=lambda msg: None, player=player)

        self.assertEqual(len(transport.sent), 1)
        self.assertEqual(player.played, ["/datapacks/book/audio/p1.wav"])

    def test_silent_scroll_response_triggers_no_playback(self):
        remote = FakeRemoteSession(audio=None)  # e.g. a within-span braille window scroll
        transport = FakeTransport(["NAV,R,S", None])
        player = FakeAudioPlayer()

        run_bridge(remote, transport, log=lambda msg: None, player=player)

        self.assertEqual(player.played, [])
        self.assertEqual(len(transport.sent), 1)  # the FRAME line still went out

    def test_hello_also_triggers_audio_for_the_current_state(self):
        audio = {"text": "문제 1", "audio_ref": "/datapacks/book/audio/p1.wav", "duration_ms": 900, "sample_rate": 22050}
        remote = FakeRemoteSession(audio=audio)
        transport = FakeTransport(["HELLO", None])
        player = FakeAudioPlayer()

        run_bridge(remote, transport, log=lambda msg: None, player=player)

        self.assertEqual(player.played, ["/datapacks/book/audio/p1.wav"])

    def test_no_player_configured_skips_playback_without_error(self):
        audio = {"text": "문제 1", "audio_ref": "/datapacks/book/audio/p1.wav", "duration_ms": 900, "sample_rate": 22050}
        remote = FakeRemoteSession(audio=audio)
        transport = FakeTransport(["NAV,D,S", None])

        run_bridge(remote, transport, log=lambda msg: None)  # player defaults to None, must not raise

        self.assertEqual(len(transport.sent), 1)

    def test_playback_failure_is_logged_not_raised_and_frame_line_still_sent(self):
        audio = {"text": "문제 1", "audio_ref": "/bad/path.wav", "duration_ms": 900, "sample_rate": 22050}
        remote = FakeRemoteSession(audio=audio)
        transport = FakeTransport(["NAV,D,S", "NAV,D,S", None])
        player = FakeAudioPlayer(fail_on={"/bad/path.wav"})
        logs = []

        run_bridge(remote, transport, log=logs.append, player=player)

        self.assertEqual(len(transport.sent), 2)  # both FRAME lines still sent despite playback failing
        self.assertTrue(any("playback failed" in msg for msg in logs))


if __name__ == "__main__":
    unittest.main()
