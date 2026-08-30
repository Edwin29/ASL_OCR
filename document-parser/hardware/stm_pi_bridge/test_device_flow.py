"""Tests for device_flow.py's selection<->reading orchestration loop,
against fake books/transport/player/remote-session-factory -- no real HTTP
server or physical board involved (same philosophy as test_pi_bridge.py).

Run from the document-parser repo root with document_parser importable,
plus this folder itself on the path for `pi_bridge`/`device_flow`:

    python -m pytest hardware/stm_pi_bridge/test_device_flow.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for `import device_flow`/`pi_bridge`

from device_flow import SelectionScreen, run_device_flow, run_reading_screen, run_selecting_screen
from test_pi_bridge import FakeAudioPlayer, FakeRemoteSession, FakeTransport


def make_books(count=3):
    return [
        {"book_id": f"book{i}", "title": f"제목{i}", "title_audio_ref": f"/datapacks/book{i}/audio/title.wav"}
        for i in range(count)
    ]


class SelectionScreenTests(unittest.TestCase):
    def test_rejects_empty_book_list(self):
        with self.assertRaises(ValueError):
            SelectionScreen([])

    def test_starts_at_index_zero(self):
        screen = SelectionScreen(make_books())
        self.assertEqual(screen.current_book["book_id"], "book0")

    def test_move_clamps_at_both_edges(self):
        screen = SelectionScreen(make_books(3))
        self.assertFalse(screen.move("UP"))  # already at 0
        self.assertTrue(screen.move("DOWN"))
        self.assertTrue(screen.move("DOWN"))
        self.assertEqual(screen.current_book["book_id"], "book2")
        self.assertFalse(screen.move("DOWN"))  # already at the end

    def test_move_by_multiple_steps_clamps_instead_of_overshooting(self):
        screen = SelectionScreen(make_books(3))
        screen.move("DOWN", steps=5)
        self.assertEqual(screen.current_book["book_id"], "book2")


class RunSelectingScreenTests(unittest.TestCase):
    def test_hello_reannounces_current_selection_without_moving(self):
        books = make_books()
        transport = FakeTransport(["HELLO", None])
        player = FakeAudioPlayer()

        result = run_selecting_screen(books, transport, player, log=lambda msg: None)

        self.assertIsNone(result)  # transport closed with nothing confirmed
        self.assertEqual(player.played, ["/datapacks/book0/audio/title.wav", "/datapacks/book0/audio/title.wav"])

    def test_down_short_moves_one_and_speaks_new_title(self):
        books = make_books()
        transport = FakeTransport(["NAV,D,S", None])
        player = FakeAudioPlayer()

        run_selecting_screen(books, transport, player, log=lambda msg: None)

        self.assertEqual(
            player.played,
            ["/datapacks/book0/audio/title.wav", "/datapacks/book1/audio/title.wav"],
        )

    def test_down_long_bursts_several_books(self):
        books = make_books(10)
        transport = FakeTransport(["NAV,D,L", None])
        player = FakeAudioPlayer()

        run_selecting_screen(books, transport, player, log=lambda msg: None)

        self.assertEqual(player.played[-1], "/datapacks/book5/audio/title.wav")

    def test_confirm_short_plays_beep_and_returns_book_id(self):
        books = make_books()
        transport = FakeTransport(["NAV,D,S", "NAV,C,S", None])
        player = FakeAudioPlayer()

        book_id = run_selecting_screen(books, transport, player, log=lambda msg: None)

        self.assertEqual(book_id, "book1")
        self.assertTrue(player.played[-1].endswith("confirm_beep.wav"))

    def test_confirm_long_is_ignored_on_the_selection_screen(self):
        books = make_books()
        transport = FakeTransport(["NAV,C,L", "NAV,C,S", None])
        player = FakeAudioPlayer()

        book_id = run_selecting_screen(books, transport, player, log=lambda msg: None)

        self.assertEqual(book_id, "book0")

    def test_left_right_page_next_are_ignored_not_crashed_on(self):
        books = make_books()
        transport = FakeTransport(["NAV,L,S", "NAV,R,S", "NAV,N,S", "NAV,C,S", None])
        player = FakeAudioPlayer()

        book_id = run_selecting_screen(books, transport, player, log=lambda msg: None)

        self.assertEqual(book_id, "book0")

    def test_transport_closing_before_confirm_returns_none(self):
        books = make_books()
        transport = FakeTransport([None])
        player = FakeAudioPlayer()

        self.assertIsNone(run_selecting_screen(books, transport, player, log=lambda msg: None))

    def test_no_player_configured_does_not_raise(self):
        books = make_books()
        transport = FakeTransport(["NAV,D,S", "NAV,C,S", None])

        book_id = run_selecting_screen(books, transport, None, log=lambda msg: None)

        self.assertEqual(book_id, "book1")


class RunReadingScreenTests(unittest.TestCase):
    def test_speaks_current_item_immediately_on_entry(self):
        remote = FakeRemoteSession()
        transport = FakeTransport([None])

        returned_to_selection = run_reading_screen(remote, transport, None, log=lambda msg: None)

        self.assertFalse(returned_to_selection)
        self.assertEqual(remote.get_current_calls, 1)
        self.assertEqual(len(transport.sent), 1)

    def test_nav_commands_forwarded_normally(self):
        remote = FakeRemoteSession()
        transport = FakeTransport(["NAV,D,S", None])

        run_reading_screen(remote, transport, None, log=lambda msg: None)

        self.assertEqual(remote.send_command_calls, [("DOWN", "SHORT")])

    def test_confirm_short_is_forwarded_to_server_as_a_replay_request(self):
        remote = FakeRemoteSession()
        transport = FakeTransport(["NAV,C,S", None])

        run_reading_screen(remote, transport, None, log=lambda msg: None)

        self.assertEqual(remote.send_command_calls, [("CONFIRM", "SHORT")])

    def test_confirm_long_returns_true_without_forwarding_to_server(self):
        remote = FakeRemoteSession()
        transport = FakeTransport(["NAV,C,L", None])

        returned_to_selection = run_reading_screen(remote, transport, None, log=lambda msg: None)

        self.assertTrue(returned_to_selection)
        self.assertEqual(remote.send_command_calls, [])

    def test_transport_closing_returns_false(self):
        remote = FakeRemoteSession()
        transport = FakeTransport([None])

        self.assertFalse(run_reading_screen(remote, transport, None, log=lambda msg: None))


class RunDeviceFlowTests(unittest.TestCase):
    def test_full_loop_select_then_read_then_confirm_long_back_to_select_then_close(self):
        books = make_books()
        transport = FakeTransport([
            "NAV,C,S",     # select book0
            "NAV,D,S",     # read: move to next node
            "NAV,C,L",     # back to selection
            "NAV,D,S",     # move selection to book1
            "NAV,C,S",     # select book1
            "NAV,D,S",     # read
            None,          # transport closes for good
        ])
        player = FakeAudioPlayer()
        remotes_created: list[str] = []

        def fake_list_books(server, api_key):
            return books

        def fake_remote_factory(server, api_key, session_id, book_id, viewport_size):
            remotes_created.append(book_id)
            return FakeRemoteSession()

        run_device_flow(
            "http://fake", "key", transport, player,
            log=lambda msg: None,
            list_books_fn=fake_list_books,
            remote_session_factory=fake_remote_factory,
        )

        self.assertEqual(remotes_created, ["book0", "book1"])

    def test_no_books_available_raises_instead_of_looping_forever(self):
        transport = FakeTransport(["HELLO", None])

        with self.assertRaises(ValueError):
            run_device_flow(
                "http://fake", "key", transport, None,
                log=lambda msg: None,
                list_books_fn=lambda server, api_key: [],
                remote_session_factory=lambda *a, **k: FakeRemoteSession(),
            )

    def test_closing_transport_during_selection_stops_the_whole_flow(self):
        transport = FakeTransport([None])
        calls = []

        run_device_flow(
            "http://fake", "key", transport, None,
            log=lambda msg: None,
            list_books_fn=lambda server, api_key: (calls.append(1) or make_books()),
            remote_session_factory=lambda *a, **k: FakeRemoteSession(),
        )

        self.assertEqual(len(calls), 1)  # list_books called once, not repeatedly


if __name__ == "__main__":
    unittest.main()
