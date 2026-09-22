"""Synthetic per-task journal and inspect-only recovery demonstration."""
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

from chimera import JournalPlan, JournalTask, inspect_interrupted


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory, "journal.sqlite")
        marker = Path(directory, "effect.txt")
        run_id = str(uuid4())
        code = """
import os, sys
from pathlib import Path
from chimera import JournalTask, run_journaled
def effect():
    Path(sys.argv[3]).write_text('performed once', encoding='utf-8')
    os.kill(os.getpid(), 9)
run_journaled(sys.argv[1], [JournalTask('effect', effect, 'demo:effect:v1')], run_id=sys.argv[2])
"""
        child = subprocess.run(
            [sys.executable, "-c", code, str(path), run_id, str(marker)],
            capture_output=True, text=True,
        )
        if child.returncode == 0 or marker.read_text(encoding="utf-8") != "performed once":
            raise RuntimeError("Synthetic interruption fixture did not execute as expected")
        plan = JournalPlan.from_tasks(
            [JournalTask("effect", lambda: (_ for _ in ()).throw(
                AssertionError("recovery executed callback")), "demo:effect:v1")]
        )
        inspection = inspect_interrupted(path, run_id, plan)
        if inspection.state != "needs_attention":
            raise RuntimeError("Interrupted run did not require operator attention")
        if inspection.tasks[0].state != "running":
            raise RuntimeError("Interrupted task was not preserved as outcome-unknown")
        if marker.read_text(encoding="utf-8") != "performed once":
            raise RuntimeError("Synthetic effect marker changed during recovery")
        print("effect marker: performed once")
        print("recovered run: needs_attention")
        print("effect task: running (outcome unknown; not retried)")
        print("callback invocations during recovery: 0")


if __name__ == "__main__":
    main()
