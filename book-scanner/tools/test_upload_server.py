"""Minimal local test server: receives one photo over HTTP and saves it.

Not production code -- this exists purely so a phone/PC on another network
can send a test photo to this machine (via a cloudflared quick tunnel) for
manual inspection, without standing up the full remote_ingest/combined_server
job-queue machinery. Perspective correction and OCR happen as separate,
manual follow-up steps after a file lands here.

Usage:
    python tools/test_upload_server.py --port 8500 --save-dir incoming

Then:
    curl -F "image=@photo.jpg" http://localhost:8500/upload
"""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from flask import Flask, jsonify, request


def create_app(save_dir: Path) -> Flask:
    app = Flask(__name__)
    save_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/upload")
    def upload():
        if "image" not in request.files:
            return jsonify({"error": "missing 'image' file field"}), 400
        file = request.files["image"]
        if not file.filename:
            return jsonify({"error": "empty filename"}), 400

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = Path(file.filename).suffix or ".jpg"
        dest = save_dir / f"{ts}{suffix}"
        file.save(dest)
        print(f"[upload] saved {dest} ({dest.stat().st_size} bytes)", flush=True)
        return jsonify({"saved_as": str(dest), "bytes": dest.stat().st_size})

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8500)
    parser.add_argument("--save-dir", default="incoming")
    args = parser.parse_args()

    app = create_app(Path(args.save_dir))
    print(f"listening on {args.host}:{args.port}, saving uploads to {Path(args.save_dir).resolve()}")
    app.run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
