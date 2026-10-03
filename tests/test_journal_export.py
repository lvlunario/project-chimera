"""Completed journal to schema-v1 evidence agreement tests."""
from pathlib import Path
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from chimera import (EvidenceStore, JournalConflict, JournalError, JournalPlan,
                     JournalStorageUnavailable, JournalTask, RequirementBindings,
                     RunEvidence, StorageConflict,
                     assess_requirements, export_journal_evidence,
                     inspect_interrupted, run_journaled)
from chimera.journal import _OwnedJournal
from chimera.ownership import DatabaseOwnership, OwnershipBusy


@unittest.skipUnless(sys.platform == "linux", "Journal ownership currently requires Linux")
class JournalExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name, "journal.sqlite")

    def test_completed_export_exactly_agrees_and_never_executes_again(self):
        calls = []

        def fail():
            calls.append("fail")
            raise ValueError("synthetic")

        tasks = [
            JournalTask("fail", fail, "export:fail:v1"),
            JournalTask("child", lambda: self.fail("blocked callback ran"),
                        "export:child:v1", ("fail",)),
            JournalTask("check", lambda: calls.append("check") or False,
                        "export:check:v1"),
        ]
        completed = run_journaled(self.path, tasks)
        plan = JournalPlan.from_tasks([
            JournalTask("fail", lambda: self.fail("export invoked fail"), "export:fail:v1"),
            JournalTask("child", lambda: self.fail("export invoked child"),
                        "export:child:v1", ("fail",)),
            JournalTask("check", lambda: self.fail("export invoked check"),
                        "export:check:v1"),
        ])
        first = export_journal_evidence(self.path, completed.run_id, plan)
        second = export_journal_evidence(self.path, completed.run_id, plan)
        self.assertEqual(calls, ["check", "fail"])
        self.assertEqual(first, second)
        self.assertEqual(RunEvidence.from_json(first.to_json()), first)
        document = first.to_dict()
        self.assertEqual(document["run_id"], completed.run_id)
        self.assertLessEqual(document["started_at"], document["finished_at"])
        self.assertEqual(
            [(item["task_id"], item["status"], item["value"], item["error"],
              item["dependencies"]) for item in document["tasks"]],
            [
                ("check", "succeeded", False, None, []),
                ("fail", "failed", None, "ValueError: synthetic", []),
                ("child", "blocked", None, "Unsuccessful dependencies: fail", ["fail"]),
            ],
        )

    def test_committed_value_is_detached_from_callback_and_export_callers(self):
        returned = {"samples": [1]}
        tasks = [JournalTask("a", lambda: returned, "export:a:v1"),
                 JournalTask("b", lambda: returned["samples"].append(2),
                             "export:b:v1", ("a",))]
        completed = run_journaled(self.path, tasks)
        plan = JournalPlan.from_tasks(tasks)
        evidence = export_journal_evidence(self.path, completed.run_id, plan)
        evidence.to_dict()["tasks"][0]["value"]["samples"].append(3)
        reopened = export_journal_evidence(self.path, completed.run_id, plan)
        self.assertEqual(reopened.to_dict()["tasks"][0]["value"], {"samples": [1]})

    def test_export_interoperates_with_completed_artifact_store_and_verdicts(self):
        tasks = [JournalTask("check", lambda: False, "export:check:v1")]
        completed = run_journaled(self.path, tasks)
        evidence = export_journal_evidence(
            self.path, completed.run_id, JournalPlan.from_tasks(tasks)
        )
        bindings = RequirementBindings.from_mapping({"REQ-LINK": "check"})
        store_path = Path(self.temp.name, "artifacts.sqlite")
        with EvidenceStore(store_path) as store:
            store.save(evidence, bindings)
            store.save(evidence, bindings)
            changed = evidence.to_dict()
            changed["tasks"][0]["value"] = True
            with self.assertRaises(StorageConflict):
                store.save(RunEvidence.from_json(json.dumps(changed)), bindings)
        with EvidenceStore(store_path) as store:
            restored = assess_requirements(*store.load(completed.run_id, bindings.sha256))
        self.assertEqual(restored.outcomes[0].verdict, "fail")

    def test_process_reopen_export_is_byte_identical_without_callbacks(self):
        tasks = [JournalTask("a", lambda: {"nested": [1, False]}, "export:a:v1")]
        completed = run_journaled(self.path, tasks)
        plan = JournalPlan.from_tasks(tasks)
        expected = export_journal_evidence(self.path, completed.run_id, plan).to_json()
        code = (
            "from chimera import JournalPlan,JournalTask,export_journal_evidence; import sys; "
            "plan=JournalPlan.from_tasks([JournalTask('a',lambda:(_ for _ in ()).throw("
            "SystemExit('callback ran')),'export:a:v1')]); "
            "print(export_journal_evidence(sys.argv[1],sys.argv[2],plan).to_json())"
        )
        child = subprocess.run(
            [sys.executable, "-c", code, str(self.path), completed.run_id],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(child.stdout.strip(), expected)

    def test_empty_completed_journal_exports(self):
        completed = run_journaled(self.path, [])
        evidence = export_journal_evidence(
            self.path, completed.run_id, JournalPlan.from_tasks([])
        )
        self.assertEqual(evidence.to_dict()["tasks"], [])

    def test_partial_attention_and_commit_conflict_never_export(self):
        run_id = str(uuid4())
        tasks = [JournalTask(
            "a", lambda: (_ for _ in ()).throw(KeyboardInterrupt()), "export:a:v1"
        )]
        with self.assertRaises(KeyboardInterrupt):
            run_journaled(self.path, tasks, run_id=run_id)
        plan = JournalPlan.from_tasks(tasks)
        with self.assertRaisesRegex(JournalConflict, "Only a completed"):
            export_journal_evidence(self.path, run_id, plan)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT state FROM journal_runs WHERE run_id=?", (run_id,)
            ).fetchone(), ("running",))
        inspect_interrupted(self.path, run_id, plan)
        with self.assertRaisesRegex(JournalConflict, "Only a completed"):
            export_journal_evidence(self.path, run_id, plan)

        conflict_path = Path(self.temp.name, "conflict.sqlite")
        conflict_run = str(uuid4())
        original = _OwnedJournal.transition
        injected = False

        def conflicting(journal, current_run, task_id, expected, state,
                        value_json=None, error=None):
            nonlocal injected
            if state == "succeeded" and not injected:
                injected = True
                original(journal, current_run, task_id, expected, state,
                         value_json='"different"', error=error)
                raise sqlite3.OperationalError("synthetic conflict")
            original(journal, current_run, task_id, expected, state,
                     value_json=value_json, error=error)

        conflict_tasks = [JournalTask("a", lambda: "intended", "export:a:v1")]
        with patch("chimera.journal._OwnedJournal.transition", new=conflicting):
            with self.assertRaises(JournalError):
                run_journaled(conflict_path, conflict_tasks, run_id=conflict_run)
        with self.assertRaisesRegex(JournalConflict, "Only a completed"):
            export_journal_evidence(
                conflict_path, conflict_run, JournalPlan.from_tasks(conflict_tasks)
            )

    def test_all_terminal_but_unfinished_run_never_exports(self):
        run_id = str(uuid4())
        tasks = [JournalTask("a", lambda: True, "export:a:v1")]
        original = _OwnedJournal.transition

        def interrupt(journal, current_run, task_id, expected, state,
                      value_json=None, error=None):
            original(journal, current_run, task_id, expected, state,
                     value_json=value_json, error=error)
            if state == "succeeded":
                raise KeyboardInterrupt

        with patch("chimera.journal._OwnedJournal.transition", new=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_journaled(self.path, tasks, run_id=run_id)
        with self.assertRaisesRegex(JournalConflict, "Only a completed"):
            export_journal_evidence(self.path, run_id, JournalPlan.from_tasks(tasks))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT state FROM journal_runs WHERE run_id=?", (run_id,)
            ).fetchone(), ("running",))

    def test_wrong_plan_and_unknown_run_are_rejected_without_callbacks(self):
        calls = []
        tasks = [JournalTask("a", lambda: calls.append("run") or True, "export:a:v1")]
        completed = run_journaled(self.path, tasks)
        wrong = JournalPlan.from_tasks([
            JournalTask("a", lambda: calls.append("wrong"), "export:a:v2")
        ])
        with self.assertRaisesRegex(JournalConflict, "plan does not match"):
            export_journal_evidence(self.path, completed.run_id, wrong)
        with self.assertRaises(KeyError):
            export_journal_evidence(self.path, str(uuid4()), JournalPlan.from_tasks(tasks))
        self.assertEqual(calls, ["run"])

    def test_missing_path_is_not_created_and_active_owner_is_refused(self):
        missing = Path(self.temp.name, "missing", "journal.sqlite")
        with self.assertRaises(JournalStorageUnavailable):
            export_journal_evidence(missing, str(uuid4()), JournalPlan.from_tasks([]))
        self.assertFalse(missing.exists())
        self.assertFalse(missing.parent.exists())

        completed = run_journaled(self.path, [])
        with DatabaseOwnership(self.path):
            with self.assertRaises(OwnershipBusy):
                export_journal_evidence(
                    self.path, completed.run_id, JournalPlan.from_tasks([])
                )

    def test_missing_wrong_and_nonterminal_rows_fail_closed(self):
        tasks = [JournalTask("a", lambda: True, "export:a:v1"),
                 JournalTask("b", lambda: 2, "export:b:v1")]
        plan = JournalPlan.from_tasks(tasks)
        mutations = [
            "DELETE FROM journal_tasks WHERE task_id='b'",
            "UPDATE journal_tasks SET task_id='wrong' WHERE task_id='b'",
            "UPDATE journal_tasks SET state='pending',value_json=NULL,error=NULL "
            "WHERE task_id='b'",
        ]
        for index, statement in enumerate(mutations):
            with self.subTest(statement=statement):
                path = Path(self.temp.name, f"corrupt-{index}.sqlite")
                completed = run_journaled(path, tasks)
                with sqlite3.connect(path) as db:
                    db.execute(statement)
                with self.assertRaises(JournalError):
                    export_journal_evidence(path, completed.run_id, plan)


if __name__ == "__main__":
    unittest.main()
