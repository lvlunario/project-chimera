import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import chimera.operator as operator
from chimera import OperatorError, OperatorInputError, OperatorOutputError
from chimera.cli import main
from chimera.journal import JournalTask


FIXTURES = Path(__file__).parents[1] / "examples" / "fixtures"


class OperatorIndependentQATests(unittest.TestCase):
    def _args(self, output: Path, *, threshold: str = "3.0") -> list[str]:
        return [
            "verify-link", str(FIXTURES / "link_margin_passed.csv"),
            "--threshold-db", threshold, "--output", str(output),
        ]

    def test_outcome_unknown_task_is_not_replayed_by_operator_resume(self):
        """A BaseException after the running marker must block every callback."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            source = (FIXTURES / "link_margin_passed.csv").read_bytes()
            original_tasks = operator._tasks(source, "3.0", None)

            def interrupt():
                raise KeyboardInterrupt("simulated process interruption")

            interrupted = (
                original_tasks[0],
                JournalTask(
                    original_tasks[1].id, interrupt,
                    original_tasks[1].operation_id,
                    original_tasks[1].dependencies,
                ),
                original_tasks[2],
            )
            with patch("chimera.operator._tasks", return_value=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    operator.run_link_verification(
                        FIXTURES / "link_margin_passed.csv", output,
                        threshold_db="3.0",
                    )

            run_id = json.loads((output / "request.json").read_text())["run_id"]
            calls = []

            def forbidden():
                calls.append("called")
                return True

            resume_tasks = tuple(
                JournalTask(task.id, forbidden, task.operation_id, task.dependencies)
                for task in original_tasks
            )
            with patch("chimera.operator._tasks", return_value=resume_tasks):
                with self.assertRaisesRegex(
                    OperatorError, "Unknown running task|requires attention"
                ):
                    operator.run_link_verification(
                        FIXTURES / "link_margin_passed.csv", output,
                        threshold_db="3.0", resume_run_id=run_id,
                    )
            self.assertEqual([], calls)
            self.assertFalse((output / "report.json").exists())

    def test_changed_fault_plan_is_rejected_before_journal_access(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            plan = Path(directory, "plan.json")
            plan.write_bytes((FIXTURES / "link_fault_plan.json").read_bytes())
            args = self._args(output) + ["--fault-plan", str(plan)]
            self.assertEqual(1, main(args))
            run_id = json.loads((output / "request.json").read_text())["run_id"]
            journal_before = (output / "journal.sqlite").read_bytes()
            plan.write_text(
                '{"schema_version":1,"model":"sample-replacement-v1",'
                '"replacements":[]}', encoding="utf-8",
            )
            self.assertEqual(2, main(args + ["--resume-run-id", run_id]))
            self.assertEqual(journal_before, (output / "journal.sqlite").read_bytes())

    def test_corrupt_journal_is_normalized_to_unavailable_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            args = self._args(output)
            self.assertEqual(0, main(args))
            run_id = json.loads((output / "request.json").read_text())["run_id"]
            (output / "journal.sqlite").write_bytes(b"not a SQLite database")
            self.assertEqual(3, main(args + ["--resume-run-id", run_id]))

    def test_symlinked_output_artifact_is_rejected_without_target_change(self):
        if not hasattr(Path, "symlink_to"):
            self.skipTest("symbolic links unavailable")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            args = self._args(output)
            self.assertEqual(0, main(args))
            run_id = json.loads((output / "request.json").read_text())["run_id"]
            target = Path(directory, "external.json")
            target.write_text((output / "report.json").read_text(), encoding="utf-8")
            (output / "report.json").unlink()
            (output / "report.json").symlink_to(target)
            before = target.read_bytes()
            self.assertEqual(3, main(args + ["--resume-run-id", run_id]))
            self.assertEqual(before, target.read_bytes())

    def test_non_ascii_threshold_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            with self.assertRaises(OperatorInputError):
                operator.run_link_verification(
                    FIXTURES / "link_margin_passed.csv", output,
                    threshold_db="３.０",
                )
            self.assertFalse(output.exists())

    def test_excessive_exponent_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            with self.assertRaises(OperatorInputError):
                operator.run_link_verification(
                    FIXTURES / "link_margin_passed.csv", output,
                    threshold_db="1e9999999999999999999999999999999999999",
                )
            self.assertFalse(output.exists())

    def test_optimized_module_cli_generates_valid_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            completed = subprocess.run(
                [
                    sys.executable, "-O", "-m", "chimera.cli", "verify-link",
                    str(FIXTURES / "link_margin_passed.csv"),
                    "--threshold-db", "3.0", "--output", str(output),
                ],
                cwd=Path(__file__).parents[1], capture_output=True, text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual("pass", report["requirement"]["verdict"])


if __name__ == "__main__":
    unittest.main()
