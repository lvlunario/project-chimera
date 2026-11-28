"""Cooperative Linux/local-file ownership, separate from SQLite transactions."""
import os
from pathlib import Path
import stat
import sys
from weakref import WeakSet


class OwnershipError(RuntimeError):
    """Ownership is unavailable, inactive, or its file identity changed."""


class OwnershipBusy(OwnershipError):
    """Another cooperative owner holds this database."""


_active = WeakSet()


def _after_fork() -> None:
    # Close, never LOCK_UN: inherited descriptors share the parent's flock.
    for owner in list(_active):
        owner.close()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


class DatabaseOwnership:
    """Hold an exclusive advisory lock on an existing local database inode.

    Initialize the database with EvidenceStore first. All future runner/recovery
    entry points must cooperate with this guard; existing P1 APIs do not use it.
    A trusted directory and stable database path are required. Not a sandbox,
    database validator, network-filesystem lock, journal, or recovery operation.
    Use one context in one thread; do not transfer it between threads/processes.
    """

    def __init__(self, path: str | Path):
        self._fd: int | None = None
        self._pid: int | None = None
        self.path = Path(path).absolute()

    def __enter__(self):
        if sys.platform != "linux":
            raise OwnershipError("Database ownership currently supports Linux only")
        if self._fd is not None:
            raise OwnershipError("Ownership context is already active")
        import fcntl

        # No creation or truncation; NONBLOCK prevents a FIFO from hanging open.
        fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise OwnershipError("Ownership requires a regular, non-hardlinked file")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise OwnershipBusy("Database already has an active owner") from exc
            self._fd, self._pid = fd, os.getpid()
            self.check()
            _active.add(self)
            return self
        except BaseException:
            self._fd = self._pid = None
            os.close(fd)
            raise

    def check(self) -> None:
        """Fail closed if inactive or the original pathname no longer names the inode.

        Call before each future journal transition/callback. This detects changes
        at checkpoints, not hostile pathname replacement between checks.
        """
        if self._fd is None or self._pid != os.getpid():
            raise OwnershipError("No active ownership in this process")
        held = os.fstat(self._fd)
        try:
            current = self.path.stat()
        except OSError as exc:
            raise OwnershipError("Owned database path is unavailable") from exc
        if ((held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
                or held.st_nlink != 1 or current.st_nlink != 1):
            raise OwnershipError("Owned database identity changed")

    def close(self) -> None:
        """Release this descriptor; no explicit unlock that could affect a parent."""
        fd, self._fd = self._fd, None
        self._pid = None
        _active.discard(self)
        if fd is not None:
            os.close(fd)

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        self.close()
