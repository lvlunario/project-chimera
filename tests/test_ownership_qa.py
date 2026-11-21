"""Independent AI QA for the Linux-only, cooperative ownership boundary."""
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest

from chimera.ownership import DatabaseOwnership, OwnershipBusy, OwnershipError


@unittest.skipUnless(sys.platform == "linux", "Linux flock contract")
class IndependentOwnershipQATests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "evidence.sqlite"
        self.path.touch()

    def _contender(self):
        return subprocess.run(
            [sys.executable, "-c", (
                "import sys; from chimera.ownership import "
                "DatabaseOwnership, OwnershipBusy\n"
                "try:\n"
                " with DatabaseOwnership(sys.argv[1]): pass\n"
                "except OwnershipBusy: sys.exit(17)\n"
            ), str(self.path)], capture_output=True, text=True, timeout=10,
        )

    def test_process_excluded_without_any_sqlite_transaction(self):
        with DatabaseOwnership(self.path) as owner:
            owner.check()
            result = self._contender()
            self.assertEqual(result.returncode, 17, result.stderr)
            owner.check()
        result = self._contender()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sigkill_releases_ownership(self):
        process = subprocess.Popen(
            [sys.executable, "-c", (
                "import sys,time; from chimera.ownership import DatabaseOwnership\n"
                "with DatabaseOwnership(sys.argv[1]):\n"
                " print('owned', flush=True)\n"
                " time.sleep(60)\n"
            ), str(self.path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertTrue(select.select([process.stdout], [], [], 10)[0])
            self.assertEqual(process.stdout.readline().strip(), "owned")
            self.assertEqual(self._contender().returncode, 17)
            process.kill()
            process.wait(timeout=10)
            result = self._contender()
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)

    def test_fork_child_cannot_validate_or_unlock_parent_ownership(self):
        read_fd, write_fd = os.pipe()
        try:
            with DatabaseOwnership(self.path) as owner:
                pid = os.fork()
                if pid == 0:
                    os.close(read_fd)
                    try:
                        try:
                            owner.check()
                        except OwnershipError:
                            owner.close()
                            os.write(write_fd, b"rejected")
                        else:
                            os.write(write_fd, b"unsafe")
                    finally:
                        os._exit(0)
                self.assertTrue(select.select([read_fd], [], [], 10)[0])
                self.assertEqual(os.read(read_fd, 32), b"rejected")
                os.waitpid(pid, 0)
                owner.check()
                self.assertEqual(self._contender().returncode, 17)
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_fork_child_does_not_extend_parent_lock_lifetime(self):
        release_read, release_write = os.pipe()
        owner = DatabaseOwnership(self.path)
        owner.__enter__()
        pid = os.fork()
        if pid == 0:
            os.close(release_write)
            try:
                os.read(release_read, 1)
            finally:
                os._exit(0)
        try:
            owner.close()
            result = self._contender()
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            owner.close()
            os.write(release_write, b"x")
            os.waitpid(pid, 0)
            os.close(release_read)
            os.close(release_write)

    def test_symlink_alias_contends_for_same_inode(self):
        alias = self.path.with_name("alias.sqlite")
        alias.symlink_to(self.path)
        with DatabaseOwnership(self.path):
            with self.assertRaises(OwnershipBusy):
                with DatabaseOwnership(alias):
                    self.fail("alias bypassed ownership")

    def test_exec_child_cannot_keep_lock_alive_even_with_close_fds_false(self):
        with DatabaseOwnership(self.path) as owner:
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(60)"],
                close_fds=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertTrue(select.select([child.stdout], [], [], 10)[0])
                self.assertEqual(child.stdout.readline().strip(), "ready")
                owner.close()
                result = self._contender()
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=10)

    def test_hardlink_added_after_acquisition_invalidates_check(self):
        with DatabaseOwnership(self.path) as owner:
            os.link(self.path, self.path.with_name("hardlink.sqlite"))
            with self.assertRaises(OwnershipError):
                owner.check()

    def test_path_replacement_invalidates_check(self):
        with DatabaseOwnership(self.path) as owner:
            replacement = self.path.with_name("replacement.sqlite")
            replacement.touch()
            replacement.replace(self.path)
            with self.assertRaises(OwnershipError):
                owner.check()

    def test_exception_exit_releases_lock(self):
        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            with DatabaseOwnership(self.path):
                raise RuntimeError("synthetic")
        result = self._contender()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_closed_owner_cannot_validate(self):
        with DatabaseOwnership(self.path) as owner:
            pass
        owner.close()
        with self.assertRaises(OwnershipError):
            owner.check()
