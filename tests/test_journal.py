"""Durable sequential journal and inspect-only recovery tests."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

from chimera import (JournalConflict, JournalError, JournalPlan, JournalTask,
                     inspect_interrupted, run_journaled)


@unittest.skipUnless(sys.platform == "linux", "Journal ownership currently requires Linux")
class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name, "journal.sqlite")

    def test_results_commit_before_next_task_and_detach_immediately(self):
        returned = {"samples": [1]}
        run_id = str(uuid4())

        def first():
            return returned

        def second():
            with sqlite3.connect(self.path) as db:
                row = db.execute(
                    "SELECT state,value_json FROM journal_tasks WHERE run_id=? AND task_id='a'",
                    (run_id,)).fetchone()
            self.assertEqual(row, ("succeeded", '{"samples":[1]}'))
            returned["samples"].append(2)
            return False

        tasks = [JournalTask("a", first, "fixture:first:v1"),
                 JournalTask("b", second, "fixture:second:v1", ("a",))]
        result = run_journaled(self.path, tasks, run_id=run_id)
        self.assertEqual(result.state, "completed")
        self.assertEqual(result.tasks[0].value, {"samples": [1]})
        self.assertEqual(result.tasks[1].value, False)

    def test_running_marker_is_visible_before_effect(self):
        run_id = str(uuid4())

        def action():
            with sqlite3.connect(self.path) as db:
                self.assertEqual(db.execute(
                    "SELECT state FROM journal_tasks WHERE run_id=? AND task_id='effect'",
                    (run_id,)).fetchone()[0], "running")
                self.assertEqual(db.execute(
                    "SELECT state FROM journal_runs WHERE run_id=?", (run_id,)
                ).fetchone()[0], "running")
            return "done"

        result = run_journaled(
            self.path, [JournalTask("effect", action, "fixture:effect:v1")], run_id=run_id)
        self.assertEqual(result.tasks[0].state, "succeeded")

    def test_second_runner_is_refused_while_callback_is_active(self):
        run_id = str(uuid4())
        code = """
import sys, time
from chimera import JournalTask, run_journaled
def wait():
    print('active', flush=True)
    time.sleep(60)
run_journaled(sys.argv[1], [JournalTask('wait', wait, 'fixture:wait:v1')], run_id=sys.argv[2])
"""
        child = subprocess.Popen([sys.executable, "-c", code, str(self.path), run_id],
                                 stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "active")
            other = subprocess.run(
                [sys.executable, "-c",
                 "from chimera import JournalPlan, JournalTask, inspect_interrupted; "
                 "import sys; inspect_interrupted(sys.argv[1],sys.argv[2],"
                 "JournalPlan.from_tasks([JournalTask('wait',lambda:None,'fixture:wait:v1')]))",
                 str(self.path), run_id], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(other.returncode, 0)
            self.assertIn("OwnershipBusy", other.stderr)
        finally:
            child.kill()
            child.wait(timeout=10)
            child.stdout.close()

    def test_killed_after_effect_recovers_unknown_without_callback(self):
        run_id = str(uuid4())
        counter = Path(self.temp.name, "counter")
        code = """
import os, sys
from pathlib import Path
from chimera import JournalTask, run_journaled
def effect():
    Path(sys.argv[3]).write_text('once', encoding='utf-8')
    print('effect', flush=True)
    os.kill(os.getpid(), 9)
