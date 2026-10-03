import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from chimera.cli import main


class CliTests(unittest.TestCase):
    def _write(self, directory: str, tasks: list[dict]) -> Path:
        path = Path(directory, "workflow.json")
        path.write_text(json.dumps({"schema_version": 1, "tasks": tasks}), encoding="utf-8")
        return path

    def test_success_writes_reopenable_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = self._write(directory, [{"id": "check", "operation": "emit", "value": {"margin_db": 4.5}}])
            evidence = Path(directory, "run.json")
            self.assertEqual(main(["run", str(workflow), "--evidence", str(evidence)]), 0)
            document = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(document["tasks"][0]["status"], "succeeded")

    def test_expected_failure_writes_evidence_and_returns_one(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = self._write(directory, [
                {"id": "check", "operation": "fail", "message": "below limit"},
                {"id": "report", "operation": "emit", "value": "bad", "dependencies": ["check"]},
                {"id": "health", "operation": "emit", "value": "ok"},
            ])
            evidence = Path(directory, "run.json")
            self.assertEqual(main(["run", str(workflow), "--evidence", str(evidence)]), 1)
            statuses = {task["task_id"]: task["status"] for task in json.loads(evidence.read_text())["tasks"]}
            self.assertEqual(statuses, {"check": "failed", "health": "succeeded", "report": "blocked"})

    def test_invalid_graph_returns_two_without_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = self._write(directory, [{"id": "a", "operation": "emit", "value": 1, "dependencies": ["missing"]}])
            evidence = Path(directory, "run.json")
            self.assertEqual(main(["run", str(workflow), "--evidence", str(evidence)]), 2)
            self.assertFalse(evidence.exists())

    def test_existing_output_returns_three_and_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = self._write(directory, [{"id": "a", "operation": "emit", "value": 1}])
            evidence = Path(directory, "run.json")
            evidence.write_text("keep", encoding="utf-8")
            self.assertEqual(main(["run", str(workflow), "--evidence", str(evidence)]), 3)
            self.assertEqual(evidence.read_text(encoding="utf-8"), "keep")

    def test_module_entrypoint_uses_usage_exit_two(self):
        result = subprocess.run(
            [sys.executable, "-m", "chimera.cli"], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: chimera", result.stderr)


if __name__ == "__main__":
    unittest.main()
