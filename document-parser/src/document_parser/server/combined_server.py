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

This module adds no ingest/navigation logic of its own beyond one legacy
listing endpoint (`GET /datapacks`) -- it wires together
`remote_ingest.register_routes`, `http_server.register_routes`, and the
persistent S0 `/api/v1` control-plane routes on one `Flask` app rooted at the
same directory. Both legacy modules
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
    GET  /datapacks                -> {"book_ids": [...]}   -- includes book_id once its job is "done"
    POST /sessions                {"session_id": "...", "book_id": "...", "viewport_size": 10}
        -> 201 {"state": {...}, "braille_frame": {...}, "audio": {...}|null}
    POST /sessions/<session_id>/command   {"button": "UP", "action": "SHORT"}
        -> same shape, after handling that one button press
"""

from __future__ import annotations

import argparse
from pathlib import Path

from document_parser.datapack.remote_ingest import JobRegistry
from document_parser.datapack.remote_ingest import register_routes as register_ingest_routes
from document_parser.server.http_server import register_routes as register_session_routes
from document_parser.server.store import SessionStore


def create_app(
    registry: JobRegistry,
    store: SessionStore,
    api_key: str,
    control_plane=None,
    s1_pipeline=None,
    presence_service=None,
):
    """Flask app factory. Flask is imported here, not at module level, so
    importing this module (e.g. from a test) never requires the
    `remote-ingest` extra (Flask) to be installed unless actually used."""
    from flask import Flask, abort, jsonify, request

    app = Flask(__name__)
    register_ingest_routes(app, registry, api_key)  # /health, /jobs, /jobs/<id>, /jobs/<id>/download
    register_session_routes(app, store, api_key)  # /sessions, /sessions/<id>, /sessions/<id>/command
    if control_plane is not None:
        from document_parser.server.s0_http import register_routes as register_s0_routes

        register_s0_routes(app, control_plane, api_key, s1_pipeline, presence_service)

    @app.get("/datapacks")
    def list_datapacks():
        if request.headers.get("X-API-Key") != api_key:
            abort(401, description="missing or invalid X-API-Key header")
        book_ids = sorted(
            p.name for p in store.datapacks_dir.iterdir()
            if p.is_dir() and p.name != "_system"
        ) if store.datapacks_dir.is_dir() else []
        return jsonify({"book_ids": book_ids})

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="0.0.0.0", help="Bind address. 0.0.0.0 = reachable from the LAN, not just this machine.")
    parser.add_argument("--port", type=int, default=8420, help="Same default as remote_ingest.py -- this replaces it as the one address a test PC talks to.")
    parser.add_argument("--api-key", required=True, help="Shared secret clients must send as the X-API-Key header.")
    parser.add_argument("--datapacks-dir", type=Path, required=True, help="Shared directory: ingest jobs write here, and sessions are served from here.")
    parser.add_argument("--jobs-dir", type=Path, default=Path("remote_ingest_jobs"), help="Scratch space for staging uploaded images before OCR -- not where finished datapacks end up.")
    parser.add_argument("--state-db", type=Path, default=None, help="Server S0 SQLite path. Defaults to DATAPACKS_DIR/_server/state.sqlite3.")
    parser.add_argument("--presence-heartbeat-seconds", type=int, default=15)
    parser.add_argument("--presence-stale-seconds", type=int, default=45)
    parser.add_argument("--presence-offline-seconds", type=int, default=120)
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

    raw_adapter = PaddleOcrVlAdapter(
        model_home=Path(args.model_home) if args.model_home else None,
        device=args.device,
    )
    from document_parser.server.s1_parser import SerializedPageAdapter, SerializedSynthesizer

    adapter = SerializedPageAdapter(raw_adapter)
    synthesize = SerializedSynthesizer(synthesize)

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
    from document_parser.server.s0_services import S0ControlPlane
    from document_parser.server.s0_store import S0Store

    state_db = args.state_db or (args.datapacks_dir / "_server" / "state.sqlite3")
    control_plane = S0ControlPlane(S0Store(state_db, args.datapacks_dir))
    bootstrap = control_plane.bootstrap_existing_datapacks()
    from document_parser.server.s1_domain import S1Config
    from document_parser.server.s1_parser import PaddleVlFragmentParser
    from document_parser.server.s1_services import S1Pipeline
    from document_parser.server.s1_workers import S1WorkerRunner
    from document_parser.server.c0_presence import DevicePresenceService

    s1_pipeline = S1Pipeline(
        control_plane.store,
        control_plane,
        S1Config.under(args.datapacks_dir),
        PaddleVlFragmentParser(adapter),
        synthesizer=synthesize,
        tts_manifest=tts_manifest,
    )
    s1_workers = S1WorkerRunner(s1_pipeline)
    s1_workers.start()
    presence_service = DevicePresenceService(
        control_plane.store,
        heartbeat_interval_seconds=args.presence_heartbeat_seconds,
        stale_after_seconds=args.presence_stale_seconds,
        offline_after_seconds=args.presence_offline_seconds,
    )
    app = create_app(
        registry,
        store,
        api_key=args.api_key,
        control_plane=control_plane,
        s1_pipeline=s1_pipeline,
        presence_service=presence_service,
    )

    print(
        f"combined server: ingest+sessions+S0+S1, datapacks at {args.datapacks_dir}, "
        f"catalog entries reconciled={len(bootstrap)}, on {args.host}:{args.port}",
        flush=True,
    )
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