run_journaled(sys.argv[1], [JournalTask('effect', effect, 'fixture:effect:v1')], run_id=sys.argv[2])
"""
        child = subprocess.run([sys.executable, "-c", code, str(self.path), run_id,
                                str(counter)], capture_output=True, text=True)
        self.assertNotEqual(child.returncode, 0)
        self.assertEqual(child.stdout.strip(), "effect")
        self.assertEqual(counter.read_text(encoding="utf-8"), "once")
        plan = JournalPlan.from_tasks(
            [JournalTask("effect", lambda: self.fail("callback executed"), "fixture:effect:v1")])
        recovered = inspect_interrupted(self.path, run_id, plan)
        self.assertEqual(recovered.state, "needs_attention")
        self.assertEqual(recovered.tasks[0].state, "running")
        self.assertEqual(inspect_interrupted(self.path, run_id, plan), recovered)
        self.assertEqual(counter.read_text(encoding="utf-8"), "once")

    def test_exception_blocks_descendant_and_continues_independent(self):
        calls = []
        tasks = [
            JournalTask("fail", lambda: (_ for _ in ()).throw(RuntimeError("no")), "fail:v1"),
            JournalTask("child", lambda: calls.append("child"), "child:v1", ("fail",)),
            JournalTask("other", lambda: calls.append("other") or True, "other:v1"),
        ]
        result = run_journaled(self.path, tasks)
        self.assertEqual([(task.task_id, task.state) for task in result.tasks],
                         [("fail", "failed"), ("other", "succeeded"), ("child", "blocked")])
        self.assertEqual(calls, ["other"])

    def test_serialization_error_stops_scheduling_and_recovery(self):
        calls = []
        tasks = [JournalTask("bad", lambda: {"bad": float("nan")}, "bad:v1"),
                 JournalTask("later", lambda: calls.append(1), "later:v1")]
        run_id = str(uuid4())
        with self.assertRaises(JournalError):
            run_journaled(self.path, tasks, run_id=run_id)
        self.assertEqual(calls, [])
        recovered = inspect_interrupted(self.path, run_id, JournalPlan.from_tasks(tasks))
        self.assertEqual(recovered.state, "needs_attention")
        self.assertEqual([task.state for task in recovered.tasks], ["running", "pending"])

    def test_interrupt_propagates_and_is_not_retried(self):
        tasks = [JournalTask("interrupt", lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
                             "interrupt:v1")]
        run_id = str(uuid4())
        with self.assertRaises(KeyboardInterrupt):
            run_journaled(self.path, tasks, run_id=run_id)
        inspection = inspect_interrupted(self.path, run_id, JournalPlan.from_tasks(tasks))
        self.assertEqual(inspection.tasks[0].state, "running")

    def test_changed_plan_and_duplicate_run_are_rejected(self):
        run_id = str(uuid4())
        tasks = [JournalTask("a", lambda: 1, "a:v1")]
        run_journaled(self.path, tasks, run_id=run_id)
        changed = JournalPlan.from_tasks([JournalTask("a", lambda: 1, "a:v2")])
        with self.assertRaises(JournalConflict):
            inspect_interrupted(self.path, run_id, changed)
        with self.assertRaises(JournalConflict):
            run_journaled(self.path, tasks, run_id=run_id)

    def test_corrupt_state_and_schema_fail_closed(self):
        tasks = [JournalTask("a", lambda: 1, "a:v1")]
        run_id = str(uuid4())
        run_journaled(self.path, tasks, run_id=run_id)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE journal_tasks SET state='mystery' WHERE run_id=?", (run_id,))
        with self.assertRaises(JournalError):
            inspect_interrupted(self.path, run_id, JournalPlan.from_tasks(tasks))

    def test_corrupt_dependency_json_and_timestamps_fail_closed(self):
        tasks = [JournalTask("a", lambda: {"a": 2, "z": 1}, "a:v1"),
                 JournalTask("b", lambda: True, "b:v1", ("a",))]
        plan = JournalPlan.from_tasks(tasks)
        mutations = [
            "UPDATE journal_tasks SET state='blocked',value_json=NULL,error='forged' "
            "WHERE task_id='b'",
            "UPDATE journal_tasks SET value_json=' {\"z\":1, \"a\":2}' WHERE task_id='a'",
            "UPDATE journal_runs SET finished_at=NULL",
            "UPDATE journal_runs SET started_at='2030-01-01',finished_at='2020-01-01'",
            "UPDATE journal_tasks SET state='pending',value_json=NULL,error=NULL "
            "WHERE task_id='a'",
            "UPDATE journal_tasks SET state='running',value_json=NULL,error=NULL",
        ]
        for statement in mutations:
            with self.subTest(statement=statement):
                if self.path.exists():
                    self.path.unlink()
                run_id = str(uuid4())
                run_journaled(self.path, tasks, run_id=run_id)
                with sqlite3.connect(self.path) as db:
                    db.execute(statement)
                with self.assertRaises(JournalError):
                    inspect_interrupted(self.path, run_id, plan)

    def test_plan_is_canonical_and_requires_operation_identity(self):
        first = JournalPlan.from_tasks([
            JournalTask("b", lambda: 2, "b:v1", ("a",)),
            JournalTask("a", lambda: 1, "a:v1"),
        ])
        second = JournalPlan.from_json(first.to_json())
        self.assertEqual(second, first)
        self.assertEqual([task.task_id for task in first.tasks], ["a", "b"])
        with self.assertRaises(JournalError):
            JournalPlan.from_tasks([JournalTask("a", lambda: 1, "")])
        malformed = json.dumps({"schema_version": 1, "tasks": []})
        with self.assertRaises(JournalError):
            JournalPlan.from_json(malformed)

    def test_empty_plan_completes(self):
        result = run_journaled(self.path, [])
        self.assertEqual(result.state, "completed")
        self.assertEqual(result.tasks, ())
