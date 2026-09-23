"""Synthetic completed-journal evidence handoff demonstration."""
from pathlib import Path
import tempfile

from chimera import (EvidenceStore, JournalPlan, JournalTask, RequirementBindings,
                     assess_requirements, export_journal_evidence, run_journaled)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        journal_path = Path(directory, "journal.sqlite")
        evidence_path = Path(directory, "evidence.sqlite")
        calls: list[str] = []
        tasks = [JournalTask(
            "link-margin-check",
            lambda: calls.append("link-margin-check") or False,
            "demo:link-margin-check:v1",
        )]
        completed = run_journaled(journal_path, tasks)
        evidence = export_journal_evidence(
            journal_path, completed.run_id, JournalPlan.from_tasks(tasks)
        )
        bindings = RequirementBindings.from_mapping({"REQ-LINK-MARGIN": "link-margin-check"})
        with EvidenceStore(evidence_path) as store:
            store.save(evidence, bindings)
        with EvidenceStore(evidence_path) as store:
            assessment = assess_requirements(
                *store.load(completed.run_id, bindings.sha256)
            )
        if calls != ["link-margin-check"]:
            raise RuntimeError("Journal export or reopen repeated the check callback")
        if assessment.outcomes[0].verdict != "fail":
            raise RuntimeError("Journal export or reopen changed the requirement verdict")
        print(f"journal run: {completed.run_id} completed")
        print("export: schema-v1 evidence reopened without callbacks")
        print("requirement REQ-LINK-MARGIN: fail")
        print("callbacks: link-margin-check=1")


if __name__ == "__main__":
    main()
