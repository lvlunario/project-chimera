"""Durable synthetic communications evidence to deterministic JSON/HTML report."""
from decimal import Decimal
from pathlib import Path
import tempfile

from chimera import (EvidenceStore, FaultPlan, JournalPlan, JournalTask,
                     RequirementBindings, VerificationReport, evaluate_link_margin,
                     export_journal_evidence, fault_manifest, inject_link_csv,
                     link_margin_passes, parse_link_csv, run_journaled)


def main() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    source = (fixtures / "link_margin_passed.csv").read_bytes()
    plan = FaultPlan.from_json((fixtures / "link_fault_plan.json").read_text())
    threshold = Decimal("3.0")
    calls = {"fault": 0, "check": 0, "report": 0}

    def derived():
        return parse_link_csv(inject_link_csv(source, plan))

    def fault():
        calls["fault"] += 1
        return fault_manifest(source, plan)

    def check():
        calls["check"] += 1
        return link_margin_passes(derived(), threshold)

    def detail():
        calls["report"] += 1
        return evaluate_link_margin(derived(), threshold).to_dict()

    tasks = (
        JournalTask("fault", fault, "report-demo:fault:v1"),
        JournalTask("check", check, "report-demo:check:v1", ("fault",)),
        JournalTask("report", detail, "report-demo:detail:v1", ("check",)),
    )
    plan_snapshot = JournalPlan.from_tasks(tasks)
    bindings = RequirementBindings.from_mapping({"COM-LINK-001": "check"})
    with tempfile.TemporaryDirectory() as directory:
        journal = Path(directory, "journal.sqlite")
        run = run_journaled(journal, tasks)
        evidence = export_journal_evidence(journal, run.run_id, plan_snapshot)
        database = Path(directory, "evidence.sqlite")
        with EvidenceStore(database) as store:
            store.save(evidence, bindings)
        with EvidenceStore(database) as store:
            reopened_evidence, reopened_bindings = store.load(run.run_id, bindings.sha256)
        report = VerificationReport.from_evidence(
            reopened_evidence, reopened_bindings,
            detail_task_id="report", provenance_task_id="fault",
        )
        reopened_report = VerificationReport.from_json(report.to_json())
        html = reopened_report.to_html()
        html_path = Path(directory, "report.html")
        html_path.write_text(html, encoding="utf-8", newline="")
        if html_path.read_text(encoding="utf-8") != html:
            raise RuntimeError("Saved HTML changed on reopen")
    document = report.to_dict()
    if document["requirement"]["verdict"] != "fail":
        raise RuntimeError("Expected synthetic requirement failure")
    if document["detail"]["link_margin"]["failure_count"] != 1:
        raise RuntimeError("Expected exactly one failing sample")
    if calls != {"fault": 1, "check": 1, "report": 1}:
        raise RuntimeError("Report generation replayed callbacks")
    print("COM-LINK-001: FAIL; one 2.0 dB sample is below the 3.0 dB threshold")
    print("provenance: synthetic source, plan and derived identities preserved")
    print(f"report: canonical JSON sha256={report.sha256}")
    print(f"html: self-contained deterministic view bytes={len(html.encode('utf-8'))}")
    print("callbacks: fault=1, check=1, report=1; report generation invokes none")


if __name__ == "__main__":
    main()
