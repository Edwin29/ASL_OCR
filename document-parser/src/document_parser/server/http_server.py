"""HTTP serving endpoint wrapping `handle_wire_command()`/`SessionStore` --
this is the actual Scenario B transport docs/datapack-schema.md left
undecided ("트랜스포트 프로토콜 미정"). Picked HTTP because a host device
running `hardware/stm_pi_bridge/pi_bridge.py` needs to reach a datapack
that lives only on this server -- with no local storage of its own, every
button press has to be a live round trip, not a local file read.

Unrelated to `document_parser.datapack.remote_ingest` (that HTTP server is
for image upload -> OCR/TTS; this one is for already-ingested datapacks ->
live navigation responses). Both can run side by side on the same
machine, on different ports.

Usage:
    python -m document_parser.server.http_server \\
        --api-key <shared secret> --datapacks-dir datapacks/

Client flow:
    POST /sessions               {"session_id": "...", "book_id": "...", "viewport_size": 10}
        -> 201 {"state": {...}, "braille_frame": {...}, "audio": {...}|null}
    GET  /sessions/<session_id>  -> same shape, current state, no navigation
    POST /sessions/<session_id>/command   {"button": "UP", "action": "SHORT"}
        -> same shape, after handling that one button press

`viewport_size` matters: it must match whatever physical display (if any)
is on the other end -- e.g. the STM32 board in hardware/stm_pi_bridge has
exactly 10 cells, while BraillePresenter's own default is 20. Passed
through to `SessionStore.get_or_create_session(braille_presenter=...)`
only on session creation; an existing session keeps whatever it was built
with.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from document_parser.accessibility import BraillePresenter
from document_parser.server.store import SessionStore
from document_parser.server.wire import command_from_wire, result_to_wire


def create_app(store: SessionStore, api_key: str):
    """Flask app factory. Flask is imported here, not at module level, so
    importing this module for `create_app`/tests never requires the
    `remote-ingest` extra (Flask) to be installed unless actually used."""
    from flask import Flask, abort, jsonify, request

    app = Flask(__name__)

    def _check_api_key() -> None:
        if request.headers.get("X-API-Key") != api_key:
            abort(401, description="missing or invalid X-API-Key header")

    def _snapshot_wire(session: Any) -> dict[str, Any]:
        """Current state/frame with no navigation applied -- used for
        session creation and GET (the "HELLO" case: resend current state,
        don't advance)."""
        return result_to_wire({"state": session.state, "braille_frame": session.braille_frame, "audio": session.audio})

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/sessions")
    def create_session():
        _check_api_key()
        payload = request.get_json(silent=True) or {}
        session_id = payload.get("session_id")
        book_id = payload.get("book_id")
        if not session_id or not book_id:
            return jsonify({"error": "session_id and book_id are required"}), 400
        viewport_size = payload.get("viewport_size")
        presenter = BraillePresenter(viewport_size=viewport_size) if viewport_size else None
        try:
            session = store.get_or_create_session(session_id, book_id, braille_presenter=presenter)
        except FileNotFoundError:
            return jsonify({"error": f"unknown book_id {book_id!r}"}), 404
        return jsonify(_snapshot_wire(session)), 201

    @app.get("/sessions/<session_id>")
    def get_session(session_id: str):
        _check_api_key()
        session = store.get_session(session_id)
        if session is None:
            return jsonify({"error": "unknown session_id -- call POST /sessions first"}), 404
        return jsonify(_snapshot_wire(session))

    @app.post("/sessions/<session_id>/command")
    def send_command(session_id: str):
        _check_api_key()
        session = store.get_session(session_id)
        if session is None:
            return jsonify({"error": "unknown session_id -- call POST /sessions first"}), 404
        payload = request.get_json(silent=True) or {}
        try:
            command = command_from_wire(payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        result = session.handle_button(command)
        return jsonify(result_to_wire(result))

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="0.0.0.0", help="Bind address. 0.0.0.0 = reachable from the LAN, not just this machine.")
    parser.add_argument("--port", type=int, default=8421, help="Different from remote_ingest's default (8420) so both can run at once.")
    parser.add_argument("--api-key", required=True, help="Shared secret the host device must send as the X-API-Key header.")
    parser.add_argument("--datapacks-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    store = SessionStore(args.datapacks_dir)
    app = create_app(store, api_key=args.api_key)
    print(f"serving datapacks from {args.datapacks_dir} on {args.host}:{args.port}", flush=True)
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
