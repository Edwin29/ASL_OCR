"""Thin HTTP client for document-parser's existing
`document_parser.datapack.remote_ingest` upload API (`POST /jobs`).

Deliberately just a function, not a class with state -- the plan leaves
open whether this responsibility ultimately lives in book-scanner or moves
into document-parser, so keeping it a small, dependency-light wrapper
around one existing endpoint (rather than new server logic) makes that
later move cheap either way.
"""

from __future__ import annotations

from pathlib import Path

import requests


def upload_page(server_url: str, api_key: str, book_id: str, image_path: Path, timeout: float = 30.0) -> dict:
    """POST `image_path` to `{server_url}/jobs` for `book_id`. Returns the
    parsed JSON job response. Raises `requests.HTTPError` on a non-2xx
    response."""
    image_path = Path(image_path)
    with open(image_path, "rb") as f:
        response = requests.post(
            f"{server_url.rstrip('/')}/jobs",
            headers={"X-API-Key": api_key},
            data={"book_id": book_id},
            files={"images": (image_path.name, f, "image/png")},
            timeout=timeout,
        )
    response.raise_for_status()
    return response.json()
