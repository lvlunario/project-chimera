from dataclasses import FrozenInstanceError
import unittest

from chimera import RunEvidence, Task, assess_requirements, run_with_evidence


class VerdictTests(unittest.TestCase):
    def test_boolean_verdicts_and_report_continuation(self):
        evidence = run_with_evidence([
            Task("pass", lambda: True), Task("fail", lambda: False),
            Task("report", lambda: "handoff", ("fail",)),
        ])
        assessment = assess_requirements(evidence, {"R2": "fail", "R1": "pass"})
        self.assertEqual([item.verdict for item in assessment.outcomes], ["pass", "fail"])
        self.assertEqual([item.requirement_id for item in assessment.outcomes], ["R1", "R2"])
        self.assertFalse(assessment.all_passed)
        self.assertEqual(evidence.to_dict()["tasks"][-1]["status"], "succeeded")

    def test_error_blocked_and_missing(self):
        def broken():
            raise ValueError("invalid samples")
        evidence = run_with_evidence([
            Task("broken", broken), Task("blocked", lambda: True, ("broken",)),
        ])
        assessment = assess_requirements(evidence, {
            "R1": "broken", "R2": "blocked", "R3": "absent",
        })
        self.assertEqual([item.verdict for item in assessment.outcomes],
                         ["error", "not_evaluated", "not_evaluated"])
        self.assertIn("ValueError: invalid samples", assessment.outcomes[0].reason)
        self.assertFalse(assessment.all_passed)

    def test_non_boolean_values_are_errors(self):
        for value in (None, 0, 1, 1.0, "pass", "", [], [True], {}, {"verdict": "pass"}):
            with self.subTest(value=value):
                evidence = run_with_evidence([Task("check", lambda: value)])
                assessment = assess_requirements(evidence, {"R1": "check"})
                self.assertEqual(assessment.outcomes[0].verdict, "error")
                self.assertFalse(assessment.all_passed)

    def test_empty_is_not_pass(self):
        evidence = run_with_evidence([])
        self.assertFalse(assess_requirements(evidence, {}).all_passed)
        self.assertFalse(assess_requirements(evidence, {"R1": "missing"}).all_passed)

    def test_complete_pass(self):
        evidence = run_with_evidence([Task("check", lambda: True)])
        self.assertTrue(assess_requirements(evidence, {"R1": "check"}).all_passed)

    def test_round_trip_does_not_execute(self):
        calls = []
        def check():
            calls.append(1)
            return False
        evidence = run_with_evidence([Task("check", check)])
        original = evidence.to_json()
        before = assess_requirements(evidence, {"R1": "check"})
        after = assess_requirements(RunEvidence.from_json(original), {"R1": "check"})
        self.assertEqual(before, after)
        self.assertEqual(before.run_id, evidence.to_dict()["run_id"])
        self.assertEqual(calls, [1])
        self.assertEqual(evidence.to_json(), original)

    def test_invalid_bindings(self):
        evidence = run_with_evidence([])
        for bindings in ({"": "task"}, {"R": " "}, {1: "task"}, {"R": None}):
            with self.subTest(bindings=bindings), self.assertRaises(ValueError):
                assess_requirements(evidence, bindings)
        with self.assertRaises(TypeError):
            assess_requirements(evidence, [("R", "task")])
        with self.assertRaises(TypeError):
            assess_requirements({}, {})

    def test_binding_copy_and_immutable_result(self):
        evidence = run_with_evidence([Task("check", lambda: True)])
        bindings = {"R": "check"}
        assessment = assess_requirements(evidence, bindings)
        bindings["R"] = "missing"
        self.assertEqual(assessment.outcomes[0].task_id, "check")
        with self.assertRaises(FrozenInstanceError):
            assessment.outcomes[0].verdict = "fail"
        with self.assertRaises(FrozenInstanceError):
            assessment.run_id = "changed"
