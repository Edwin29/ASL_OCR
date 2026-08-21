import unittest

from document_parser.datapack import (
    SYSTEM_BOUNDARY_MESSAGES,
    build_audio_index_entry,
    build_manifest,
    utterance_key_for_cell,
    utterance_key_for_item,
    utterance_key_for_span,
)


class SystemBoundaryMessagesTests(unittest.TestCase):
    def test_no_duplicates(self):
        self.assertEqual(len(SYSTEM_BOUNDARY_MESSAGES), len(set(SYSTEM_BOUNDARY_MESSAGES)))

    def test_all_non_empty_strings(self):
        self.assertTrue(all(isinstance(message, str) and message for message in SYSTEM_BOUNDARY_MESSAGES))


class UtteranceKeyTests(unittest.TestCase):
    def test_item_key_is_item_id(self):
        item = {"id": "p003-node-007", "kind": "TEXT"}
        self.assertEqual(utterance_key_for_item(item), "p003-node-007")

    def test_span_key_appends_index(self):
        item = {"id": "p003-node-007", "kind": "TEXT"}
        self.assertEqual(utterance_key_for_span(item, 0), "p003-node-007#0")
        self.assertEqual(utterance_key_for_span(item, 2), "p003-node-007#2")

    def test_cell_key_prefers_cell_id(self):
        item = {"id": "p003-node-012", "kind": "TABLE"}
        cell = {"id": "p003-node-012-r1-c2", "row_index": 1, "column_index": 2}
        self.assertEqual(utterance_key_for_cell(item, cell), "p003-node-012-r1-c2")

    def test_cell_key_falls_back_to_row_column(self):
        item = {"id": "p003-node-012", "kind": "TABLE"}
        cell = {"id": None, "row_index": 1, "column_index": 2}
        self.assertEqual(utterance_key_for_cell(item, cell), "p003-node-012#r1c2")

    def test_cell_key_falls_back_when_id_missing_entirely(self):
        item = {"id": "p003-node-012", "kind": "TABLE"}
        cell = {"row_index": 0, "column_index": 0}
        self.assertEqual(utterance_key_for_cell(item, cell), "p003-node-012#r0c0")


class BuildManifestTests(unittest.TestCase):
    def test_round_trips_all_fields(self):
        manifest = build_manifest(
            book_id="ebs_2027_math1",
            title="2027 수능특강 수학Ⅰ",
            page_ids=["p003", "p004"],
            created_at="2026-08-21T21:20:24+09:00",
            engine_manifest={"general_ocr": {"engine_id": "paddleocr_vl"}},
            tts_manifest={"engine_id": "piper", "voice": "ko_KR-kss-medium"},
            validation_summary={"schema_valid": True},
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["book_id"], "ebs_2027_math1")
        self.assertEqual(manifest["page_ids"], ["p003", "p004"])
        self.assertEqual(manifest["engine_manifest"], {"general_ocr": {"engine_id": "paddleocr_vl"}})
        self.assertEqual(manifest["tts_manifest"]["voice"], "ko_KR-kss-medium")
        self.assertEqual(manifest["validation_summary"], {"schema_valid": True})

    def test_page_ids_copied_not_aliased(self):
        page_ids = ["p003", "p004"]
        manifest = build_manifest(
            book_id="b", title="t", page_ids=page_ids, created_at="now",
            engine_manifest={}, tts_manifest={}, validation_summary={},
        )
        page_ids.append("p005")
        self.assertEqual(manifest["page_ids"], ["p003", "p004"])


class BuildAudioIndexEntryTests(unittest.TestCase):
    def test_shape(self):
        entry = build_audio_index_entry(
            text="함수 f에 대하여",
            wav_path="audio/p003-node-007.wav",
            duration_ms=2140,
            sample_rate=22050,
        )
        self.assertEqual(entry, {
            "text": "함수 f에 대하여",
            "wav": "audio/p003-node-007.wav",
            "duration_ms": 2140,
            "sample_rate": 22050,
        })


if __name__ == "__main__":
    unittest.main()
