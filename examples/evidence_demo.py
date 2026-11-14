"""Synthetic save/reopen demonstration; temporary files are cleaned on exit."""
from pathlib import Path
from tempfile import TemporaryDirectory

from chimera import RunEvidence, Task, run_with_evidence


def main() -> None:
    def verify_link() -> None:
        raise ValueError("Synthetic link margin 2.0 dB is below required 3.0 dB")

    evidence = run_with_evidence([
        Task("ingest", lambda: {"source": "synthetic", "margin_db": 2.0}),
        Task("link-check", verify_link, ("ingest",)),
        Task("report", lambda: "All checks passed", ("link-check",)),
        Task("health", lambda: "Runner responsive"),
    ])
    with TemporaryDirectory(prefix="chimera-evidence-") as directory:
        path = Path(directory) / "run.json"
        with path.open("x", encoding="utf-8") as stream:
            stream.write(evidence.to_json())
        reopened = RunEvidence.from_json(path.read_text(encoding="utf-8"))
        assert reopened == evidence, "Reopened evidence changed"
        print("Synthetic evidence v1: saved and reopened; exact snapshot match")
        for task in reopened.to_dict()["tasks"]:
            print(f"{task['task_id']}: {task['status']}")
    print("Temporary evidence removed; no task code ran during reload")


if __name__ == "__main__":
    main()
