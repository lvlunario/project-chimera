"""Synthetic communications CSV to durable evidence demonstration."""
from pathlib import Path
import tempfile
from decimal import Decimal

from chimera import (EvidenceStore, JournalPlan, JournalTask, RequirementBindings,
                     TelemetryError, assess_requirements, evaluate_link_margin,
                     export_journal_evidence, identify_link_csv, link_margin_passes,
                     load_link_csv, run_journaled)


def main() -> None:
    source = Path(__file__).parent / "fixtures" / "link_margin_failed.csv"
    identity = identify_link_csv(source)
    threshold_db = Decimal("3.0")
    callbacks = {"ingest": 0, "check": 0, "report": 0}

    def ingest() -> dict:
        callbacks["ingest"] += 1
        return load_link_csv(source, expected_sha256=identity.sha256).manifest()

    def check() -> bool:
        callbacks["check"] += 1
        telemetry = load_link_csv(source, expected_sha256=identity.sha256)
        return link_margin_passes(telemetry, threshold_db)

    def report() -> dict:
        callbacks["report"] += 1
        telemetry = load_link_csv(source, expected_sha256=identity.sha256)
        return evaluate_link_margin(telemetry, threshold_db).to_dict()

    tasks = (
        JournalTask("ingest", ingest, f"link-csv-v1:{identity.sha256}"),
        JournalTask("verification-config", lambda: {
            "rule": "minimum_link_margin_gte",
            "threshold_db": str(threshold_db),
            "unit": "dB",
        }, f"minimum-link-margin-config-v1:{threshold_db}"),
        JournalTask("link-margin-check", check,
                    f"minimum-link-margin-v1:{identity.sha256}:{threshold_db}",
                    ("ingest", "verification-config")),
        JournalTask("link-margin-report", report,
                    f"minimum-link-margin-report-v1:{identity.sha256}:{threshold_db}",
                    ("link-margin-check",)),
    )
    plan = JournalPlan.from_tasks(tasks)
    bindings = RequirementBindings.from_mapping(
        {"COM-LINK-001": "link-margin-check"}
    )
    with tempfile.TemporaryDirectory() as directory:
        journal_path = Path(directory, "journal.sqlite")
        run = run_journaled(journal_path, tasks)
        evidence = export_journal_evidence(journal_path, run.run_id, plan)
        with EvidenceStore(Path(directory, "evidence.sqlite")) as store:
            store.save(evidence, bindings)
            reopened = store.load(run.run_id, bindings.sha256)
        assessment = assess_requirements(*reopened)

    document = evidence.to_dict()
    report_value = next(
        item["value"] for item in document["tasks"]
        if item["task_id"] == "link-margin-report"
    )
    passing = load_link_csv(Path(__file__).parent / "fixtures" / "link_margin_passed.csv")
    passing_report = evaluate_link_margin(passing, threshold_db)
    try:
        load_link_csv(Path(__file__).parent / "fixtures" / "link_margin_malformed.csv")
    except TelemetryError:
        malformed = "rejected"
    else:
        raise RuntimeError("Malformed reference control was accepted")

    print(f"input: sha256={identity.sha256} bytes={identity.byte_length}")
    print("journal/export: completed and reopened without callback replay")
    print(f"COM-LINK-001: {assessment.outcomes[0].verdict} (minimum 2.0 dB < 3.0 dB)")
    print(f"failing samples: {report_value['failure_count']} (report task succeeded)")
    print(f"passing control: {'pass' if passing_report.passed else 'fail'}")
    print(f"malformed control: {malformed}")
    print("callbacks: " + ", ".join(
        f"{name}={count}" for name, count in callbacks.items()
    ))


if __name__ == "__main__":
    main()
