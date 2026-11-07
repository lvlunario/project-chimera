import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from chimera import (EvidenceStore, RequirementBindings, RunEvidence, StorageConflict,
                     StorageError, Task, assess_requirements, run_with_evidence)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name, "evidence.sqlite")
        self.calls = []
        self.run = run_with_evidence([Task("check", lambda: self.calls.append(1) or False)])
        self.bindings = RequirementBindings.from_mapping({"LINK-001": "check"})
        self.run_id = self.run.to_dict()["run_id"]

    def test_process_reopen_reproduces_assessment_without_execution(self):
        with EvidenceStore(self.path) as store:
            store.save(self.run, self.bindings)
        code = (
            "from chimera import EvidenceStore, assess_requirements; import sys; "
            "s=EvidenceStore(sys.argv[1]); "
            "r,b=s.load(sys.argv[2],sys.argv[3]); "
            "print(r.to_json()); print(b.to_json()); "
            "print(assess_requirements(r,b).outcomes[0].verdict); s.close()"
        )
        result = subprocess.run([sys.executable, "-c", code, str(self.path), self.run_id,
                                 self.bindings.sha256], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, self.run.to_json() + "\n" + self.bindings.to_json() + "\nfail\n")
        with EvidenceStore(self.path) as store:
            restored = store.load(self.run_id, self.bindings.sha256)
            self.assertEqual(assess_requirements(*restored), assess_requirements(self.run, self.bindings))
        self.assertEqual(self.calls, [1])

    def test_identical_save_and_multiple_mappings_preserve_original(self):
        other = RequirementBindings.from_mapping({"LINK-002": "missing"})
        with EvidenceStore(self.path) as store:
            store.save(self.run, self.bindings)
            store.save(self.run, self.bindings)
            store.save(self.run, other)
            self.assertEqual(store.load(self.run_id, self.bindings.sha256), (self.run, self.bindings))
            self.assertEqual(store.load(self.run_id, other.sha256), (self.run, other))
        with sqlite3.connect(self.path) as db:
            self.assertEqual([db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                              for table in ("runs", "bindings", "associations")], [1, 2, 2])

    def test_changed_run_id_conflicts_without_writes(self):
        changed = self.run.to_dict()
        changed["tasks"][0]["value"] = True
        different = RunEvidence.from_json(json.dumps(changed))
        other = RequirementBindings.from_mapping({"OTHER": "check"})
        with EvidenceStore(self.path) as store:
            store.save(self.run, self.bindings)
            with self.assertRaises(StorageConflict):
                store.save(different, other)
            self.assertEqual(store.load(self.run_id, self.bindings.sha256), (self.run, self.bindings))
            with self.assertRaises(KeyError):
                store.load(self.run_id, other.sha256)

    def test_injected_write_failure_rolls_back_all_artifacts_then_retry(self):
        with EvidenceStore(self.path) as store:
            store._db.set_authorizer(lambda action, table, *_:
                                     sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT
                                     and table == "bindings" else sqlite3.SQLITE_OK)
            with self.assertRaises(sqlite3.DatabaseError):
                store.save(self.run, self.bindings)
            store._db.set_authorizer(None)
            with sqlite3.connect(self.path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM bindings").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM associations").fetchone()[0], 0)
            store.save(self.run, self.bindings)
            self.assertEqual(store.load(self.run_id, self.bindings.sha256), (self.run, self.bindings))

    def test_unknown_version_and_foreign_database_are_not_adopted(self):
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA user_version = 99")
        with self.assertRaises(StorageError):
            EvidenceStore(self.path)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 99)
            db.execute("PRAGMA user_version = 0")
            db.execute("CREATE TABLE unrelated (value TEXT)")
        with self.assertRaises(StorageError):
            EvidenceStore(self.path)

    def test_corrupt_artifact_and_invalid_relationship_fail_closed(self):
        for statement in ("UPDATE runs SET document = 'invalid'",
                          "UPDATE runs SET digest = 'wrong'",
                          "UPDATE bindings SET document = 'invalid'",
                          "UPDATE bindings SET digest = 'wrong'",
                          "INSERT INTO associations VALUES ('missing', 'missing')"):
            with self.subTest(statement=statement):
                if self.path.exists():
                    self.path.unlink()
                with EvidenceStore(self.path) as store:
                    store.save(self.run, self.bindings)
                with sqlite3.connect(self.path) as db:
                    db.execute(statement)
                with self.assertRaises(StorageError):
                    EvidenceStore(self.path)

    def test_missing_association_and_wrong_types(self):
        with EvidenceStore(self.path) as store:
            with self.assertRaises(KeyError):
                store.load(self.run_id, self.bindings.sha256)
            with self.assertRaises(TypeError):
                store.save({}, self.bindings)
