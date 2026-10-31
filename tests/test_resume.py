"""Bounded resume tests: only a durable pending suffix may execute."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from chimera import (JournalConflict, JournalPlan, JournalTask,
                     inspect_interrupted, resume_journaled, run_journaled)
from chimera.journal import _OwnedJournal


@unittest.skipUnless(sys.platform == "linux", "Journal ownership currently requires Linux")
class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name, "journal.sqlite")

    def _interrupt_after_terminal(self, tasks, task_id="a"):
        run_id = str(uuid4())
        original = _OwnedJournal.transition

        def transition(journal, current_run, current_task, expected, state,
                       value_json=None, error=None):
            original(journal, current_run, current_task, expected, state,
                     value_json=value_json, error=error)
            if current_task == task_id and state in ("succeeded", "failed", "blocked"):
                raise KeyboardInterrupt

        with patch("chimera.journal._OwnedJournal.transition", new=transition):
            with self.assertRaises(KeyboardInterrupt):
                run_journaled(self.path, tasks, run_id=run_id)
        return run_id

    def test_resume_preserves_terminal_prefix_and_runs_pending_suffix(self):
        calls = []
        initial = [JournalTask("a", lambda: calls.append("a") or {"saved": 1}, "a:v1"),
                   JournalTask("b", lambda: calls.append("b") or True, "b:v1", ("a",))]
        run_id = self._interrupt_after_terminal(initial)
        self.assertEqual(calls, ["a"])
        recovered = inspect_interrupted(
            self.path, run_id, JournalPlan.from_tasks(initial))
        self.assertEqual(recovered.state, "needs_attention")
        self.assertEqual([task.state for task in recovered.tasks], ["succeeded", "pending"])

        resumed = [JournalTask("a", lambda: self.fail("terminal task repeated"), "a:v1"),
                   JournalTask("b", lambda: calls.append("b") or True, "b:v1", ("a",))]
        result = resume_journaled(self.path, run_id, resumed)
        self.assertEqual(calls, ["a", "b"])
        self.assertEqual(result.state, "completed")
        self.assertEqual([(task.task_id, task.state, task.value) for task in result.tasks],
                         [("a", "succeeded", {"saved": 1}),
                          ("b", "succeeded", True)])

    def test_resume_refuses_any_unknown_running_task_without_callbacks(self):
        calls = []
        tasks = [JournalTask("a", lambda: (_ for _ in ()).throw(KeyboardInterrupt()), "a:v1"),
                 JournalTask("b", lambda: calls.append("b"), "b:v1")]
        run_id = str(uuid4())
        with self.assertRaises(KeyboardInterrupt):
            run_journaled(self.path, tasks, run_id=run_id)
        with self.assertRaisesRegex(JournalConflict, "Unknown running task"):
            resume_journaled(self.path, run_id, tasks)
        self.assertEqual(calls, [])
        # Refusal itself persists attention; no separate inspection is needed.
        import sqlite3
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT state FROM journal_runs WHERE run_id=?", (run_id,)
            ).fetchone()[0], "needs_attention")
        inspection = inspect_interrupted(self.path, run_id, JournalPlan.from_tasks(tasks))
        self.assertEqual(inspection.state, "needs_attention")
        self.assertEqual([task.state for task in inspection.tasks], ["running", "pending"])

    def test_prior_failure_blocks_descendant_but_independent_pending_runs(self):
        calls = []
        tasks = [
            JournalTask("a", lambda: (_ for _ in ()).throw(RuntimeError("expected")), "a:v1"),
            JournalTask("b", lambda: calls.append("b"), "b:v1", ("a",)),
            JournalTask("c", lambda: calls.append("c") or False, "c:v1"),
        ]
        run_id = self._interrupt_after_terminal(tasks)
        resumed = [
            JournalTask("a", lambda: self.fail("failed task repeated"), "a:v1"),
            JournalTask("b", lambda: calls.append("b"), "b:v1", ("a",)),
            JournalTask("c", lambda: calls.append("c") or False, "c:v1"),
        ]
        result = resume_journaled(self.path, run_id, resumed)
        self.assertEqual(calls, ["c"])
        self.assertEqual([(task.task_id, task.state) for task in result.tasks],
                         [("a", "failed"), ("c", "succeeded"), ("b", "blocked")])
        self.assertIs(result.tasks[1].value, False)

    def test_changed_plan_is_rejected_before_callbacks(self):
        calls = []
        tasks = [JournalTask("a", lambda: True, "a:v1"),
                 JournalTask("b", lambda: calls.append("b"), "b:v1")]
        run_id = self._interrupt_after_terminal(tasks)
        changed = [JournalTask("a", lambda: calls.append("a"), "a:v2"),
                   JournalTask("b", lambda: calls.append("b"), "b:v1")]
        with self.assertRaisesRegex(JournalConflict, "plan does not match"):
            resume_journaled(self.path, run_id, changed)
        self.assertEqual(calls, [])

    def test_completed_resume_is_callback_free_and_idempotent(self):
        result = run_journaled(
            self.path, [JournalTask("a", lambda: 1, "a:v1")])
        reopened = resume_journaled(
            self.path, result.run_id,
            [JournalTask("a", lambda: self.fail("completed task repeated"), "a:v1")],
        )
        self.assertEqual(reopened, result)

    def test_interrupt_during_resumed_callback_leaves_unknown_and_pending(self):
        initial = [JournalTask("a", lambda: True, "a:v1"),
                   JournalTask("b", lambda: None, "b:v1"),
                   JournalTask("c", lambda: None, "c:v1")]
        run_id = self._interrupt_after_terminal(initial)
        resumed = [JournalTask("a", lambda: self.fail("repeated"), "a:v1"),
                   JournalTask("b", lambda: (_ for _ in ()).throw(KeyboardInterrupt()), "b:v1"),
                   JournalTask("c", lambda: self.fail("later task ran"), "c:v1")]
        with self.assertRaises(KeyboardInterrupt):
            resume_journaled(self.path, run_id, resumed)
        inspection = inspect_interrupted(
            self.path, run_id, JournalPlan.from_tasks(resumed))
        self.assertEqual(inspection.state, "needs_attention")
        self.assertEqual([task.state for task in inspection.tasks],
                         ["succeeded", "running", "pending"])

    def test_nonfinite_resumed_result_stops_before_later_task(self):
        calls = []
        initial = [JournalTask("a", lambda: True, "a:v1"),
                   JournalTask("b", lambda: None, "b:v1"),
                   JournalTask("c", lambda: None, "c:v1")]
        run_id = self._interrupt_after_terminal(initial)
        resumed = [JournalTask("a", lambda: self.fail("repeated"), "a:v1"),
                   JournalTask("b", lambda: float("nan"), "b:v1"),
                   JournalTask("c", lambda: calls.append("c"), "c:v1")]
        from chimera import JournalError
        with self.assertRaises(JournalError):
            resume_journaled(self.path, run_id, resumed)
        self.assertEqual(calls, [])
        inspection = inspect_interrupted(
            self.path, run_id, JournalPlan.from_tasks(resumed))
        self.assertEqual([task.state for task in inspection.tasks],
                         ["succeeded", "running", "pending"])

    def test_resume_ownership_excludes_competing_recovery_during_callback(self):
        initial = [JournalTask("a", lambda: True, "a:v1"),
                   JournalTask("b", lambda: None, "b:v1")]
        run_id = self._interrupt_after_terminal(initial)

        def owned_callback():
            code = (
                "from chimera import JournalTask,resume_journaled; import sys; "
                "resume_journaled(sys.argv[1],sys.argv[2],["
                "JournalTask('a',lambda:None,'a:v1'),"
                "JournalTask('b',lambda:None,'b:v1')])"
            )
            other = subprocess.run(
                [sys.executable, "-c", code, str(self.path), run_id],
                capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(other.returncode, 0)
            self.assertIn("OwnershipBusy", other.stderr)
            return True

        result = resume_journaled(self.path, run_id, [
            JournalTask("a", lambda: self.fail("repeated"), "a:v1"),
            JournalTask("b", owned_callback, "b:v1"),
        ])
        self.assertEqual(result.state, "completed")

    def test_process_reopen_resumes_after_terminal_commit_crash(self):
        run_id = str(uuid4())
        marker = Path(self.temp.name, "marker")
        code = r'''\
import os, sys
from pathlib import Path
from chimera import JournalTask, run_journaled
from chimera.journal import _OwnedJournal
original = _OwnedJournal.transition
def transition(self, run_id, task_id, expected, state, value_json=None, error=None):
    original(self, run_id, task_id, expected, state, value_json=value_json, error=error)
    if task_id == "a" and state == "succeeded":
        os.kill(os.getpid(), 9)
_OwnedJournal.transition = transition
run_journaled(sys.argv[1], [
    JournalTask("a", lambda: Path(sys.argv[3]).write_text("a", encoding="utf-8") or True, "a:v1"),
    JournalTask("b", lambda: None, "b:v1", ("a",)),
], run_id=sys.argv[2])
'''
        child = subprocess.run(
            [sys.executable, "-c", code, str(self.path), run_id, str(marker)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(child.returncode, 0)
        calls = []
        result = resume_journaled(self.path, run_id, [
            JournalTask("a", lambda: self.fail("a repeated"), "a:v1"),
            JournalTask("b", lambda: calls.append("b") or "done", "b:v1", ("a",)),
        ])
        self.assertEqual(marker.read_text(encoding="utf-8"), "a")
        self.assertEqual(calls, ["b"])
        self.assertEqual(result.state, "completed")

    def test_killed_resumed_callback_releases_owner_but_stays_unknown(self):
        initial = [JournalTask("a", lambda: True, "a:v1"),
                   JournalTask("b", lambda: None, "b:v1"),
                   JournalTask("c", lambda: None, "c:v1")]
        run_id = self._interrupt_after_terminal(initial)
        marker = Path(self.temp.name, "resumed-effect")
        code = r'''\
import os, sys
from pathlib import Path
from chimera import JournalTask, resume_journaled
def effect():
    Path(sys.argv[3]).write_text("once", encoding="utf-8")
    os.kill(os.getpid(), 9)
resume_journaled(sys.argv[1], sys.argv[2], [
    JournalTask("a", lambda: None, "a:v1"),
    JournalTask("b", effect, "b:v1"),
    JournalTask("c", lambda: None, "c:v1"),
])
'''
        child = subprocess.run(
            [sys.executable, "-c", code, str(self.path), run_id, str(marker)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(child.returncode, 0)
        calls = []
        with self.assertRaisesRegex(JournalConflict, "Unknown running task"):
            resume_journaled(self.path, run_id, [
                JournalTask("a", lambda: calls.append("a"), "a:v1"),
                JournalTask("b", lambda: calls.append("b"), "b:v1"),
                JournalTask("c", lambda: calls.append("c"), "c:v1"),
            ])
        self.assertEqual(marker.read_text(encoding="utf-8"), "once")
        self.assertEqual(calls, [])
