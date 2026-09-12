import unittest

from chimera import Task, run


class EngineTests(unittest.TestCase):
    def test_order(self):
        observed = []
        results = run([
            Task("c", lambda: observed.append("c"), ("a", "b")),
            Task("b", lambda: observed.append("b")),
            Task("a", lambda: observed.append("a")),
        ])
        self.assertEqual(observed, ["a", "b", "c"])
        self.assertTrue(all(r.status == "succeeded" for r in results.values()))

    def test_invalid_ids(self):
        for tasks in ([Task("", lambda: None)], [Task(" ", lambda: None)],
                      [Task("a", lambda: None), Task("a", lambda: None)]):
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                run(tasks)

    def test_missing_dependency(self):
        observed = []
        with self.assertRaisesRegex(ValueError, "missing dependency"):
            run([Task("a", lambda: observed.append("a")), Task("b", lambda: None, ("missing",))])
        self.assertEqual(observed, [])

    def test_cycle_preflight(self):
        observed = []
        with self.assertRaisesRegex(ValueError, "cycle"):
            run([Task("free", lambda: observed.append("free")),
                 Task("a", lambda: None, ("b",)), Task("b", lambda: None, ("a",))])
        self.assertEqual(observed, [])

    def test_failure_propagates(self):
        def fail():
            raise ValueError("fixture failure")
        def must_not_run():
            self.fail("Blocked task executed")
        results = run([Task("a", fail), Task("b", must_not_run, ("a",)),
                       Task("c", must_not_run, ("b",)), Task("independent", lambda: 42)])
        self.assertEqual(results["a"].status, "failed")
        self.assertEqual(results["a"].error, "ValueError: fixture failure")
        self.assertEqual(results["b"].status, "blocked")
        self.assertEqual(results["c"].status, "blocked")
        self.assertEqual(results["independent"].value, 42)

    def test_interrupt(self):
        def interrupt():
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            run([Task("interrupt", interrupt)])

    def test_empty(self):
        self.assertEqual(run([]), {})

    def test_invalid_action(self):
        with self.assertRaisesRegex(ValueError, "callable"):
            run([Task("bad", None)])

    def test_self_cycle(self):
        with self.assertRaisesRegex(ValueError, "cycle"):
            run([Task("a", lambda: None, ("a",))])


if __name__ == "__main__":
    unittest.main()
