import json
import unittest

from chimera import EvidenceError, RunEvidence, Task, run_with_evidence


class EvidenceTests(unittest.TestCase):
    def test_round_trip(self):
        evidence = run_with_evidence([Task("measure", lambda: {"margin_db": [2.0, 3.0]})])
        self.assertEqual(RunEvidence.from_json(evidence.to_json()), evidence)
        document = evidence.to_dict()
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["tasks"][0]["value"], {"margin_db": [2.0, 3.0]})
        self.assertLessEqual(document["started_at"], document["finished_at"])

    def test_snapshot_is_detached(self):
        value = {"samples": [1, 2]}
        evidence = run_with_evidence([Task("a", lambda: value)])
        value["samples"].append(3)
        evidence.to_dict()["tasks"][0]["value"]["samples"].append(4)
        self.assertEqual(evidence.to_dict()["tasks"][0]["value"], {"samples": [1, 2]})

    def test_failed_blocked_and_independent(self):
        def fail():
            raise ValueError("synthetic failure")
        evidence = run_with_evidence([
            Task("fail", fail), Task("blocked", lambda: self.fail("ran"), ("fail",)),
            Task("independent", lambda: 42),
        ])
        tasks = {task["task_id"]: task for task in evidence.to_dict()["tasks"]}
        self.assertEqual(tasks["fail"]["error"], "ValueError: synthetic failure")
        self.assertEqual(tasks["blocked"]["status"], "blocked")
        self.assertEqual(tasks["blocked"]["dependencies"], ["fail"])
        self.assertEqual(tasks["independent"]["value"], 42)
        self.assertEqual(RunEvidence.from_json(evidence.to_json()), evidence)

    def test_reject_lossy_values(self):
        circular = []
        circular.append(circular)
        for value in (object(), {1: "key"}, (1, 2), float("nan"), float("inf"), circular):
            with self.subTest(value=type(value)), self.assertRaises(EvidenceError):
                run_with_evidence([Task("a", lambda: value)])

    def test_reject_invalid_document(self):
        valid = run_with_evidence([Task("a", lambda: 1)]).to_dict()
        mutations = [
            {"schema_version": 2}, {"schema_version": True}, {"run_id": "invalid"},
            {"started_at": "2026-09-12T00:00:00"}, {"finished_at": "2000-01-01T00:00:00Z"},
            {"tasks": {}}, {"unknown": 1},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(EvidenceError):
                RunEvidence.from_json(json.dumps(valid | mutation))
        for text in ('{}', 'null', '{', '{"schema_version":1,"schema_version":1}'):
            with self.subTest(text=text), self.assertRaises(EvidenceError):
                RunEvidence.from_json(text)

    def test_empty_and_generator(self):
        first = run_with_evidence([]).to_dict()
        self.assertEqual(first["tasks"], [])
        self.assertNotEqual(first["run_id"], run_with_evidence([]).to_dict()["run_id"])
        self.assertEqual(len(run_with_evidence(Task(str(i), lambda: None) for i in range(2)).to_dict()["tasks"]), 2)

    def test_preflight_and_interrupt(self):
        observed = []
        with self.assertRaises(ValueError):
            run_with_evidence([Task("a", lambda: observed.append(1), ("missing",))])
        self.assertEqual(observed, [])
        for exception in (KeyboardInterrupt, SystemExit):
            def interrupt():
                raise exception()
            with self.subTest(exception=exception), self.assertRaises(exception):
                run_with_evidence([Task("a", interrupt)])


if __name__ == "__main__":
    unittest.main()
