from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from document_parser.datapack.ingest import build_datapack
from document_parser.datapack.preflight import preflight_catalog, preflight_datapack_root
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store


class FakeSynthesizer:
    def __call__(self, text):
        return (b"\x00\x00" * 100, 16000, 1)


class FixtureVlAdapter:
    engine_id = "fixture-paddleocr-vl"
    engine_version = "0.0.0"

    def __init__(self, result_by_path):
        self.result_by_path = result_by_path

    def parse_page(self, image_path):
        return self.result_by_path[str(Path(image_path).resolve())]


def _write_book(datapacks_dir: Path, book_id: str = "book-a") -> Path:
    image = datapacks_dir / "source.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"fixture")
    page_ir = build_document_ir_from_vl(
        [image],
        adapter=FixtureVlAdapter(
            {
                str(image.resolve()): {
                    "width": 1000,
                    "height": 1400,
                    "parsing_res_list": [
                        {
                            "block_label": "text",
                            "block_content": "테스트 본문",
                            "block_bbox": [10, 10, 900, 100],
                            "block_id": 1,
                            "block_order": 1,
                        }
                    ],
                }
            }
        ),
        book_id=book_id,
    )
    return build_datapack(
        book_id,
        book_id,
        page_ir,
        FakeSynthesizer(),
        {},
        datapacks_dir,
        datapacks_dir / "_system",
        log_fn=lambda _message: None,
    )


def test_preflight_accepts_complete_datapack() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        datapacks = Path(temp_dir) / "datapacks"
        book = _write_book(datapacks)

        report = preflight_datapack_root(book, datapacks / "_system")

        assert report["status"] == "passed"
        assert report["error_count"] == 0
        assert report["metrics"]["page_count"] == 1
        assert report["metrics"]["checked_audio_file_count"] > 0


def test_preflight_reports_missing_required_wav() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        datapacks = Path(temp_dir) / "datapacks"
        book = _write_book(datapacks)
        index = json.loads((book / "audio_index.json").read_text(encoding="utf-8"))
        wav = next(iter(index["utterances"].values()))["wav"]
        (book / wav).unlink()

        report = preflight_datapack_root(book, datapacks / "_system")

        assert report["status"] == "failed"
        assert "AUDIO_FILE_MISSING" in {issue["code"] for issue in report["issues"]}


def test_preflight_reports_braille_exception_without_raising() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        datapacks = Path(temp_dir) / "datapacks"
        book = _write_book(datapacks)
        document_path = book / "document.json"
        document = json.loads(document_path.read_text(encoding="utf-8"))
        item = document["pages"][0]["focus_items"][0]
        item.update(
            {
                "kind": "MATH",
                "raw_formula": "x",
                "presentation_ast": {"type": "Identifier", "name": "x"},
                "ast_status": "VALID",
            }
        )
        document_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

        with patch(
            "document_parser.datapack.preflight.BraillePresenter.present_focus",
            side_effect=ValueError("bad math"),
        ):
            report = preflight_datapack_root(book, datapacks / "_system")

        assert "BRAILLE_RENDER_FAILED" in {issue["code"] for issue in report["issues"]}


def test_catalog_preflight_checks_only_current_ready_revisions() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        datapacks = root / "datapacks"
        _write_book(datapacks)
        control = S0ControlPlane(S0Store(root / "state.sqlite3", datapacks))
        control.bootstrap_existing_datapacks()
        control.create_datapack("device-1", "draft-operation")

        report = preflight_catalog(root / "state.sqlite3", datapacks)

        assert report["status"] == "passed"
        assert report["catalog_datapack_count"] == 2
        assert report["checked_revision_count"] == 1
        assert report["skipped_datapack_count"] == 1
