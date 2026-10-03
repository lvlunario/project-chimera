"""Independent AI QA: malformed schema and externally altered repositories."""
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from chimera import RequirementBindings, Task, run_with_evidence
from chimera.storage import EvidenceStore, StorageError


class IndependentStorageQATests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "evidence.sqlite"
        self.evidence = run_with_evidence([Task("check", lambda: False)])
        self.bindings = RequirementBindings.from_mapping({"REQ-1": "check"})
        self.run_id = self.evidence.to_dict()["run_id"]

    def test_same_names_without_required_constraints_fail_closed(self):
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE runs (run_id TEXT, document TEXT, digest TEXT)")
            db.execute("CREATE TABLE bindings (digest TEXT, document TEXT)")
            db.execute("CREATE TABLE associations (run_id TEXT, digest TEXT)")
            db.execute("PRAGMA user_version = 1")
        with self.assertRaises(StorageError):
            EvidenceStore(self.path)

    def test_corrupt_run_digest_rejected_on_already_open_reader(self):
        with EvidenceStore(self.path) as store:
            store.save(self.evidence, self.bindings)
            with sqlite3.connect(self.path) as db:
                db.execute("UPDATE runs SET digest = ?", ("0" * 64,))
            with self.assertRaises(StorageError):
                store.load(self.run_id, self.bindings.sha256)

    def test_changed_schema_version_rejected_before_already_open_write(self):
        with EvidenceStore(self.path) as store:
            with sqlite3.connect(self.path) as db:
                db.execute("PRAGMA user_version = 99")
            with self.assertRaises(StorageError):
                store.save(self.evidence, self.bindings)
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)

    def test_orphan_association_rejected_on_reopen(self):
        with EvidenceStore(self.path) as store:
            store.save(self.evidence, self.bindings)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM bindings")
        with self.assertRaises(StorageError):
            EvidenceStore(self.path)

    def test_binding_noncanonical_json_is_rejected_even_if_digest_unchanged(self):
        with EvidenceStore(self.path) as store:
            store.save(self.evidence, self.bindings)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE bindings SET document = ?",
                       (" " + self.bindings.to_json(),))
        with self.assertRaises(StorageError):
            EvidenceStore(self.path)

    def test_missing_pair_read_rolls_back_then_store_remains_usable(self):
        with EvidenceStore(self.path) as store:
            with self.assertRaises(KeyError):
                store.load(self.run_id, self.bindings.sha256)
            store.save(self.evidence, self.bindings)
            recovered, bindings = store.load(self.run_id, self.bindings.sha256)
        self.assertEqual(recovered, self.evidence)
        self.assertEqual(bindings, self.bindings)

    def test_injected_binding_write_failure_rolls_back_run(self):
        with EvidenceStore(self.path) as store:
            def deny_binding_insert(action, table, *_):
                return (sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT
                        and table == "bindings" else sqlite3.SQLITE_OK)
            store._db.set_authorizer(deny_binding_insert)
            with self.assertRaises(sqlite3.DatabaseError):
                store.save(self.evidence, self.bindings)
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM bindings").fetchone()[0], 0)
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM associations").fetchone()[0], 0)
            store._db.set_authorizer(None)
            store.save(self.evidence, self.bindings)
        with EvidenceStore(self.path) as reopened:
            self.assertEqual(reopened.load(self.run_id, self.bindings.sha256)[0], self.evidence)

    def test_two_process_identical_saves_preserve_single_pair(self):
        script = (
            "import sys; from chimera import RunEvidence, RequirementBindings; "
            "from chimera.storage import EvidenceStore; "
            "store=EvidenceStore(sys.argv[1]); "
            "store.save(RunEvidence.from_json(sys.argv[2]), "
            "RequirementBindings.from_json(sys.argv[3])); store.close()"
        )
        processes = [subprocess.Popen(
            [sys.executable, "-c", script, str(self.path),
             self.evidence.to_json(), self.bindings.to_json()],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ) for _ in range(2)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, stdout + stderr)
        with EvidenceStore(self.path) as reopened:
            self.assertEqual(reopened.load(self.run_id, self.bindings.sha256)[0], self.evidence)
            for table in ("runs", "bindings", "associations"):
                self.assertEqual(reopened._db.execute(
                    f"SELECT COUNT(*) FROM {table}").fetchone()[0], 1)
