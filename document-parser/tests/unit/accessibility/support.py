"""Shared fixture-loading helper for accessibility unit tests."""

import json
from pathlib import Path

from document_parser.accessibility.flattening import flatten_document

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "accessibility"


def load_fixture(page_id: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / f"{page_id}.json").read_text(encoding="utf-8"))


def load_accessible_document(page_id: str) -> dict[str, object]:
    return flatten_document(load_fixture(page_id))
