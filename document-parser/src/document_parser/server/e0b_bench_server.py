"""Deterministic desktop Server origin for remote E0-B hardware acceptance.

This bench server uses the real C0/S0/V4 HTTP routes, SQLite stores, upload
journal, S1 worker, revision publish, and reading APIs.  Only content parsing
and speech synthesis are deterministic fixtures so a remote Laptop can validate
camera/STM/audio and ACK/READY ordering through an HTTPS tunnel.  It is not a
production OCR server and refuses non-loopback bind addresses so that the tunnel
is the only intended ingress.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import struct
from dataclasses import dataclass
from pathlib import Path

from document_parser.server.c0_presence import DevicePresenceService
from document_parser.server.s0_http import create_app
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from document_parser.server.s1_domain import S1Config
from document_parser.server.s1_parser import ParsedFragment
from document_parser.server.s1_services import S1Pipeline
from document_parser.server.s1_workers import S1WorkerRunner
from document_parser.server.v4_domain import V4Config
from document_parser.server.v4_upload import V4UploadService

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class BenchFragmentParser:
    def parse(self, _image_path: Path, page_id: str, _document_id: str) -> ParsedFragment:
        item_id = f"{page_id}-bench-item"
        page = {"page_id": page_id, "nodes": [], "reading_order": []}
        accessible = {
            "page_id": page_id,
            "focus_items": [
                {
                    "id": item_id,
                    "kind": "TEXT",
                    "page_id": page_id,
                    "reading_index": 0,
                    "confidence": 1.0,
                    "issues": [],
                    "source_node_ids": [item_id],
                    "problem_id": None,
                    "spans": [{"kind": "TEXT", "text": f"remote bench content {page_id}"}],
                }
            ],
        }
        return ParsedFragment(
            page,
            accessible,
            {"engine": "e0b-deterministic-bench"},
            {"schema_valid": True, "bench_only": True},
        )


class BenchSynthesizer:
    """Deterministic audible tone fixture; this is not production TTS."""

    sample_rate = 16_000
    duration_ms = 500
    amplitude = 6_000

    def __call__(self, text: str) -> tuple[bytes, int, int]:
        frequency = self.frequency_for(text)
        frame_count = self.sample_rate * self.duration_ms // 1000
        frames = bytearray()
        for index in range(frame_count):
            envelope = min(1.0, index / 320, (frame_count - index - 1) / 320)
            sample = round(
                self.amplitude
                * max(0.0, envelope)
                * math.sin(2.0 * math.pi * frequency * index / self.sample_rate)
            )
            frames.extend(struct.pack("<h", sample))
        return bytes(frames), self.sample_rate, 1

    @staticmethod
    def frequency_for(text: str) -> int:
        if "낮은" in text or "low" in text.lower():
            return 440
        if "높은" in text or "high" in text.lower():
            return 880
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return 440 + (int.from_bytes(digest[:2], "big") % 9) * 55


@dataclass(frozen=True, slots=True)
class E0BBenchComposition:
    app: object
    store: S0Store
    control_plane: S0ControlPlane
    pipeline: S1Pipeline
    worker: S1WorkerRunner
    v4_service: V4UploadService


def build_e0b_bench_server(state_root: str | Path, api_key: str) -> E0BBenchComposition:
    if not isinstance(api_key, str) or not api_key or len(api_key) > 4096 or "\n" in api_key or "\r" in api_key:
        raise ValueError("bench API key is invalid")
    root = Path(state_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    datapacks_root = root / "datapacks"
    store = S0Store(root / "server.sqlite3", datapacks_root)
    control_plane = S0ControlPlane(store)
    pipeline = S1Pipeline(
        store,
        control_plane,
        S1Config.under(datapacks_root),
        BenchFragmentParser(),
        synthesizer=BenchSynthesizer(),
        tts_manifest={"engine_id": "e0b-deterministic-bench", "bench_only": True},
    )
    v4_service = V4UploadService(store, pipeline, V4Config.from_s1(pipeline.config))
    v4_service.recover()
    presence = DevicePresenceService(store)
    app = create_app(
        control_plane,
        api_key,
        pipeline,
        presence_service=presence,
        v4_service=v4_service,
    )
    worker = S1WorkerRunner(pipeline, idle_seconds=0.05)
    return E0BBenchComposition(app, store, control_plane, pipeline, worker, v4_service)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8421)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--api-key-file", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.host not in _LOOPBACK_HOSTS:
        parser.error("E0-B bench server must bind only to a loopback host")
    try:
        api_key = args.api_key_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        parser.error(f"cannot read API key file: {type(exc).__name__}")
    composition = build_e0b_bench_server(args.state_root, api_key)
    composition.worker.start()
    print(
        f"E0-B desktop bench origin on http://{args.host}:{args.port}; "
        f"state={Path(args.state_root).resolve()}",
        flush=True,
    )
    try:
        composition.app.run(host=args.host, port=args.port, threaded=True)
    finally:
        composition.worker.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
