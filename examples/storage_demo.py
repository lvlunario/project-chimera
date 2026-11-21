"""Synthetic immutable storage exercise; temporary database, no task recovery."""
from pathlib import Path
import tempfile

from chimera import EvidenceStore, RequirementBindings, Task, assess_requirements, run_with_evidence


def main():
    calls = []
    evidence = run_with_evidence([Task("link-check", lambda: calls.append(1) or False)])
    bindings = RequirementBindings.from_mapping({"COM-LINK-001": "link-check"})
    original = assess_requirements(evidence, bindings)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory, "evidence.sqlite")
        with EvidenceStore(path) as store:
            store.save(evidence, bindings)
            store.save(evidence, bindings)
        with EvidenceStore(path) as store:
            restored = assess_requirements(*store.load(original.run_id, bindings.sha256))
        if restored != original or calls != [1]:
            raise RuntimeError("Reopen changed assessment or repeated execution")
        print("storage: original failed verdict preserved after connection reopen")
        print("storage: identical save acknowledged; check invoked once")
    print("storage: temporary database removed; journal/recovery not implemented")


if __name__ == "__main__":
    main()
