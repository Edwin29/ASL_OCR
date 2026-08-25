"""Manual test driver for session/loop.py -- runs the actual capture->
detect->judge->guide/transmit loop against either a PC webcam or a fixed
sequence of image files, printing every event as it happens.

Usage (webcam, dry-run -- prints instead of transmitting):
    python tools/run_session_cli.py --webcam --out-dir session_out

Usage (image sequence, e.g. simulating a repeated-capture session by hand):
    python tools/run_session_cli.py --images bg.jpg f1.jpg f2.jpg ... --out-dir session_out

Add --server URL --api-key KEY --book-id ID to actually transmit to a
running document-parser remote_ingest server instead of dry-running.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from book_scanner.session.capture_source import SequenceCaptureSource, WebcamCaptureSource
from book_scanner.session.loop import GuidanceEvent, PageTransmittedEvent, SpreadCompleteEvent, run_session
from book_scanner.transmit.client import upload_page


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--webcam", action="store_true")
    source_group.add_argument("--images", nargs="+")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--centerline-fraction", type=float, default=0.5)
    parser.add_argument("--server", default=None, help="if set, actually POST to this document-parser remote_ingest server")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--book-id", default="book_scanner_session")
    args = parser.parse_args()

    if args.webcam:
        capture_source = WebcamCaptureSource()
    else:
        capture_source = SequenceCaptureSource([Path(p) for p in args.images])

    if args.server:
        if not args.api_key:
            raise SystemExit("--api-key is required with --server")

        def transmit_fn(path: Path) -> None:
            result = upload_page(args.server, args.api_key, args.book_id, path)
            print(f"  -> uploaded, job: {result}")
    else:
        def transmit_fn(path: Path) -> None:
            print(f"  -> [dry run, no --server given] would transmit {path}")

    from book_scanner.detect.spread import SpreadConfig

    spread_config = SpreadConfig(centerline_fraction=args.centerline_fraction)

    print("starting session -- first frame is registered as the empty background")
    for event in run_session(capture_source, Path(args.out_dir), transmit_fn, spread_config=spread_config):
        if isinstance(event, GuidanceEvent):
            print(f"[guidance] {event.side.value}: {event.reason.value}")
        elif isinstance(event, PageTransmittedEvent):
            print(f"[transmitted] {event.side.value}: {event.corrected_path}")
        elif isinstance(event, SpreadCompleteEvent):
            print("[spread complete] -- watching for next page")

    print("session ended (capture source exhausted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
