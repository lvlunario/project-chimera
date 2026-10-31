import json
from pathlib import Path
import tempfile
import unittest

from chimera import run_with_evidence
from chimera.workflow import MAX_WORKFLOW_BYTES, WorkflowError, load_workflow, parse_workflow


class WorkflowTests(unittest.TestCase):
    def test_valid_workflow_is_deterministic_and_bounded(self):
        tasks = parse_workflow(json.dumps({
            "schema_version": 1,
            "tasks": [
                {"id": "b", "operation": "emit", "value": [1, {"ok": True}]},
                {"id": "a", "operation": "fail", "message": "expected"},
                {"id": "c", "operation": "emit", "value": None, "dependencies": ["a"]},
            ],
        }))
        records = run_with_evidence(tasks).to_dict()["tasks"]
        self.assertEqual([record["task_id"] for record in records], ["a", "b", "c"])
        self.assertEqual([record["status"] for record in records], ["failed", "succeeded", "blocked"])

    def test_rejects_invalid_documents(self):
        invalid = [
            '{"schema_version":1,"schema_version":1,"tasks":[]}',
            '{"schema_version":NaN,"tasks":[]}',
            json.dumps({"schema_version": True, "tasks": []}),
            json.dumps({"schema_version": 2, "tasks": []}),
            json.dumps({"schema_version": 1, "tasks": [], "extra": 1}),
            json.dumps({"schema_version": 1, "tasks": "no"}),
            "not json",
        ]
        for document in invalid:
            with self.subTest(document=document), self.assertRaises(WorkflowError):
                parse_workflow(document)

    def test_rejects_invalid_tasks(self):
        invalid_tasks = [
            {"id": "bad id", "operation": "emit", "value": 1},
            {"id": "a" * 129, "operation": "emit", "value": 1},
            {"id": "a", "operation": "unknown", "value": 1},
            {"id": "a", "operation": "emit"},
            {"id": "a", "operation": "emit", "value": 1, "extra": True},
            {"id": "a", "operation": "fail", "message": ""},
            {"id": "a", "operation": "fail", "message": "x" * 1001},
            {"id": "a", "operation": "fail", "message": "x", "value": 1},
            {"id": "a", "operation": "emit", "value": 1, "dependencies": "b"},
            {"id": "a", "operation": "emit", "value": 1, "dependencies": ["b", "b"]},
        ]
        for task in invalid_tasks:
            with self.subTest(task=task), self.assertRaises(WorkflowError):
                parse_workflow(json.dumps({"schema_version": 1, "tasks": [task]}))

    def test_rejects_duplicate_task_ids(self):
        document = {"schema_version": 1, "tasks": [
            {"id": "same", "operation": "emit", "value": 1},
            {"id": "same", "operation": "emit", "value": 2},
        ]}
        with self.assertRaisesRegex(WorkflowError, "Duplicate task id"):
            parse_workflow(json.dumps(document))

    def test_load_rejects_oversize_and_non_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "workflow.json")
            path.write_bytes(b" " * (MAX_WORKFLOW_BYTES + 1))
            with self.assertRaisesRegex(WorkflowError, "exceeds"):
                load_workflow(path)
            path.write_bytes(b"\xff")
            with self.assertRaisesRegex(WorkflowError, "UTF-8"):
                load_workflow(path)


if __name__ == "__main__":
    unittest.main()
