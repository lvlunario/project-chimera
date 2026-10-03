import json
import unittest

from chimera import BindingError, RequirementBindings


class RequirementBindingsTests(unittest.TestCase):
    def test_mapping_round_trip_is_canonical_and_detached(self):
        source = {"R2": "task-b", "R1": "task-a"}
        bindings = RequirementBindings.from_mapping(source)
        source["R1"] = "changed"
        self.assertEqual(bindings.to_mapping(), {"R1": "task-a", "R2": "task-b"})
        self.assertEqual(bindings, RequirementBindings.from_json(bindings.to_json()))
        self.assertEqual(
            bindings.to_json(),
            '{"bindings":[{"requirement_id":"R1","task_id":"task-a"},'
            '{"requirement_id":"R2","task_id":"task-b"}],"schema_version":1}',
        )
        self.assertEqual(
            bindings.sha256,
            "de0516478247e8e75cdc5068af83148090a8dd2519eb2dfe3832ffad2d85283a",
        )

    def test_equivalent_order_has_same_json_and_digest(self):
        first = RequirementBindings.from_mapping({"R2": "b", "R1": "a"})
        second = RequirementBindings.from_mapping({"R1": "a", "R2": "b"})
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.sha256, second.sha256)

    def test_empty_selection_is_valid_artifact(self):
        bindings = RequirementBindings.from_mapping({})
        self.assertEqual(bindings.to_mapping(), {})

    def test_rejects_invalid_documents(self):
        invalid = [
            "[]", "{}", '{"schema_version":2,"bindings":[]}',
            '{"schema_version":true,"bindings":[]}',
            '{"schema_version":1,"bindings":{},"extra":0}',
            '{"schema_version":1,"bindings":[{}]}',
            '{"schema_version":1,"bindings":[{"requirement_id":"","task_id":"t"}]}',
            '{"schema_version":1,"bindings":[{"requirement_id":"R","task_id":" "}]}',
            '{"schema_version":1,"bindings":[{"requirement_id":"R","task_id":"a"},{"requirement_id":"R","task_id":"b"}]}',
            '{"schema_version":1,"schema_version":1,"bindings":[]}',
            '{"schema_version":1,"bindings":[{"requirement_id":"\\ud800","task_id":"t"}]}',
            '{"schema_version":1,"bindings":[{"requirement_id":"R","task_id":"\\udfff"}]}',
        ]
        for document in invalid:
            with self.subTest(document=document), self.assertRaises(BindingError):
                RequirementBindings.from_json(document)

    def test_rejects_non_mapping_and_non_string_mapping_ids(self):
        with self.assertRaises(TypeError):
            RequirementBindings.from_mapping([("R", "task")])
        for value in ({1: "task"}, {"R": None}, {"R": ["task"]}, {"R": "\udfff"}):
            with self.subTest(value=value), self.assertRaises(BindingError):
                RequirementBindings.from_mapping(value)

    def test_json_is_utf8_stable(self):
        bindings = RequirementBindings.from_mapping({"REQ-μ": "check-μ"})
        self.assertIn("μ", bindings.to_json())
        self.assertEqual(json.loads(bindings.to_json())["schema_version"], 1)
