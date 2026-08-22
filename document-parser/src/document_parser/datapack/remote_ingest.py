"""Internal team-testing tool: lets a GPU-less teammate send page images to
this machine over HTTP and get back a finished datapack. This is UNRELATED
to `document_parser.server` (that package is the future hardware-facing
Scenario B serving layer, still pending a transport-protocol decision) --
this exists purely to unblock teammates from testing against real OCR/TTS
output while that decision is made. Not part of the product's own
transport; do not wire hardware to this.

Requires the `remote-ingest` extra (`pip install document-parser[remote-ingest]`,
i.e. just `flask`) on top of the GPU venv described in
docs/gpu-inference-setup.md.

Usage (on the GPU machine):
    python -m document_parser.datapack.remote_ingest \\
        --api-key <a shared secret you make up> \\
        --piper-model D:/models/piper-korean/ko_KR-kss-medium.onnx \\
        --piper-espeak-data D:/espeak-ng-data

A teammate then:
    curl -X POST http://<this-machine-LAN-IP>:8420/jobs \\
        -H "X-API-Key: <the same secret>" \\
        -F "book_id=test_book" -F "images=@p001.png" -F "images=@p002.png"
    # -> {"job_id": "...", "status": "queued"}
    curl http://<LAN-IP>:8420/jobs/<job_id> -H "X-API-Key: ..."
    # -> {"status": "running" | "done" | "error", ...}
    curl -OJ http://<LAN-IP>:8420/jobs/<job_id>/download -H "X-API-Key: ..."
    # -> a .zip containing datapacks/{book_id}/ and datapacks/_system/,
    #    ready to point document_parser.server.cli or SessionStore at.
"""

from __future__ import annotations

import argparse
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Any, Callable

from document_parser.datapack.ingest import SynthesizeFn, build_datapack
from document_parser.serialization import build_document_ir_from_vl


def run_ingest_job(
    book_id: str,
    image_paths: list[Path],
    output_dir: Path,
    system_dir: Path,
    adapter: Any,
    synthesize: SynthesizeFn,
    tts_manifest: dict[str, Any],
    log_fn: Callable[[str], None] = lambda msg: None,
) -> Path:
    """OCR + full datapack build for one remote-ingest job. Thin wrapper
    around `build_document_ir_from_vl` + `build_datapack` -- the same two
    calls `document_parser.datapack.ingest.main()` makes for the local CLI
    path -- so this module adds no new ingest behavior, only a network
    front end to trigger the existing one. Kept as a standalone function
    (not a method) so it's testable with fakes without any Flask/threading
    involved, matching this project's usual split between core logic and
    its I/O wrapper.
    """
    log_fn(f"OCR: building document IR for {len(image_paths)} image(s)")
    page_ir = build_document_ir_from_vl(sorted(image_paths), adapter, book_id)
    log_fn("OCR complete")
    return build_datapack(
        book_id=book_id,
        title=book_id,
        page_ir=page_ir,
        synthesize=synthesize,
        tts_manifest=tts_manifest,
        output_dir=output_dir,
        system_dir=system_dir,
        log_fn=log_fn,
    )


def zip_datapack_output(output_dir: Path, zip_path: Path) -> Path:
    """Zip `output_dir` (which holds both `{book_id}/` and `_system/` --
    `load_datapack`/`server.cli` need both) into one downloadable file."""
    archive_base = str(zip_path.with_suffix(""))
    created = shutil.make_archive(archive_base, "zip", root_dir=output_dir)
    return Path(created)


@dataclass
class Job:
    job_id: str
    book_id: str
    status: str = "queued"  # queued -> running -> done | error
    error: str | None = None
    zip_path: Path | None = None


