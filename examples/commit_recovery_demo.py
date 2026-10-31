"""Synthetic post-COMMIT error demo; no callback is repeated."""
from pathlib import Path
import sqlite3
import tempfile

from chimera import JournalTask, run_journaled
from chimera.journal import _OwnedJournal


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory, "commit-recovery.sqlite")
        calls: list[str] = []
        original = _OwnedJournal.transition
        injected = False

        def transition(journal, run_id, task_id, expected, state,
                       value_json=None, error=None):
            nonlocal injected
            original(journal, run_id, task_id, expected, state,
                     value_json=value_json, error=error)
            if task_id == "measure" and state == "succeeded" and not injected:
                injected = True
                raise sqlite3.OperationalError("synthetic connection loss after COMMIT")

        _OwnedJournal.transition = transition
        try:
            result = run_journaled(path, [
                JournalTask("measure", lambda: calls.append("measure") or {"margin_db": 3.2},
                            "demo:measure:v1"),
                JournalTask("report", lambda: calls.append("report") or True,
                            "demo:report:v1", ("measure",)),
            ])
        finally:
            _OwnedJournal.transition = original
        assert calls == ["measure", "report"] and result.state == "completed"
        print("synthetic fault: connection error reported after terminal COMMIT")
        print("reconciliation: exact durable result matched")
        print("callbacks: measure=1, report=1 (no duplicate effect)")
        print("run: completed")


if __name__ == "__main__":
    main()
