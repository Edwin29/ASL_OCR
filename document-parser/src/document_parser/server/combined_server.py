"""One process combining `document_parser.datapack.remote_ingest` (image
upload -> OCR/TTS -> datapack) and `document_parser.server.http_server`
(datapack -> live navigation) onto a single Flask app, backed by a single
shared datapacks directory.

Why this exists: with the two servers kept separate, testing end to end
meant uploading an image, waiting for the job, downloading the resulting
zip, extracting it by hand into wherever the *other* server's
`--datapacks-dir` pointed, and only then starting a session -- four manual
steps, three of them just moving the same bytes around. Here, a finished
ingest job writes directly into the same directory `SessionStore` reads
from (see `JobRegistry(datapacks_dir=...)` in remote_ingest.py), so a book
becomes selectable and servable the moment its job status flips to "done"
-- no download/extract step, and no `/jobs/<id>/download` route at all.

This module adds no new logic of its own beyond one listing endpoint
(`GET /datapacks`) -- it only wires together `remote_ingest.register_routes`
and `http_server.register_routes` on one `Flask` app and one `JobRegistry`/
`SessionStore` pair rooted at the same directory. Both of those modules
keep working completely unchanged on their own (`remote_ingest.py` for a
GPU-less teammate who just wants a zip, no hardware; `http_server.py` for
serving an already-populated datapacks directory with no live ingest) --
neither one imports or knows about this module or the other.
`/jobs/<id>/download` still exists here (it comes along with
`remote_ingest.register_routes`) but always answers 409 in this mode -- the
result was never zipped, since it's already sitting where `/datapacks` and
`POST /sessions` read it from directly.

Usage:
    python -m document_parser.server.combined_server \\
        --api-key <shared secret> --datapacks-dir datapacks/ \\
        --piper-model D:/models/piper-korean/ko_KR-kss-medium.onnx \\
        --piper-espeak-data D:/espeak-ng-data

Client flow (see hardware/stm_pi_bridge/test_client.py for the one-command
version of this):
    POST /jobs                    multipart: book_id, images=@p1.png ...
        -> 202 {"job_id": "...", "status": "queued"}
    GET  /jobs/<job_id>           -> {"status": "queued"|"running"|"done"|"error", ...}
    GET  /datapacks                -> {"book_ids": [...], "books": [{"book_id","title","title_audio_ref"}, ...]}
                                       -- includes book_id once its job is "done"; title_audio_ref is an
                                          absolute path (same convention as a command response's audio_ref),
                                          null only if that book predates the title_audio manifest field
    POST /sessions                {"session_id": "...", "book_id": "...", "viewport_size": 10}
        -> 201 {"state": {...}, "braille_frame": {...}, "audio": {...}|null}
    POST /sessions/<session_id>/command   {"button": "UP", "action": "SHORT"}
        -> same shape, after handling that one button press
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from document_parser.datapack.remote_ingest import JobRegistry
from document_parser.datapack.remote_ingest import register_routes as register_ingest_routes
from document_parser.server.http_server import register_routes as register_session_routes
from document_parser.server.store import SessionStore


def create_app(registry: JobRegistry, store: SessionStore, api_key: str):
    """Flask app factory. Flask is imported here, not at module level, so
    importing this module (e.g. from a test) never requires the
    `remote-ingest` extra (Flask) to be installed unless actually used."""
    from flask import Flask, abort, jsonify, request

    app = Flask(__name__)
    register_ingest_routes(app, registry, api_key)  # /health, /jobs, /jobs/<id>, /jobs/<id>/download
    register_session_routes(app, store, api_key)  # /sessions, /sessions/<id>, /sessions/<id>/command

    def _book_summary(book_id: str) -> dict:
        manifest_path = store.datapacks_dir / book_id / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            # A directory under datapacks_dir with no valid manifest.json --
            # not a real ingest-produced book (build_datapack always writes
            # one), but the listing itself shouldn't break because of it.
            return {"book_id": book_id, "title": book_id, "title_audio_ref": None}
        title_audio = manifest.get("title_audio")
        return {
            "book_id": book_id,
            "title": manifest.get("title", book_id),
            "title_audio_ref": str((store.datapacks_dir / book_id / title_audio).resolve()) if title_audio else None,
        }

    @app.get("/datapacks")
    def list_datapacks():
        if request.headers.get("X-API-Key") != api_key:
            abort(401, description="missing or invalid X-API-Key header")
        book_ids = sorted(
            p.name for p in store.datapacks_dir.iterdir()
            if p.is_dir() and p.name != "_system"
        ) if store.datapacks_dir.is_dir() else []
        # `books` carries title/title_audio (from manifest.json) alongside
        # each book_id, for a book-selection UI (hardware/stm_pi_bridge/
        # device_flow.py) to browse and speak book names without loading a
        # full session per candidate. `book_ids` is kept too, unchanged, so
        # any existing caller reading only that key is unaffected.
        books = [_book_summary(book_id) for book_id in book_ids]
        return jsonify({"book_ids": book_ids, "books": books})

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="0.0.0.0", help="Bind address. 0.0.0.0 = reachable from the LAN, not just this machine.")
    parser.add_argument("--port", type=int, default=8420, help="Same default as remote_ingest.py -- this replaces it as the one address a test PC talks to.")
    parser.add_argument("--api-key", required=True, help="Shared secret clients must send as the X-API-Key header.")
    parser.add_argument("--datapacks-dir", type=Path, required=True, help="Shared directory: ingest jobs write here, and sessions are served from here.")
    parser.add_argument("--jobs-dir", type=Path, default=Path("remote_ingest_jobs"), help="Scratch space for staging uploaded images before OCR -- not where finished datapacks end up.")
    parser.add_argument("--model-home", default=None, help="PaddleOCR-VL model_home; see docs/gpu-inference-setup.md.")
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--piper-model", required=True)
    parser.add_argument("--piper-espeak-data", required=True)
    parser.add_argument("--piper-use-cuda", action="store_true")
    args = parser.parse_args(argv)

    from document_parser.accessibility.adapters.tts_engine import load_piper_voice
    from document_parser.datapack.ingest import make_piper_synthesize_fn
    from document_parser.ocr.paddleocr_vl_adapter import PaddleOcrVlAdapter

    print("loading Piper voice", flush=True)
    voice = load_piper_voice(args.piper_model, args.piper_espeak_data, use_cuda=args.piper_use_cuda)
    synthesize = make_piper_synthesize_fn(voice)

    adapter = PaddleOcrVlAdapter(
        model_home=Path(args.model_home) if args.model_home else None,
        device=args.device,
    )

    tts_manifest = {
        "engine_id": "piper",
        "voice": Path(args.piper_model).stem,
        "use_cuda": args.piper_use_cuda,
    }

    args.jobs_dir.mkdir(parents=True, exist_ok=True)
    args.datapacks_dir.mkdir(parents=True, exist_ok=True)
    registry = JobRegistry(
        adapter=adapter, synthesize=synthesize, tts_manifest=tts_manifest,
        jobs_root=args.jobs_dir, datapacks_dir=args.datapacks_dir,
    )
    store = SessionStore(args.datapacks_dir)
    app = create_app(registry, store, api_key=args.api_key)

    print(f"combined server: ingest+sessions, datapacks at {args.datapacks_dir}, on {args.host}:{args.port}", flush=True)
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
