"""팀원용 원격 ingest 클라이언트 -- docs/remote-ingest.md의 2~4단계
(이미지 전송 -> 완료 대기 -> 결과 다운로드/압축 해제)를 한 번에 자동으로
처리합니다. 이 프로젝트의 다른 코드와 무관하게, 파이썬 표준 라이브러리만
써서 동작합니다(pip install 필요 없음) -- 팀원이 이 프로젝트 개발 환경을
따로 갖추지 않아도 이 파일 하나만 있으면 실행할 수 있게 하기 위함입니다.

사용법:
    python remote_ingest_client.py \\
        --server https://무작위이름.trycloudflare.com \\
        --api-key <서버 운영자가 알려준 값> \\
        --book-id 아무이름 \\
        이미지1.png 이미지2.png

완료되면 결과를 압축 해제해서 보여주고, 그걸 눈으로 확인하는 다음 명령어를
알려줍니다(그 명령어는 이 프로젝트 코드가 있는 컴퓨터에서 실행해야 합니다).
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
import zipfile
from pathlib import Path
from typing import Any


def _encode_multipart(fields: dict[str, str], images: list[Path]) -> tuple[bytes, str]:
    """Hand-rolled multipart/form-data body -- stdlib `urllib` has no
    built-in helper for this, and pulling in `requests` would defeat the
    point of a zero-install script."""
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


def submit_job(server: str, api_key: str, book_id: str, images: list[Path]) -> str:
    body, content_type = _encode_multipart({"book_id": book_id}, images)
    payload = _request_json(f"{server}/jobs", api_key, data=body, content_type=content_type)
    return payload["job_id"]


def wait_for_job(server: str, api_key: str, job_id: str, poll_seconds: float = 5.0) -> None:
    elapsed = 0
    while True:
        payload = _request_json(f"{server}/jobs/{job_id}", api_key)
        status = payload["status"]
        if status == "done":
            print(f"  -> 완료 (총 {elapsed}초)")
            return
        if status == "error":
            raise RuntimeError(f"작업이 실패했습니다: {payload.get('error')}")
        print(f"  -> 처리 중... ({elapsed}초 경과, 상태: {status})")
        time.sleep(poll_seconds)
        elapsed += int(poll_seconds)


def download_and_extract(server: str, api_key: str, job_id: str, book_id: str) -> Path:
    request = urllib.request.Request(f"{server}/jobs/{job_id}/download", headers={"X-API-Key": api_key})
    with urllib.request.urlopen(request) as response:
        data = response.read()
    zip_path = Path(f"{book_id}.zip")
    zip_path.write_bytes(data)
    extract_dir = Path(f"{book_id}_result")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
    return extract_dir


def main(argv: list[str] | None = None) -> int:
    # 다른 이 프로젝트 CLI들(accessibility/cli.py, server/cli.py)과 같은 이유:
    # 한국어 로케일 Windows 콘솔의 기본 코드페이지(cp949)는 이 스크립트가
    # 출력하는 문자 일부를 못 그려서 UnicodeEncodeError로 죽거나 글자가
    # 깨져 보일 수 있다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", required=True, help="서버 주소 (예: https://...trycloudflare.com, 끝에 / 없이)")
    parser.add_argument("--api-key", required=True, help="서버 운영자가 알려준 인증 값")
    parser.add_argument("--book-id", required=True, help="이번 테스트를 구분할 아무 이름")
    parser.add_argument("images", nargs="+", type=Path, help="보낼 이미지 파일들")
    args = parser.parse_args(argv)

    server = args.server.rstrip("/")
    for image in args.images:
        if not image.is_file():
            print(f"파일을 찾을 수 없습니다: {image}", file=sys.stderr)
            return 1

    print("[1/3] 이미지 전송 중...")
    try:
        job_id = submit_job(server, args.api_key, args.book_id, args.images)
    except urllib.error.HTTPError as exc:
        print(f"전송 실패 ({exc.code}): {exc.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"서버에 연결할 수 없습니다: {exc.reason}", file=sys.stderr)
        return 1
    print(f"  -> 등록됨 (작업 번호: {job_id})")

    print("[2/3] 처리 대기 중 (몇십 초~몇 분 걸릴 수 있습니다)...")
    try:
        wait_for_job(server, args.api_key, job_id)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("[3/3] 결과 다운로드 및 압축 해제 중...")
    extract_dir = download_and_extract(server, args.api_key, job_id, args.book_id)

    print()
    print(f"완료! 결과: {extract_dir}")
    print(f"확인하려면 (이 프로젝트 코드가 있는 컴퓨터에서): python -m document_parser.server.cli {extract_dir} {args.book_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
