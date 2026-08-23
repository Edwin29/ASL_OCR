"""One-command test entry point for the testing PC: optionally send an
image (or several) -> wait for `document_parser.server.combined_server` to
finish building the datapack -> list what's currently stored on the server
-> pick one -> enter display test mode (real STM board over serial, or a
console-simulated fallback with no hardware attached).

Specifically talks to `document_parser.server.combined_server`, not the
standalone `remote_ingest.py`/`http_server.py` -- this script relies on a
finished ingest job being immediately selectable via `GET /datapacks` and
servable via `POST /sessions` on the *same* server, with no download/
extract step in between (see combined_server.py's module docstring for why
that's now possible).

Reuses this same folder's pi_bridge.py building blocks unchanged
(`HttpRemoteSession`, `SerialLineTransport`, `run_bridge`,
`build_default_audio_player`) for the real-hardware path, and
`accessibility.cli.render_braille_frame` for the console-simulated path --
no protocol/navigation logic is duplicated here, only the upload -> list ->
select orchestration around it. The multipart upload/poll helpers below
mirror `tools/remote_ingest_client.py`'s (not imported from there: that
script is deliberately stdlib-only/zero-install for a teammate machine
without document_parser, whereas this one already needs document_parser
installed for pi_bridge.py's pieces -- same reasoning `_COMMANDS` is
duplicated across accessibility/cli.py and server/cli.py rather than
shared).

Usage:
    # upload a new image, then pick from the list and test on a real board:
    python test_client.py --server https://...trycloudflare.com --api-key <key> \\
        --port COM5 --upload-book-id my_test p001.png

    # skip uploading, just pick from what's already on the server:
    python test_client.py --server https://...trycloudflare.com --api-key <key> --port COM5

    # no --port: console-simulated display, no physical board needed
    python test_client.py --server https://...trycloudflare.com --api-key <key>
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from pi_bridge import (
    BRAILLE_CELL_COUNT,
    AudioPlayer,
    HttpRemoteSession,
    RemoteSession,
    SerialLineTransport,
    build_default_audio_player,
    run_bridge,
)

from document_parser.accessibility.cli import render_braille_frame

def _log(msg: str) -> None:
    # Piping this script's stdout (e.g. through the Bash tool, or `| tee`)
    # otherwise block-buffers -- progress lines then only appear at process
    # exit, all at once and out of order relative to stderr. This script's
    # whole point is showing live progress, so flush every line.
    print(msg, flush=True)


_COMMANDS: dict[str, tuple[str, str]] = {
    "u": ("UP", "SHORT"), "up": ("UP", "SHORT"),
    "d": ("DOWN", "SHORT"), "down": ("DOWN", "SHORT"),
    "l": ("LEFT", "SHORT"), "left": ("LEFT", "SHORT"),
    "r": ("RIGHT", "SHORT"), "right": ("RIGHT", "SHORT"),
    "ul": ("UP", "LONG"),
    "dl": ("DOWN", "LONG"),
    "ll": ("LEFT", "LONG"),
    "rl": ("RIGHT", "LONG"),
    "pn": ("PAGE_NEXT", "SHORT"),
    "pp": ("PAGE_PREVIOUS", "SHORT"),
}


# ---- upload + poll (mirrors tools/remote_ingest_client.py) ----

def _encode_multipart(fields: dict[str, str], images: list[Path]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    for path in images:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        header = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="images"; filename="{path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        parts.append(header + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _request_json(url: str, api_key: str, data: bytes | None = None, content_type: str | None = None) -> dict[str, Any]:
    headers = {"X-API-Key": api_key}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def upload_and_wait(server: str, api_key: str, book_id: str, images: list[Path], log=_log) -> None:
    """Submits an ingest job and blocks until it's done (or raises on
    error) -- once this returns, `book_id` is immediately visible in
    `GET /datapacks` and servable via `POST /sessions`, no further steps."""
    body, content_type = _encode_multipart({"book_id": book_id}, images)
    payload = _request_json(f"{server}/jobs", api_key, data=body, content_type=content_type)
    job_id = payload["job_id"]
    log(f"업로드됨 (작업 번호: {job_id}) -- 처리 대기 중...")

    elapsed = 0.0
    poll_seconds = 5.0
    while True:
        status_payload = _request_json(f"{server}/jobs/{job_id}", api_key)
        status = status_payload["status"]
        if status == "done":
            log(f"완료 ({elapsed:.0f}초)")
            return
        if status == "error":
            raise RuntimeError(f"작업 실패: {status_payload.get('error')}")
        log(f"처리 중... ({elapsed:.0f}초 경과, 상태: {status})")
        time.sleep(poll_seconds)
        elapsed += poll_seconds


def list_datapacks(server: str, api_key: str) -> list[str]:
    return _request_json(f"{server}/datapacks", api_key)["book_ids"]


def choose_book_id(book_ids: list[str], preselected: str | None, input_fn=input, log=_log) -> str:
    """Prints a numbered menu and returns the chosen book_id. Raises
    ValueError if `book_ids` is empty (nothing to test) or the user's input
    doesn't resolve to a valid choice -- callers should treat that as a
    fatal, user-facing error, not retry silently."""
    if not book_ids:
        raise ValueError("서버에 저장된 데이터팩이 없습니다 -- 먼저 이미지를 업로드하세요.")
    log("저장된 데이터팩:")
    for index, book_id in enumerate(book_ids, start=1):
        marker = " (방금 생성됨)" if book_id == preselected else ""
        log(f"  {index}. {book_id}{marker}")
    raw = input_fn("번호 선택: ").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= len(book_ids)):
        raise ValueError(f"잘못된 선택입니다: {raw!r}")
    return book_ids[int(raw) - 1]


# ---- console-simulated display test mode (no physical board needed) ----

def describe_audio(audio: dict[str, Any] | None) -> str:
    if audio is None:
        return "(무음 -- 점자 창만 이동, 새로 재생할 오디오 없음)"
    return f"[AUDIO] {audio['text']}  ({audio['audio_ref']})"


def _report_turn(result: dict[str, Any], player: AudioPlayer | None, log) -> None:
    state = result["state"]
    print(
        f"[state] mode={state['mode']} page={state['page_index']} node={state['node_index']} "
        f"table=({state['table_row']},{state['table_column']}) span={state['math_span_index']} "
        f"offset={state['braille_offset']} gen={state['generation']}"
    )
    print(render_braille_frame(result["braille_frame"]))
    audio = result["audio"]
    print(describe_audio(audio))
    if player is None or audio is None:
        return
    try:
        player.play(audio["audio_ref"])
    except Exception as exc:  # noqa: BLE001 -- same rationale as pi_bridge.py's _emit(): best-effort, never fatal
        log(f"audio playback failed for {audio['audio_ref']!r}: {exc}")


def run_console_test_mode(remote: RemoteSession, player: AudioPlayer | None, input_stream=sys.stdin) -> None:
    """Drives `remote` from the keyboard instead of a real STM board --
    same command vocabulary and turn reporting as `server/cli.py`, adapted
    to the wire-format dicts HttpRemoteSession returns (that CLI drives a
    local DatapackSession directly and sees real NavigationState objects;
    this one only ever sees JSON off the wire)."""
    _report_turn(remote.get_current(), player, print)
    print("명령: up/down/left/right (SHORT), ul/dl/ll/rl (LONG), pn/pp(페이지 넘김), q(종료)")
    for line in input_stream:
        token = line.strip().lower()
        if not token:
            continue
        if token in ("q", "quit", "exit"):
            return
        command = _COMMANDS.get(token)
        if command is None:
            print(f"알 수 없는 명령: {token!r}")
            continue
        button, action = command
        _report_turn(remote.send_command(button, action), player, print)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", required=True, help="document_parser.server.combined_server 주소 (LAN IP 또는 터널 주소)")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--upload-book-id", help="주어지면 먼저 이미지들을 이 이름으로 업로드하고 완료를 기다립니다.")
    parser.add_argument("images", nargs="*", type=Path, help="--upload-book-id와 함께 보낼 이미지 파일들")
    parser.add_argument("--port", help="STM 보드가 연결된 COM 포트(예: COM5). 생략하면 콘솔 시뮬레이션 모드로 진행합니다.")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--session-id", default="stm-bridge")
    parser.add_argument("--no-audio", action="store_true")
    args = parser.parse_args(argv)

    server = args.server.rstrip("/")

    if args.upload_book_id:
        for image in args.images:
            if not image.is_file():
                print(f"파일을 찾을 수 없습니다: {image}", file=sys.stderr)
                return 1
        try:
            upload_and_wait(server, args.api_key, args.upload_book_id, args.images)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as exc:
            print(f"업로드 실패: {exc}", file=sys.stderr)
            return 1
    elif args.images:
        print("이미지 파일이 주어졌지만 --upload-book-id가 없습니다 -- 이름을 정해서 --upload-book-id로 주세요.", file=sys.stderr)
        return 1

    try:
        book_ids = list_datapacks(server, args.api_key)
        book_id = choose_book_id(book_ids, preselected=args.upload_book_id)
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    remote = HttpRemoteSession(server, args.api_key, args.session_id, book_id, viewport_size=BRAILLE_CELL_COUNT)
    player = None if args.no_audio else build_default_audio_player(print)

    if args.port:
        print(f"디스플레이 테스트 모드 시작 (실제 보드: {args.port}, book={book_id!r}, audio={'off' if player is None else 'on'})")
        transport = SerialLineTransport(args.port, baudrate=args.baudrate)
        try:
            run_bridge(remote, transport, player=player)
        finally:
            transport.close()
    else:
        print(f"디스플레이 테스트 모드 시작 (콘솔 시뮬레이션 -- 보드 없음, book={book_id!r}, audio={'off' if player is None else 'on'})")
        run_console_test_mode(remote, player)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
