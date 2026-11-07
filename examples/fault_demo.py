"""Synthetic pass-to-fail fault plan, durable report and callback-free handoff."""
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import tempfile

from chimera import (EvidenceStore, FaultPlan, JournalPlan, JournalTask,
                     RequirementBindings, assess_requirements, evaluate_link_margin,
                     export_journal_evidence, fault_manifest, inject_link_csv,
                     link_margin_passes, parse_link_csv, run_journaled)


def main() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    source = (fixtures / "link_margin_passed.csv").read_bytes()
    plan = FaultPlan.from_json((fixtures / "link_fault_plan.json").read_text())
    identity = sha256(source).hexdigest()
    threshold = Decimal("3.0")
    calls = {"fault": 0, "check": 0, "report": 0}

    def derived():
        return parse_link_csv(inject_link_csv(source, plan, expected_sha256=identity))

    def fault():
        calls["fault"] += 1
        return fault_manifest(source, plan, expected_sha256=identity)

    def check():
        calls["check"] += 1
        return link_margin_passes(derived(), threshold)

    def report():
        calls["report"] += 1
        return evaluate_link_margin(derived(), threshold).to_dict()

    operation = f"fault-v1:{identity}:{plan.sha256}"
    tasks = (
        JournalTask("fault", fault, operation),
        JournalTask("config", lambda: {"threshold_db": str(threshold), "unit": "dB"},
                    "margin-config-v1:3.0"),
        JournalTask("check", check, operation + ":check:3.0", ("fault", "config")),
        JournalTask("report", report, operation + ":report:3.0", ("check",)),
    )
    bindings = RequirementBindings.from_mapping({"COM-LINK-001": "check"})
    with tempfile.TemporaryDirectory() as directory:
        journal = Path(directory, "journal.sqlite")
        run = run_journaled(journal, tasks)
        evidence = export_journal_evidence(journal, run.run_id, JournalPlan.from_tasks(tasks))
        database = Path(directory, "evidence.sqlite")
        with EvidenceStore(database) as store:
            store.save(evidence, bindings)
        with EvidenceStore(database) as store:
            reopened = store.load(run.run_id, bindings.sha256)
        assessment = assess_requirements(*reopened)
    values = {item["task_id"]: item["value"] for item in reopened[0].to_dict()["tasks"]}
    first = inject_link_csv(source, plan)
    if first != inject_link_csv(source, FaultPlan.from_json(plan.to_json())):
        raise RuntimeError("Repeated fault injection changed bytes")
    if not link_margin_passes(parse_link_csv(source), threshold):
        raise RuntimeError("Source control did not pass")
    if assessment.outcomes[0].verdict != "fail" or values["report"]["failure_count"] != 1:
        raise RuntimeError("Injected control did not preserve expected failure")
    if values["fault"]["derived"]["input_sha256"] != values["report"]["input_sha256"]:
        raise RuntimeError("Fault/report identity mismatch")
    if calls != {"fault": 1, "check": 1, "report": 1}:
        raise RuntimeError("Evidence handoff replayed callbacks")
    print("synthetic only: source PASS -> replacement sample 2 = 2.0 dB -> COM-LINK-001 FAIL")
    print("repeatability: identical derived bytes and plan digest")
    print("handoff: source/plan/derived identities and one failing sample preserved")
    print("callbacks: fault=1, check=1, report=1; reopen invokes none")


if __name__ == "__main__":
    main()
