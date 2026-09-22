"""Independent adversarial checks for bounded synthetic sample replacement."""
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from chimera import (EvidenceStore, FaultError, FaultPlan, JournalPlan, JournalTask,
                     RequirementBindings, TelemetryError, assess_requirements,
                     evaluate_link_margin, export_journal_evidence, fault_manifest,
                     inject_link_csv, parse_link_csv, run_journaled)
from chimera.telemetry import MAX_INPUT_BYTES


def make_plan(items=()):
    return FaultPlan(json.dumps({"schema_version": 1, "model": "sample-replacement-v1",
                                 "replacements": list(items)}))


class IndependentFaultQATests(unittest.TestCase):
    def test_ambient_decimal_capitals_cannot_change_output_or_provenance(self):
        source = b"timestamp_utc,link_margin_db\n2026-09-22T00:00:00Z,1e3\n"
        outputs, manifests, reports = [], [], []
        for capitals in (0, 1):
            with localcontext() as context:
                context.capitals = capitals
                context.prec = 2
                outputs.append(inject_link_csv(source, make_plan()))
                manifests.append(fault_manifest(source, make_plan()))
                reports.append(evaluate_link_margin(parse_link_csv(outputs[-1]),
                                                    Decimal("2E+3")).to_json())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(manifests[0], manifests[1])
        self.assertEqual(reports[0], reports[1])

    def test_derived_output_bound_is_checked_after_valid_source_and_plan(self):
        start = datetime(2026, 9, 22)
        source = ("timestamp_utc,link_margin_db\n" + "".join(
            f"{start + timedelta(seconds=i):%Y-%m-%dT%H:%M:%SZ},{'4' * 82}\n"
            for i in range(10000))).encode()
        self.assertLess(len(source), MAX_INPUT_BYTES)
        self.assertEqual(10000, len(parse_link_csv(source).samples))
        plan = make_plan([{"sample_index": i + 1, "link_margin_db": "2" * 120}
                          for i in range(300)])
        with self.assertRaisesRegex(TelemetryError, "input bound"):
            inject_link_csv(source, plan)

    def test_nested_duplicate_field_cannot_silently_override_replacement(self):
        text = ('{"schema_version":1,"model":"sample-replacement-v1",'
                '"replacements":[{"sample_index":1,"sample_index":2,"link_margin_db":"2"}]}')
        with self.assertRaises(FaultError):
            FaultPlan(text)

    def test_quoted_source_has_original_identity_and_same_semantic_control(self):
        source = (b'"timestamp_utc","link_margin_db"\r\n'
                  b'"2026-09-22T00:00:00+00:00","+4.00"\r\n')
        manifest = fault_manifest(source, make_plan())
        output = inject_link_csv(source, make_plan())
        self.assertNotEqual(source, output)
        self.assertEqual(sha256(source).hexdigest(), manifest["source"]["input_sha256"])
        self.assertEqual(sha256(output).hexdigest(), manifest["derived"]["input_sha256"])
        self.assertEqual(parse_link_csv(source).samples, parse_link_csv(output).samples)

    def test_malformed_source_blocks_check_report_and_survives_durable_handoff(self):
        source = b"timestamp_utc,link_margin_db\n2026-09-22T00:00:00Z,NaN\n"
        tasks = (
            JournalTask("fault", lambda: fault_manifest(source, make_plan()), "bad-source:v1"),
            JournalTask("check", lambda: self.fail("check callback ran"), "check:v1", ("fault",)),
            JournalTask("report", lambda: self.fail("report callback ran"), "report:v1", ("check",)),
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
        statuses = {item["task_id"]: item["status"] for item in reopened[0].to_dict()["tasks"]}
        self.assertEqual({"fault": "failed", "check": "blocked", "report": "blocked"}, statuses)
        self.assertEqual("not_evaluated", assess_requirements(*reopened).outcomes[0].verdict)


if __name__ == "__main__":
    unittest.main()
