"""Synthetic fault-injection demo for bounded pending-task resume."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

from chimera import JournalTask, resume_journaled


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory, "resume.sqlite")
        marker = Path(directory, "first.txt")
        run_id = str(uuid4())
        code = r'''\
import os, sys
from pathlib import Path
from chimera import JournalTask, run_journaled
from chimera.journal import _OwnedJournal
original = _OwnedJournal.transition
def transition(self, run_id, task_id, expected, state, value_json=None, error=None):
    original(self, run_id, task_id, expected, state, value_json=value_json, error=error)
    if task_id == "first" and state == "succeeded":
        os.kill(os.getpid(), 9)
_OwnedJournal.transition = transition
run_journaled(sys.argv[1], [
    JournalTask("first", lambda: Path(sys.argv[3]).write_text("once", encoding="utf-8") or True,
                "demo:first:v1"),
    JournalTask("second", lambda: True, "demo:second:v1", ("first",)),
], run_id=sys.argv[2])
'''
        child = subprocess.run(
            [sys.executable, "-c", code, str(path), run_id, str(marker)],
            capture_output=True, text=True,
        )
        if child.returncode == 0 or marker.read_text(encoding="utf-8") != "once":
            raise RuntimeError("Synthetic fault did not occur after the first commit")
        calls: list[str] = []
        result = resume_journaled(path, run_id, [
            JournalTask("first", lambda: (_ for _ in ()).throw(
                AssertionError("terminal task repeated")), "demo:first:v1"),
            JournalTask("second", lambda: calls.append("second") or True,
                        "demo:second:v1", ("first",)),
        ])
        if calls != ["second"] or result.state != "completed":
            raise RuntimeError("Pending-only resume repeated work or did not complete")
        print("first task: preserved succeeded (not repeated)")
        print("second task: resumed from pending and succeeded")
        print("run: completed after process restart")


if __name__ == "__main__":
    main()
