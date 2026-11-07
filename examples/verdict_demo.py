"""Synthetic boolean checks; no CSV ingestion or physical-radio validation."""
from pathlib import Path
from tempfile import TemporaryDirectory

from chimera import RunEvidence, Task, assess_requirements, run_with_evidence


def main():
    def invalid_input():
        raise ValueError("synthetic missing units")

    evidence = run_with_evidence([
        Task("link-check", lambda: 2.0 >= 3.0),
        Task("passing-control", lambda: 4.0 >= 3.0),
        Task("invalid-input", invalid_input),
        Task("blocked-check", lambda: True, ("invalid-input",)),
        Task("handoff", lambda: "failure evidence available", ("link-check",)),
    ])
    bindings = {"COM-LINK-001": "link-check", "CONTROL": "passing-control",
                "INVALID": "invalid-input", "BLOCKED": "blocked-check",
                "MISSING": "absent"}
    assessment = assess_requirements(evidence, bindings)
    with TemporaryDirectory() as directory:
        path = Path(directory) / "run.json"
        with path.open("x", encoding="utf-8") as stream:
            stream.write(evidence.to_json())
        reopened = RunEvidence.from_json(path.read_text(encoding="utf-8"))
        assert assess_requirements(reopened, bindings) == assessment
    for task in evidence.to_dict()["tasks"]:
        print(f"task {task['task_id']}: {task['status']}")
    for outcome in assessment.outcomes:
        print(f"requirement {outcome.requirement_id}: {outcome.verdict}")
    assert not assessment.all_passed
    print("reopened assessment: identical; all_passed: False")


if __name__ == "__main__":
    main()
