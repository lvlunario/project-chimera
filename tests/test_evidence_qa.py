"""Independent AI QA: adversarial checks of the P1 evidence contract."""
import json
import unittest

from chimera import Task
from chimera.evidence import EvidenceError, RunEvidence, run_with_evidence


class EvidenceQATests(unittest.TestCase):
    def fixture(self):
        return run_with_evidence([
            Task("source", lambda: {"samples": [0, False, None, "μV", 1.5]}),
            Task("verify", lambda: True, ("source",)),
        ]).to_dict()

    def reject(self, payload):
        with self.assertRaises(EvidenceError):
            RunEvidence.from_json(json.dumps(payload))

    def test_nested_json_values_round_trip(self):
        payload = self.fixture()
        restored = RunEvidence.from_json(json.dumps(payload)).to_dict()
        self.assertEqual(restored, payload)

    def test_non_json_values_rejected_without_coercion(self):
        class IntSubclass(int):
            pass
        circular = []
        circular.append(circular)
        for value in [(1, 2), {1: "bad key"}, {"a": float("nan")},
                      float("inf"), float("-inf"), object(), IntSubclass(1), circular]:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(EvidenceError):
                    run_with_evidence([Task("source", lambda: value)])

    def test_malformed_json_rejected(self):
        for text in ["", "{", "null", "[]", "42", '"evidence"']:
            with self.subTest(text=text), self.assertRaises(EvidenceError):
                RunEvidence.from_json(text)

    def test_unknown_fields_rejected(self):
        payload = self.fixture()
        payload["unrecognized"] = 1
        self.reject(payload)
        payload = self.fixture()
        payload["tasks"][0]["unrecognized"] = 1
        self.reject(payload)

    def test_duplicate_or_blank_task_ids_rejected(self):
        for bad_id in ["source", "", " ", 42, None]:
            with self.subTest(bad_id=bad_id):
                payload = self.fixture()
                payload["tasks"][1]["task_id"] = bad_id
                self.reject(payload)

    def test_dependency_order_and_missing_parent_rejected(self):
        for dependencies in [["verify"], ["missing"], ["source"], "source", [7]]:
            with self.subTest(dependencies=dependencies):
                payload = self.fixture()
                payload["tasks"][0]["dependencies"] = dependencies
                self.reject(payload)

    def test_status_and_error_consistency_rejected(self):
        for status, error, value in [
            ("unknown", None, None), ("succeeded", "failure", None),
            ("failed", None, None), ("failed", "error", 123),
            ("blocked", "error", None), (True, None, None),
        ]:
            with self.subTest(status=status, error=error, value=value):
                payload = self.fixture()
                payload["tasks"][0].update(status=status, error=error, value=value)
                self.reject(payload)

    def test_success_with_failed_dependency_rejected(self):
        payload = self.fixture()
        payload["tasks"][0].update(status="failed", error="ValueError: bad", value=None)
        self.reject(payload)

    def test_failed_and_blocked_results_round_trip(self):
        def fail():
            raise ValueError("injected")
        evidence = run_with_evidence([
            Task("source", fail),
            Task("verify", lambda: self.fail("blocked action executed"), ("source",)),
            Task("independent", lambda: 42),
        ])
        restored = RunEvidence.from_json(evidence.to_json()).to_dict()
        statuses = {task["task_id"]: task["status"] for task in restored["tasks"]}
        self.assertEqual(statuses, {"source": "failed", "verify": "blocked", "independent": "succeeded"})

    def test_control_flow_interrupts_are_not_completed_evidence(self):
        for exception_type in [KeyboardInterrupt, SystemExit]:
            def interrupt():
                raise exception_type()
            with self.subTest(exception_type=exception_type), self.assertRaises(exception_type):
                run_with_evidence([Task("interrupt", interrupt)])

    def test_graph_validation_precedes_actions(self):
        observed = []
        with self.assertRaises(ValueError):
            run_with_evidence([
                Task("valid", lambda: observed.append("ran")),
                Task("invalid", lambda: None, ("missing",)),
            ])
        self.assertEqual(observed, [])

    def test_nonfinite_json_input_rejected(self):
        for value in [float("nan"), float("inf"), float("-inf")]:
            with self.subTest(value=value):
                payload = self.fixture()
                payload["tasks"][0]["value"] = {"reading": value}
                self.reject(payload)

    def test_caller_dependency_mutation_cannot_change_validated_plan(self):
        dependencies = ["source"]
        def fail_and_mutate():
            dependencies.clear()
            raise ValueError("injected")
        evidence = run_with_evidence([
            Task("source", fail_and_mutate),
            Task("verify", lambda: self.fail("mutated plan ran blocked action"), dependencies),
        ])
        tasks = {task["task_id"]: task for task in evidence.to_dict()["tasks"]}
        self.assertEqual(tasks["verify"]["status"], "blocked")
        self.assertEqual(tasks["verify"]["dependencies"], ["source"])

    def test_duplicate_nested_json_keys_rejected(self):
        document = run_with_evidence([Task("source", lambda: {"unique": 42})]).to_json()
        document = document.replace('"unique": 42', '"unique": 42, "unique": 43')
        with self.assertRaises(EvidenceError):
            RunEvidence.from_json(document)


if __name__ == "__main__":
    unittest.main()
