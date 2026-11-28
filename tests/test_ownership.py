"""Lifetime ownership prerequisites; these do not test a resumable runner."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from chimera import DatabaseOwnership, EvidenceStore, OwnershipBusy, OwnershipError


@unittest.skipUnless(sys.platform == "linux", "Linux ownership contract")
class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name, "runs.sqlite")
        with EvidenceStore(self.path):
            pass

    def test_acquire_release_and_no_database_change(self):
        before = self.path.read_bytes()
        owner = DatabaseOwnership(self.path)
        with self.assertRaises(OwnershipError):
            owner.check()
        for _ in range(2):
            with owner:
                owner.check()
                with self.assertRaises(OwnershipBusy):
                    with DatabaseOwnership(self.path):
                        self.fail("second owner entered")
                with self.assertRaises(OwnershipError):
                    owner.__enter__()
                owner.check()
        owner.close()
        self.assertEqual(before, self.path.read_bytes())

    def test_exception_releases(self):
        with self.assertRaises(KeyboardInterrupt):
            with DatabaseOwnership(self.path):
                raise KeyboardInterrupt
        with DatabaseOwnership(self.path) as owner:
            owner.check()

    def test_sqlite_commit_and_close_do_not_release_ownership(self):
        with DatabaseOwnership(self.path):
            with EvidenceStore(self.path):
                pass
            with self.assertRaises(OwnershipBusy):
                with DatabaseOwnership(self.path):
                    self.fail("SQLite close released lifetime lock")

    def test_symlink_contends_on_same_inode(self):
        alias = self.path.with_name("alias.sqlite")
        alias.symlink_to(self.path)
        with DatabaseOwnership(self.path):
            with self.assertRaises(OwnershipBusy):
                with DatabaseOwnership(alias):
                    self.fail("alias bypassed lock")

    def test_missing_special_and_hardlinked_paths(self):
        missing = self.path.with_name("absent")
        with self.assertRaises(FileNotFoundError):
            with DatabaseOwnership(missing):
                pass
        self.assertFalse(missing.exists())
        fifo = self.path.with_name("fifo")
        os.mkfifo(fifo)
        for path in (fifo, self.path.parent):
            with self.assertRaises(OwnershipError):
                with DatabaseOwnership(path):
                    pass
        alias = self.path.with_name("hardlink")
        os.link(self.path, alias)
        with self.assertRaises(OwnershipError):
            with DatabaseOwnership(alias):
                pass

    def test_replacement_and_unlink_detected(self):
        with DatabaseOwnership(self.path) as owner:
            self.path.rename(self.path.with_name("old.sqlite"))
            with self.assertRaises(OwnershipError):
                owner.check()
            with EvidenceStore(self.path):
                pass
            with self.assertRaises(OwnershipError):
                owner.check()

    def test_other_process_refused_without_waiting(self):
        code = """
import sys
from chimera import DatabaseOwnership, OwnershipBusy
try:
    with DatabaseOwnership(sys.argv[1]):
        raise SystemExit(9)
except OwnershipBusy:
    print('refused')
"""
        with DatabaseOwnership(self.path):
            result = subprocess.run([sys.executable, "-c", code, str(self.path)],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "refused")

    def test_process_kill_releases_guard(self):
        code = """
import sys, time
from chimera import DatabaseOwnership
with DatabaseOwnership(sys.argv[1]):
    print('owned', flush=True)
    time.sleep(60)
"""
        child = subprocess.Popen([sys.executable, "-c", code, str(self.path)],
                                 stdout=subprocess.PIPE, text=True)
        try:
            import select
            ready, _, _ = select.select([child.stdout], [], [], 10)
            self.assertTrue(ready, "child did not signal ownership")
            self.assertEqual(child.stdout.readline().strip(), "owned")
            with self.assertRaises(OwnershipBusy):
                with DatabaseOwnership(self.path):
                    pass
            child.kill()
            child.wait(timeout=10)
            with DatabaseOwnership(self.path) as owner:
                owner.check()
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)
            child.stdout.close()

    def test_unsupported_platform_fails_without_changing_file(self):
        with patch("chimera.ownership.sys.platform", "win32"):
            with self.assertRaises(OwnershipError):
                with DatabaseOwnership(self.path):
                    pass
