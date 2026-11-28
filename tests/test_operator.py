import json
from pathlib import Path
import tempfile
import unittest

from chimera import OperatorInputError, OperatorOutputError, VerificationReport
from chimera.cli import main


FIXTURES = Path(__file__).parents[1] / "examples" / "fixtures"


class OperatorWorkflowTests(unittest.TestCase):
    def test_passing_operator_journey_writes_reopenable_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            code = main([
                "verify-link", str(FIXTURES / "link_margin_passed.csv"),
                "--threshold-db", "3.0", "--output", str(output),
            ])
            self.assertEqual(0, code)
            self.assertEqual(
                {"bindings.json", "evidence.json", "evidence.sqlite", "journal.sqlite",
                 "report.html", "report.json", "request.json"},
                {item.name for item in output.iterdir()},
            )
            report = VerificationReport.from_json(
                (output / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual("pass", report.to_dict()["requirement"]["verdict"])
            self.assertIsNone(report.to_dict()["provenance"])

    def test_fault_journey_returns_requirement_failure_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            source = FIXTURES / "link_margin_passed.csv"
            original = source.read_bytes()
            code = main([
                "verify-link", str(source), "--threshold-db", "3.0",
                "--fault-plan", str(FIXTURES / "link_fault_plan.json"),
                "--output", str(output),
            ])
            self.assertEqual(1, code)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual("fail", report["requirement"]["verdict"])
            self.assertTrue(report["provenance"]["synthetic"])
            self.assertEqual(original, source.read_bytes())

    def test_completed_run_resumes_idempotently_without_changing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            args = [
                "verify-link", str(FIXTURES / "link_margin_passed.csv"),
                "--threshold-db", "3.0", "--output", str(output),
            ]
            self.assertEqual(0, main(args))
            run_id = json.loads((output / "request.json").read_text())["run_id"]
            before = {item.name: item.read_bytes() for item in output.iterdir()}
            self.assertEqual(0, main(args + ["--resume-run-id", run_id]))
            after = {item.name: item.read_bytes() for item in output.iterdir()}
            self.assertEqual(before, after)

    def test_changed_input_is_rejected_before_resume_callbacks(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "source.csv")
            source.write_bytes((FIXTURES / "link_margin_passed.csv").read_bytes())
            output = Path(directory, "run")
            args = ["verify-link", str(source), "--threshold-db", "3.0",
                    "--output", str(output)]
            self.assertEqual(0, main(args))
            run_id = json.loads((output / "request.json").read_text())["run_id"]
            source.write_bytes((FIXTURES / "link_margin_failed.csv").read_bytes())
            before = (output / "journal.sqlite").read_bytes()
            self.assertEqual(2, main(args + ["--resume-run-id", run_id]))
            self.assertEqual(before, (output / "journal.sqlite").read_bytes())

    def test_invalid_input_has_no_output_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            code = main([
                "verify-link", str(FIXTURES / "link_margin_malformed.csv"),
                "--threshold-db", "3.0", "--output", str(output),
            ])
            self.assertEqual(2, code)
            self.assertFalse(output.exists())

    def test_existing_directory_is_not_reused_for_new_run(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            output.mkdir()
            sentinel = Path(output, "keep.txt")
            sentinel.write_text("keep", encoding="utf-8")
            code = main([
                "verify-link", str(FIXTURES / "link_margin_passed.csv"),
                "--threshold-db", "3.0", "--output", str(output),
            ])
            self.assertEqual(3, code)
            self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))

    def test_conflicting_report_is_not_overwritten_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "run")
            args = [
                "verify-link", str(FIXTURES / "link_margin_passed.csv"),
                "--threshold-db", "3.0", "--output", str(output),
            ]
            self.assertEqual(0, main(args))
            run_id = json.loads((output / "request.json").read_text())["run_id"]
            (output / "report.json").write_text("changed", encoding="utf-8")
            self.assertEqual(3, main(args + ["--resume-run-id", run_id]))
            self.assertEqual("changed", (output / "report.json").read_text())


if __name__ == "__main__":
    unittest.main()
