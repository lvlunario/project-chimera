"""Independent AI QA: requirement interpretation at integration boundaries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import MappingProxyType
import unittest

from chimera import EvidenceError, RunEvidence, Task, assess_requirements, run_with_evidence


class VerdictIndependentQATests(unittest.TestCase):
    def test_cli_execution_success_can_be_requirement_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory, "workflow.json")
            output = Path(directory, "run.json")
            workflow.write_text(json.dumps({"schema_version": 1, "tasks": [
                {"id": "check", "operation": "emit", "value": False},
                {"id": "handoff", "operation": "emit", "value": "ready",
                 "dependencies": ["check"]},
            ]}), encoding="utf-8")
            result = subprocess.run([
                sys.executable, "-m", "chimera.cli", "run", str(workflow),
                "--evidence", str(output),
            ], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = RunEvidence.from_json(output.read_text(encoding="utf-8"))
            assessment = assess_requirements(evidence, {"COM-LINK-001": "check"})
            self.assertEqual(assessment.outcomes[0].verdict, "fail")
            self.assertFalse(assessment.all_passed)
            self.assertTrue(all(task["status"] == "succeeded"
                                for task in evidence.to_dict()["tasks"]))

    def test_read_only_mapping_and_caller_selection_are_explicit(self):
        evidence = run_with_evidence([
            Task("passing", lambda: True), Task("failing", lambda: False),
        ])
        source = {"R1": "passing", "R2": "passing"}
        selected = assess_requirements(evidence, MappingProxyType(source))
        self.assertTrue(selected.all_passed)
        self.assertEqual(len(selected.outcomes), 2)
        source["R1"] = "failing"
        self.assertTrue(selected.all_passed)
        self.assertFalse(assess_requirements(evidence, source).all_passed)

    def test_ids_are_not_silently_normalized(self):
        evidence = run_with_evidence([Task("check", lambda: True)])
        assessment = assess_requirements(evidence, {"R": " check "})
        self.assertEqual(assessment.outcomes[0].verdict, "not_evaluated")
        self.assertFalse(assessment.all_passed)

    def test_truthy_json_values_stay_errors_after_replay(self):
        for value in ("true", "false", -1, 0.5, [False], {"pass": True}):
            with self.subTest(value=value):
                evidence = run_with_evidence([Task("check", lambda: value)])
                replay = RunEvidence.from_json(evidence.to_json())
                assessment = assess_requirements(replay, {"R": "check"})
                self.assertEqual(assessment.outcomes[0].verdict, "error")
                self.assertFalse(assessment.all_passed)

    def test_invalid_success_like_status_rejected_before_assessment(self):
        document = run_with_evidence([Task("check", lambda: True)]).to_dict()
        document["tasks"][0]["status"] = "running"
        with self.assertRaises(EvidenceError):
            RunEvidence.from_json(json.dumps(document))

    def test_assessment_does_not_mutate_or_rerun_on_repeated_reads(self):
        calls = []

        def action():
            calls.append("executed")
            return True

        evidence = run_with_evidence([Task("check", action)])
        original = evidence.to_json()
        outcomes = [assess_requirements(RunEvidence.from_json(original), {"R": "check"})
                    for _ in range(3)]
        self.assertEqual(calls, ["executed"])
        self.assertTrue(all(item == outcomes[0] for item in outcomes))
        self.assertEqual(evidence.to_json(), original)