class JobRegistry:
    """In-memory job store backed by a single background worker thread --
    deliberately not one thread per job. PaddleOCR-VL's GPU reader isn't
    meant to be hit with concurrent `.predict()` calls, and this tool is
    for a handful of teammates testing casually, not real concurrent
    throughput, so jobs simply queue and run one at a time.
    """

    def __init__(
        self,
        adapter: Any,
        synthesize: SynthesizeFn,
        tts_manifest: dict[str, Any],
        jobs_root: Path,
    ) -> None:
        self.jobs_root = jobs_root
        self._adapter = adapter
        self._synthesize = synthesize
        self._tts_manifest = tts_manifest
        self._jobs: dict[str, Job] = {}
        self._image_paths: dict[str, list[Path]] = {}
        self._lock = threading.Lock()
        self._queue: Queue[str] = Queue()
        threading.Thread(target=self._worker_loop, daemon=True).start()

    def submit(self, job_id: str, book_id: str, image_paths: list[Path]) -> None:
        with self._lock:
            self._jobs[job_id] = Job(job_id=job_id, book_id=book_id)
            self._image_paths[job_id] = image_paths
        self._queue.put(job_id)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            self._run(job_id)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            image_paths = self._image_paths[job_id]
        job_dir = self.jobs_root / job_id
        output_dir = job_dir / "datapacks"
        system_dir = output_dir / "_system"
        try:
            run_ingest_job(
                book_id=job.book_id,
                image_paths=image_paths,
                output_dir=output_dir,
                system_dir=system_dir,
                adapter=self._adapter,
                synthesize=self._synthesize,
                tts_manifest=self._tts_manifest,
                log_fn=lambda msg: print(f"[{job_id}] {msg}", flush=True),
            )
            zip_path = zip_datapack_output(output_dir, job_dir / f"{job.book_id}.zip")
            with self._lock:
                job.status = "done"
                job.zip_path = zip_path
        except Exception as exc:  # noqa: BLE001 -- report to the client, never crash the worker loop
            with self._lock:
                job.status = "error"
                job.error = str(exc)


def create_app(registry: JobRegistry, api_key: str):
    """Flask app factory. Flask is imported here, not at module level, so
    importing this module for `run_ingest_job`/`JobRegistry` (e.g. from a
    test) never requires the `remote-ingest` extra to be installed."""
    from flask import Flask, abort, jsonify, request, send_file

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB: generous for a page-image batch, not unbounded

    def _check_api_key() -> None:
        if request.headers.get("X-API-Key") != api_key:
            abort(401, description="missing or invalid X-API-Key header")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/jobs")
    def create_job():
        _check_api_key()
        book_id = request.form.get("book_id")
        if not book_id:
            return jsonify({"error": "book_id is required"}), 400
        uploads = request.files.getlist("images")
        if not uploads:
            return jsonify({"error": "at least one image file ('images') is required"}), 400

        job_id = uuid.uuid4().hex[:12]
        image_dir = registry.jobs_root / job_id / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_paths = []
        for upload in uploads:
            # .name strips any directory components a client might send --
            # never trust an uploaded filename as a path.
            path = image_dir / Path(upload.filename or "page.png").name
            upload.save(path)
            image_paths.append(path)

        registry.submit(job_id, book_id, image_paths)
        return jsonify({"job_id": job_id, "status": "queued"}), 202

    @app.get("/jobs/<job_id>")
    def job_status(job_id: str):
        _check_api_key()
        job = registry.get(job_id)
        if job is None:
            return jsonify({"error": "unknown job_id"}), 404
        return jsonify({"job_id": job.job_id, "book_id": job.book_id, "status": job.status, "error": job.error})

    @app.get("/jobs/<job_id>/download")
    def job_download(job_id: str):
        _check_api_key()
        job = registry.get(job_id)
        if job is None:
            return jsonify({"error": "unknown job_id"}), 404
        if job.status != "done":
            return jsonify({"error": f"job status is {job.status!r}, not done yet"}), 409
        return send_file(job.zip_path, as_attachment=True, download_name=f"{job.book_id}.zip")

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="0.0.0.0", help="Bind address. 0.0.0.0 = reachable from the LAN, not just this machine -- make sure that's intended.")
    parser.add_argument("--port", type=int, default=8420)
    parser.add_argument("--api-key", required=True, help="Shared secret teammates must send as the X-API-Key header. Make one up; there is no other auth.")
    parser.add_argument("--jobs-dir", type=Path, default=Path("remote_ingest_jobs"))
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
    registry = JobRegistry(adapter=adapter, synthesize=synthesize, tts_manifest=tts_manifest, jobs_root=args.jobs_dir)
    app = create_app(registry, api_key=args.api_key)

    print(f"remote ingest server listening on {args.host}:{args.port} (jobs run one at a time)", flush=True)
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
