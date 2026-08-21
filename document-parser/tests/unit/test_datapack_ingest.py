import json
import tempfile
import unittest
import wave
from pathlib import Path

from document_parser.datapack.ingest import (
    build_datapack,
    ensure_system_pool,
    enumerate_utterances,
    synthesize_all,
)
from document_parser.datapack.schema import SYSTEM_BOUNDARY_MESSAGES
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl


class FakeSynthesizer:
    """Deterministic, silent fake TTS: same shape as a real `SynthesizeFn`
    (text -> (pcm16 bytes, sample_rate, channels)) but instant and offline,
    matching this project's convention of testing the real production path
    minus the model (see `FixtureVlAdapter` in test_vl_page_ir.py)."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, text: str) -> tuple[bytes, int, int]:
        self.calls.append(text)
        # 100 int16 samples of silence at 16kHz mono.
        return (b"\x00\x00" * 100, 16000, 1)


class FixtureVlAdapter:
    engine_id = "fixture-paddleocr-vl"
    engine_version = "0.0.0"

    def __init__(self, result_by_path):
        self.result_by_path = result_by_path

    def parse_page(self, image_path):
        return self.result_by_path[str(Path(image_path).resolve())]


def text_block(block_id, content, order, bbox=None):
    return {
        "block_label": "text",
        "block_content": content,
        "block_bbox": bbox or [100, 100 + block_id * 100, 900, 160 + block_id * 100],
        "block_id": block_id,
        "block_order": order,
    }


def fixture_result(blocks):
    return {"width": 2434, "height": 3071, "parsing_res_list": blocks}


def build_sample_page_ir(book_id="test-book"):
    """A small but multi-kind Page IR (TEXT with an inline math span, a
    display formula, and a table) via the real production path
    (`build_document_ir_from_vl`), no model weights required."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        image_path = root / f"{book_id}_p001.png"
        image_path.write_bytes(b"fake-png")

        blocks = [
            text_block(1, "함수 $f(x)=x^2$ 에 대하여", order=1),
            {
                "block_label": "display_formula",
                "block_content": "$$y=2x+1$$",
                "block_bbox": [100, 300, 500, 350],
                "block_id": 2,
                "block_order": 2,
            },
            {
                "block_label": "table",
                "block_content": "<table><tr><td>a&gt;0</td></tr></table>",
                "block_bbox": [100, 400, 500, 500],
                "block_id": 3,
                "block_order": 3,
            },
        ]
        adapter = FixtureVlAdapter({str(image_path.resolve()): fixture_result(blocks)})
        return build_document_ir_from_vl([image_path], adapter=adapter, book_id=book_id)


class EnumerateUtterancesTests(unittest.TestCase):
    def test_covers_text_math_span_and_table_cell(self):
        from document_parser.accessibility.flattening import flatten_document

        page_ir = build_sample_page_ir()
        document = flatten_document(page_ir)

        utterances = enumerate_utterances(document)

        focus_items = document["pages"][0]["focus_items"]
        kinds = {item["kind"] for item in focus_items}
        self.assertEqual(kinds, {"TEXT", "MATH", "TABLE"})

        text_item = next(item for item in focus_items if item["kind"] == "TEXT")
        table_item = next(item for item in focus_items if item["kind"] == "TABLE")

        for item in focus_items:
            self.assertIn(item["id"], utterances)
        # The TEXT item has one inline math span (x^2) -> one span-level entry.
        self.assertIn(f"{text_item['id']}#0", utterances)
        # The table has exactly one cell -> one cell-level entry.
        cell_id = table_item["cells"][0]["id"]
        self.assertIn(cell_id, utterances)

    def test_math_item_has_no_separate_span_entry(self):
        from document_parser.accessibility.flattening import flatten_document

        page_ir = build_sample_page_ir()
        document = flatten_document(page_ir)
        math_item = next(item for item in document["pages"][0]["focus_items"] if item["kind"] == "MATH")

        utterances = enumerate_utterances(document)

        self.assertNotIn(f"{math_item['id']}#0", utterances)


