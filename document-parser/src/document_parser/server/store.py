"""`SessionStore`: keeps loaded `Datapack`s (by book_id) and active
`DatapackSession`s (by session_id) in memory. Whatever transport eventually
gets picked, it will need exactly this -- "give me the session for this
connection/device, creating one against this book if it doesn't exist yet"
-- so it's built and tested once here, transport-agnostic, rather than
re-solved inside each transport experiment.

`session_id` is deliberately just a caller-supplied string. What identifies
a session (a device id, a connection id, a cookie) is itself a transport
decision this store stays out of.
"""

from __future__ import annotations

from pathlib import Path

from document_parser.accessibility import BraillePresenter, NavigationState
from document_parser.datapack.loader import Datapack, load_datapack
from document_parser.server.session import DatapackSession


class SessionStore:
    def __init__(self, datapacks_dir: Path, system_dir: Path | None = None) -> None:
        self._datapacks_dir = Path(datapacks_dir)
        self._system_dir = Path(system_dir) if system_dir is not None else self._datapacks_dir / "_system"
        self._datapacks: dict[str, Datapack] = {}
        self._sessions: dict[str, DatapackSession] = {}

    def get_session(self, session_id: str) -> DatapackSession | None:
        return self._sessions.get(session_id)

    def get_or_create_session(
        self,
        session_id: str,
        book_id: str,
        initial_state: NavigationState | None = None,
        braille_presenter: BraillePresenter | None = None,
    ) -> DatapackSession:
        """Returns the existing session for `session_id` if it's already on
        `book_id`; otherwise starts a fresh one (e.g. the user picked a
        different book, or this is a brand new session_id). Switching books
        mid-session intentionally replaces the session rather than mutating
        it -- a session's `NavigationState.document_id` must always match
        the document it's actually driving.

        `braille_presenter` lets a caller override the default 20-cell
        viewport (`BraillePresenter.DEFAULT_VIEWPORT_SIZE`) -- required for
        any real physical display, which has a fixed cell count of its own
        (e.g. a 10-cell board) that the server has no way to know about
        unless told. Only takes effect when this call actually creates a
        new session; an existing session keeps whatever presenter it was
        built with."""
        existing = self._sessions.get(session_id)
        if existing is not None and existing.datapack.book_id == book_id:
            return existing
        datapack = self._load_datapack_cached(book_id)
        session = DatapackSession(datapack, initial_state=initial_state, braille_presenter=braille_presenter)
        self._sessions[session_id] = session
        return session

    def drop_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _load_datapack_cached(self, book_id: str) -> Datapack:
        cached = self._datapacks.get(book_id)
        if cached is not None:
            return cached
        datapack = load_datapack(self._datapacks_dir / book_id, self._system_dir)
        self._datapacks[book_id] = datapack
        return datapack
