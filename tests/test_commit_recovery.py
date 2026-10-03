"""Ambiguous SQLite commit reconciliation and no-duplicate-effect tests."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from chimera import (JournalCommitUncertain, JournalError, JournalPlan,
                     JournalStorageUnavailable, JournalTask,
                     inspect_interrupted, resume_journaled, run_journaled)
from chimera.journal import _OwnedJournal


@unittest.skipUnless(sys.platform == "linux", "Journal ownership currently requires Linux")
class CommitRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name, "journal.sqlite")

    def _transition_fault(self, task_id, state, *, after_commit):
        original = _OwnedJournal.transition
        injected = False

        def transition(journal, run_id, current_task, expected, current_state,
                       value_json=None, error=None):
            nonlocal injected
            matches = current_task == task_id and current_state == state and not injected
            if matches and not after_commit:
                injected = True
                raise sqlite3.OperationalError("injected before commit")
            original(journal, run_id, current_task, expected, current_state,
                     value_json=value_json, error=error)
            if matches:
                injected = True
                raise sqlite3.OperationalError("injected after commit")

        return patch("chimera.journal._OwnedJournal.transition", new=transition)

    def test_running_marker_before_commit_is_retried_before_one_callback(self):
        calls = []
        with self._transition_fault("a", "running", after_commit=False):
            result = run_journaled(
                self.path, [JournalTask("a", lambda: calls.append("a") or 1, "a:v1")]
            )
        self.assertEqual(calls, ["a"])
        self.assertEqual(result.tasks[0].state, "succeeded")

    def test_running_marker_after_commit_reopens_before_one_callback(self):
        calls = []
        with self._transition_fault("a", "running", after_commit=True):
            result = run_journaled(
                self.path, [JournalTask("a", lambda: calls.append("a") or 1, "a:v1")]
            )
        self.assertEqual(calls, ["a"])
        self.assertEqual(result.state, "completed")

    def test_terminal_after_commit_continues_without_repeating_callback(self):
        calls = []
        tasks = [JournalTask("a", lambda: calls.append("a") or {"answer": 1}, "a:v1"),
                 JournalTask("b", lambda: calls.append("b") or True, "b:v1")]
        with self._transition_fault("a", "succeeded", after_commit=True):
            result = run_journaled(self.path, tasks)
        self.assertEqual(calls, ["a", "b"])
        self.assertEqual([task.state for task in result.tasks], ["succeeded", "succeeded"])

    def test_terminal_before_commit_stops_and_persists_attention(self):
        calls = []
        run_id = str(uuid4())
        tasks = [JournalTask("a", lambda: calls.append("a") or 1, "a:v1"),
                 JournalTask("b", lambda: calls.append("b"), "b:v1")]
        with self._transition_fault("a", "succeeded", after_commit=False):
            with self.assertRaises(JournalCommitUncertain) as caught:
                run_journaled(self.path, tasks, run_id=run_id)
        self.assertEqual(calls, ["a"])
        self.assertTrue(caught.exception.durable_attention)
        self.assertEqual(caught.exception.last_verified_state, "running")
        inspection = inspect_interrupted(self.path, run_id, JournalPlan.from_tasks(tasks))
        self.assertEqual(inspection.state, "needs_attention")
        self.assertEqual([task.state for task in inspection.tasks], ["running", "pending"])
        with self.assertRaisesRegex(Exception, "Unknown running task"):
            resume_journaled(self.path, run_id, tasks)
        self.assertEqual(calls, ["a"])

    def test_failed_terminal_after_commit_is_reconciled_exactly(self):
        def fail():
            raise ValueError("expected")

        tasks = [JournalTask("a", fail, "a:v1"),
                 JournalTask("b", lambda: self.fail("blocked callback ran"),
                             "b:v1", ("a",))]
        with self._transition_fault("a", "failed", after_commit=True):
            result = run_journaled(self.path, tasks)
        self.assertEqual([task.state for task in result.tasks], ["failed", "blocked"])
        self.assertEqual(result.tasks[0].error, "ValueError: expected")

    def test_wrong_terminal_payload_is_not_accepted_as_intended_commit(self):
        original = _OwnedJournal.transition
        injected = False
        calls = []
        run_id = str(uuid4())

        def transition(journal, run_id, task_id, expected, state,
                       value_json=None, error=None):
            nonlocal injected
            if task_id == "a" and state == "succeeded" and not injected:
                injected = True
                original(journal, run_id, task_id, expected, state,
                         value_json='{"answer":2}', error=error)
                raise sqlite3.OperationalError("injected conflicting commit")
            original(journal, run_id, task_id, expected, state,
                     value_json=value_json, error=error)

        tasks = [JournalTask("a", lambda: calls.append("a") or {"answer": 1}, "a:v1"),
                 JournalTask("b", lambda: calls.append("b"), "b:v1")]
        with patch("chimera.journal._OwnedJournal.transition", new=transition):
            with self.assertRaisesRegex(JournalError, "conflicts with the intended"):
                run_journaled(self.path, tasks, run_id=run_id)
        self.assertEqual(calls, ["a"])
        inspection = inspect_interrupted(self.path, run_id, JournalPlan.from_tasks(tasks))
        self.assertEqual(inspection.state, "commit_conflict")
        with self.assertRaisesRegex(Exception, "Commit-conflicted run cannot resume"):
            resume_journaled(self.path, run_id, tasks)
        self.assertEqual(calls, ["a"])

    def test_run_creation_before_and_after_commit_are_reconciled(self):
        for after_commit in (False, True):
            with self.subTest(after_commit=after_commit):
                path = Path(self.temp.name, f"create-{after_commit}.sqlite")
                original = _OwnedJournal.create
                injected = False
                calls = []

                def create(journal, run_id, plan):
                    nonlocal injected
                    if not injected and not after_commit:
                        injected = True
                        raise sqlite3.OperationalError("injected before create")
                    original(journal, run_id, plan)
                    if not injected:
                        injected = True
                        raise sqlite3.OperationalError("injected after create")

                with patch("chimera.journal._OwnedJournal.create", new=create):
                    result = run_journaled(
                        path,
                        [JournalTask("a", lambda: calls.append("a") or True, "a:v1")],
                    )
                self.assertEqual(calls, ["a"])
                self.assertEqual(result.state, "completed")

    def test_resume_claim_before_and_after_commit_are_reconciled(self):
        for after_commit in (False, True):
            with self.subTest(after_commit=after_commit):
                path = Path(self.temp.name, f"claim-{after_commit}.sqlite")
                run_id = str(uuid4())
                calls = []
                tasks = [JournalTask("a", lambda: calls.append("a") or True, "a:v1"),
                         JournalTask("b", lambda: None, "b:v1")]
                original_transition = _OwnedJournal.transition

                def interrupt(journal, current_run, task_id, expected, state,
                              value_json=None, error=None):
                    original_transition(journal, current_run, task_id, expected, state,
                                        value_json=value_json, error=error)
                    if task_id == "a" and state == "succeeded":
                        raise KeyboardInterrupt

                with patch("chimera.journal._OwnedJournal.transition", new=interrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        run_journaled(path, tasks, run_id=run_id)
                inspect_interrupted(path, run_id, JournalPlan.from_tasks(tasks))
                original_prepare = _OwnedJournal.prepare_resume
                injected = False

                def prepare(journal, current_run, plan):
                    nonlocal injected
                    if not injected and not after_commit:
                        injected = True
                        raise sqlite3.OperationalError("injected before claim")
                    result = original_prepare(journal, current_run, plan)
                    if not injected:
                        injected = True
                        raise sqlite3.OperationalError("injected after claim")
                    return result

                resumed = [JournalTask("a", lambda: self.fail("prefix repeated"), "a:v1"),
                           JournalTask("b", lambda: calls.append("b") or True, "b:v1")]
                with patch("chimera.journal._OwnedJournal.prepare_resume", new=prepare):
                    result = resume_journaled(path, run_id, resumed)
                self.assertEqual(calls, ["a", "b"])
                self.assertEqual(result.state, "completed")

    def test_attention_inspection_before_and_after_commit_is_reconciled(self):
        for after_commit in (False, True):
            with self.subTest(after_commit=after_commit):
                path = Path(self.temp.name, f"inspect-{after_commit}.sqlite")
                run_id = str(uuid4())
                tasks = [JournalTask(
                    "a", lambda: (_ for _ in ()).throw(KeyboardInterrupt()), "a:v1"
                )]
                with self.assertRaises(KeyboardInterrupt):
                    run_journaled(path, tasks, run_id=run_id)
                original = _OwnedJournal.inspect
                injected = False

                def inspect(journal, current_run, plan, recover):
                    nonlocal injected
                    if recover and not injected and not after_commit:
                        injected = True
                        raise sqlite3.OperationalError("injected before inspection commit")
                    result = original(journal, current_run, plan, recover)
                    if recover and not injected:
                        injected = True
                        raise sqlite3.OperationalError("injected after inspection commit")
                    return result

                with patch("chimera.journal._OwnedJournal.inspect", new=inspect):
                    result = inspect_interrupted(path, run_id, JournalPlan.from_tasks(tasks))
                self.assertEqual(result.state, "needs_attention")
                self.assertEqual(result.tasks[0].state, "running")

    def test_resumed_terminal_after_commit_does_not_repeat_prefix_or_callback(self):
        run_id = str(uuid4())
        calls = []
        initial = [JournalTask("a", lambda: calls.append("a") or True, "a:v1"),
                   JournalTask("b", lambda: calls.append("unexpected"), "b:v1")]
        original = _OwnedJournal.transition

        def interrupt(journal, current_run, task_id, expected, state,
                      value_json=None, error=None):
            original(journal, current_run, task_id, expected, state,
                     value_json=value_json, error=error)
            if task_id == "a" and state == "succeeded":
                raise KeyboardInterrupt

        with patch("chimera.journal._OwnedJournal.transition", new=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_journaled(self.path, initial, run_id=run_id)
        inspect_interrupted(self.path, run_id, JournalPlan.from_tasks(initial))
        resumed = [JournalTask("a", lambda: self.fail("terminal prefix repeated"), "a:v1"),
                   JournalTask("b", lambda: calls.append("b") or True, "b:v1")]
        with self._transition_fault("b", "succeeded", after_commit=True):
            result = resume_journaled(self.path, run_id, resumed)
        self.assertEqual(calls, ["a", "b"])
        self.assertEqual(result.state, "completed")

    def test_finish_before_and_after_commit_are_callback_free(self):
        for after_commit in (False, True):
            with self.subTest(after_commit=after_commit):
                path = Path(self.temp.name, f"finish-{after_commit}.sqlite")
                calls = []
                original = _OwnedJournal.finish
                injected = False

                def finish(journal, run_id):
                    nonlocal injected
                    if not injected and not after_commit:
                        injected = True
                        raise sqlite3.OperationalError("injected before finish")
                    original(journal, run_id)
                    if not injected:
                        injected = True
                        raise sqlite3.OperationalError("injected after finish")

                with patch("chimera.journal._OwnedJournal.finish", new=finish):
                    result = run_journaled(
                        path,
                        [JournalTask("a", lambda: calls.append("a") or True, "a:v1")],
                    )
                self.assertEqual(calls, ["a"])
                self.assertEqual(result.state, "completed")

    def test_missing_storage_never_claims_attention_or_runs_callback(self):
        original = _OwnedJournal.transition
        removed = False
        calls = []

        def transition(journal, run_id, task_id, expected, state,
                       value_json=None, error=None):
            nonlocal removed
            if state == "running" and not removed:
                removed = True
                assert journal.db is not None
                journal.db.close()
                journal.db = None
                self.path.unlink()
                raise sqlite3.OperationalError("connection lost")
            original(journal, run_id, task_id, expected, state,
                     value_json=value_json, error=error)

        with patch("chimera.journal._OwnedJournal.transition", new=transition):
            with self.assertRaisesRegex(
                    JournalStorageUnavailable, "durable state was not verified"):
                run_journaled(
                    self.path,
                    [JournalTask("a", lambda: calls.append("a"), "a:v1")],
                )
        self.assertEqual(calls, [])
        self.assertFalse(self.path.exists())

    def test_terminal_connection_loss_never_claims_attention(self):
        original = _OwnedJournal.transition
        removed = False
        calls = []

        def transition(journal, run_id, task_id, expected, state,
                       value_json=None, error=None):
            nonlocal removed
            if state == "succeeded" and not removed:
                removed = True
                self.path.unlink()
                raise sqlite3.OperationalError("terminal connection lost")
            original(journal, run_id, task_id, expected, state,
                     value_json=value_json, error=error)

        tasks = [JournalTask("a", lambda: calls.append("a") or True, "a:v1"),
                 JournalTask("b", lambda: calls.append("b"), "b:v1")]
        with patch("chimera.journal._OwnedJournal.transition", new=transition):
            with self.assertRaises(JournalStorageUnavailable) as caught:
                run_journaled(self.path, tasks)
        self.assertNotIsInstance(caught.exception, JournalCommitUncertain)
        self.assertEqual(calls, ["a"])
        self.assertFalse(self.path.exists())
