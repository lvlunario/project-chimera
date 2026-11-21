"""Independent negative-path tests for the declarative CLI boundary."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chimera.cli import main
from chimera.workflow import (
    MAX_DEPENDENCIES,
    MAX_TASKS,
    WorkflowError,
    parse_workflow,
)


def _document(tasks: list[dict]) -> str:
    return json.dumps({"schema_version": 1, "tasks": tasks})


class CliIndependentQATests(unittest.TestCase):
    def test_duplicate_key_at_nested_depth_is_rejected(self):
        document = (
            '{"schema_version":1,"tasks":['
            '{"id":"check","operation":"emit","value":{"reading":1,"reading":2}}]}'
        )
        with self.assertRaisesRegex(WorkflowError, "Duplicate JSON field: reading"):
            parse_workflow(document)

    def test_value_nesting_limit_is_enforced(self):
        value: object = 0
        for _ in range(101):
            value = [value]
        with self.assertRaisesRegex(WorkflowError, "100 nesting levels"):
            parse_workflow(_document([
                {"id": "check", "operation": "emit", "value": value}
            ]))

    def test_task_and_dependency_count_limits_are_enforced(self):
        too_many_tasks = [
            {"id": f"t{index}", "operation": "emit", "value": None}
            for index in range(MAX_TASKS + 1)
        ]
        with self.assertRaisesRegex(WorkflowError, "at most"):
            parse_workflow(_document(too_many_tasks))

        too_many_dependencies = [f"d{index}" for index in range(MAX_DEPENDENCIES + 1)]
        with self.assertRaisesRegex(WorkflowError, "dependencies must be a list"):
            parse_workflow(_document([
                {
                    "id": "check",
                    "operation": "emit",
                    "value": None,
                    "dependencies": too_many_dependencies,
                }
            ]))

    def test_huge_json_integer_has_domain_specific_error(self):
        document = (
            '{"schema_version":1,"tasks":['
            '{"id":"check","operation":"emit","value":' + ("9" * 5_000) + "}]}"
        )
        with self.assertRaises(WorkflowError):
            parse_workflow(document)

    def test_cycle_and_missing_dependency_exit_two_without_evidence(self):
        invalid_workflows = [
            [{"id": "a", "operation": "emit", "value": 1, "dependencies": ["a"]}],
            [{"id": "a", "operation": "emit", "value": 1, "dependencies": ["missing"]}],
        ]
        for tasks in invalid_workflows:
            with self.subTest(tasks=tasks), tempfile.TemporaryDirectory() as directory:
                workflow = Path(directory, "workflow.json")
                workflow.write_text(_document(tasks), encoding="utf-8")
                evidence = Path(directory, "evidence.json")
                with patch("sys.stderr"):
                    self.assertEqual(
                        main(["run", str(workflow), "--evidence", str(evidence)]), 2
                    )
                self.assertFalse(evidence.exists())

    def test_input_cannot_select_python_import_or_execute_code(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory, "must-not-exist")
            workflow = Path(directory, "workflow.json")
            workflow.write_text(_document([
                {
                    "id": "attack",
                    "operation": "__import__",
                    "value": f"pathlib.Path({str(sentinel)!r}).touch()",
                }
            ]), encoding="utf-8")
            evidence = Path(directory, "evidence.json")
            with patch("sys.stderr"):
                self.assertEqual(
                    main(["run", str(workflow), "--evidence", str(evidence)]), 2
                )
            self.assertFalse(sentinel.exists())
            self.assertFalse(evidence.exists())

    def test_existing_evidence_is_not_overwritten_even_on_failed_run(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory, "workflow.json")
            workflow.write_text(_document([
                {"id": "check", "operation": "fail", "message": "expected"}
            ]), encoding="utf-8")
            evidence = Path(directory, "evidence.json")
            evidence.write_bytes(b"original evidence")
            with patch("sys.stderr"):
                self.assertEqual(
                    main(["run", str(workflow), "--evidence", str(evidence)]), 3
                )
            self.assertEqual(evidence.read_bytes(), b"original evidence")

    def test_unwritable_destination_returns_three_without_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory, "workflow.json")
            workflow.write_text(_document([
                {"id": "check", "operation": "emit", "value": "ok"}
            ]), encoding="utf-8")
            evidence = Path(directory, "missing", "evidence.json")
            with patch("sys.stderr"):
                self.assertEqual(
                    main(["run", str(workflow), "--evidence", str(evidence)]), 3
                )
            self.assertFalse(evidence.exists())


if __name__ == "__main__":
    unittest.main()
