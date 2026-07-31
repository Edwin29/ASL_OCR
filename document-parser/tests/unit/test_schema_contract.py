import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SchemaContractTests(unittest.TestCase):
    def load_schema(self, name):
        return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))

    def test_page_ir_schema_declares_required_contract(self):
        schema = self.load_schema("page-ir.schema.json")
        self.assertIn("ParsedDocument", schema["title"])
        required = set(schema["required"])
        self.assertTrue({"document_manifest", "pages", "engine_manifest", "validation_summary"} <= required)
        node_types = set(schema["$defs"]["contentType"]["enum"])
        self.assertEqual(node_types, {"TEXT", "MATH", "TABLE", "UNSUPPORTED_VISUAL", "UNKNOWN"})

    def test_forbidden_semantic_fields_are_not_schema_properties(self):
        schema = self.load_schema("page-ir.schema.json")
        forbidden = {
            "importance",
            "educational_role",
            "problem_role",
            "answer_of",
            "solution_of",
            "visibility_level",
            "is_core_content",
            "tts_priority",
        }
        serialized = json.dumps(schema)
        for field in forbidden:
            self.assertNotIn(field, serialized)

    def test_supporting_schemas_are_valid_json(self):
        for name in ["math-ast.schema.json", "table-ir.schema.json", "parse-issue.schema.json"]:
            schema = self.load_schema(name)
            self.assertIn("$schema", schema)
            self.assertIn("title", schema)


if __name__ == "__main__":
    unittest.main()