class SynthesizeAllTests(unittest.TestCase):
    def test_writes_one_wav_and_index_entry_per_utterance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pool_dir = Path(temp_dir)
            synth = FakeSynthesizer()

            index = synthesize_all({"a": "hello", "b": "world"}, synth, pool_dir, log_fn=lambda msg: None)

            self.assertEqual(set(index.keys()), {"a", "b"})
            self.assertTrue((pool_dir / "audio" / "a.wav").exists())
            self.assertTrue((pool_dir / "audio" / "b.wav").exists())
            self.assertEqual(index["a"]["text"], "hello")
            self.assertEqual(index["a"]["duration_ms"], 6)  # 100 samples / 16000 Hz * 1000
            with wave.open(str(pool_dir / "audio" / "a.wav"), "rb") as wav_file:
                self.assertEqual(wav_file.getframerate(), 16000)
                self.assertEqual(wav_file.getnchannels(), 1)

    def test_skips_resynthesis_when_cached_text_matches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pool_dir = Path(temp_dir)
            synth = FakeSynthesizer()
            first = synthesize_all({"a": "hello"}, synth, pool_dir, log_fn=lambda msg: None)
            self.assertEqual(len(synth.calls), 1)

            second = synthesize_all({"a": "hello"}, synth, pool_dir, existing_index=first, log_fn=lambda msg: None)

            self.assertEqual(len(synth.calls), 1)  # not called again
            self.assertEqual(second["a"], first["a"])

    def test_resynthesizes_when_cached_text_differs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pool_dir = Path(temp_dir)
            synth = FakeSynthesizer()
            first = synthesize_all({"a": "hello"}, synth, pool_dir, log_fn=lambda msg: None)

            second = synthesize_all({"a": "goodbye"}, synth, pool_dir, existing_index=first, log_fn=lambda msg: None)

            self.assertEqual(len(synth.calls), 2)
            self.assertEqual(second["a"]["text"], "goodbye")


class EnsureSystemPoolTests(unittest.TestCase):
    def test_synthesizes_all_boundary_messages_exactly_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            system_dir = Path(temp_dir)
            synth = FakeSynthesizer()

            index = ensure_system_pool(synth, system_dir, log_fn=lambda msg: None)

            self.assertEqual(len(index), len(SYSTEM_BOUNDARY_MESSAGES))
            self.assertEqual(len(synth.calls), len(SYSTEM_BOUNDARY_MESSAGES))
            self.assertTrue((system_dir / "audio_index.json").exists())

            ensure_system_pool(synth, system_dir, log_fn=lambda msg: None)
            self.assertEqual(len(synth.calls), len(SYSTEM_BOUNDARY_MESSAGES))  # idempotent, no re-synthesis


class BuildDatapackTests(unittest.TestCase):
    def test_writes_full_datapack_directory(self):
        page_ir = build_sample_page_ir(book_id="ebs_test")
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "datapacks"
            system_dir = output_dir / "_system"
            synth = FakeSynthesizer()

            book_dir = build_datapack(
                book_id="ebs_test",
                title="테스트 교재",
                page_ir=page_ir,
                synthesize=synth,
                tts_manifest={"engine_id": "piper", "voice": "ko_KR-kss-medium"},
                output_dir=output_dir,
                system_dir=system_dir,
                log_fn=lambda msg: None,
            )

            self.assertEqual(book_dir, output_dir / "ebs_test")
            manifest = json.loads((book_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["book_id"], "ebs_test")
            self.assertEqual(manifest["title"], "테스트 교재")
            self.assertEqual(manifest["page_ids"], ["p001"])
            self.assertTrue(manifest["validation_summary"]["schema_valid"])

            document = json.loads((book_dir / "document.json").read_text(encoding="utf-8"))
            self.assertEqual(document["document_id"], "ebs_test")

            audio_index = json.loads((book_dir / "audio_index.json").read_text(encoding="utf-8"))
            self.assertGreater(len(audio_index["utterances"]), 0)

            self.assertTrue((system_dir / "audio_index.json").exists())

    def test_refuses_invalid_page_ir(self):
        invalid_page_ir = {"validation_summary": {"schema_valid": False}}
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                build_datapack(
                    book_id="bad",
                    title="bad",
                    page_ir=invalid_page_ir,
                    synthesize=FakeSynthesizer(),
                    tts_manifest={},
                    output_dir=Path(temp_dir) / "datapacks",
                    system_dir=Path(temp_dir) / "datapacks" / "_system",
                    log_fn=lambda msg: None,
                )

    def test_second_run_reuses_cached_audio(self):
        page_ir = build_sample_page_ir(book_id="ebs_test2")
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "datapacks"
            system_dir = output_dir / "_system"
            synth = FakeSynthesizer()

            build_datapack(
                book_id="ebs_test2", title="t", page_ir=page_ir, synthesize=synth,
                tts_manifest={}, output_dir=output_dir, system_dir=system_dir, log_fn=lambda msg: None,
            )
            first_call_count = len(synth.calls)

            build_datapack(
                book_id="ebs_test2", title="t", page_ir=page_ir, synthesize=synth,
                tts_manifest={}, output_dir=output_dir, system_dir=system_dir, log_fn=lambda msg: None,
            )

            self.assertEqual(len(synth.calls), first_call_count)  # nothing new synthesized


if __name__ == "__main__":
    unittest.main()
