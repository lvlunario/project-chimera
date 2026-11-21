"""Independent adversarial checks for the P4 verification-report boundary."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from chimera import (
    FaultPlan,
    ReportError,
    RequirementBindings,
    Task,
    VerificationReport,
    evaluate_link_margin,
    fault_manifest,
    inject_link_csv,
    parse_link_csv,
    run_with_evidence,
)


FIXTURES = Path(__file__).parents[1] / "examples" / "fixtures"


def synthetic_evidence(mutator=None):
    source = (FIXTURES / "link_margin_passed.csv").read_bytes()
    plan = FaultPlan.from_json((FIXTURES / "link_fault_plan.json").read_text())
    derived = inject_link_csv(source, plan)
    provenance = fault_manifest(source, plan)
    if mutator is not None:
        mutator(provenance)
    detail = evaluate_link_margin(parse_link_csv(derived), 3).to_dict()
    return run_with_evidence([
        Task("fault", lambda: provenance),
        Task("check", lambda: False, ("fault",)),
        Task("detail", lambda: detail, ("check",)),
    ])


class VerificationReportIndependentQATests(unittest.TestCase):
    def setUp(self):
        self.bindings = RequirementBindings.from_mapping({"COM-LINK-001": "check"})

    def test_rejects_json_escaped_lone_surrogate_as_report_error(self):
        report = VerificationReport.from_evidence(
            synthetic_evidence(), self.bindings,
            detail_task_id="detail", provenance_task_id="fault",
        )
        document = report.to_dict()
        document["requirement"]["reason"] = "invalid-\ud800-unicode"
        with self.assertRaises(ReportError):
            VerificationReport.from_json(json.dumps(document))

    def test_rejects_fault_plan_that_is_not_its_strict_saved_contract(self):
        mutations = (
            lambda value: value["fault_plan"].pop("schema_version"),
            lambda value: value["fault_plan"].__setitem__("schema_version", 99),
            lambda value: value["fault_plan"].__setitem__("unexpected", "field"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), self.assertRaises(ReportError):
                VerificationReport.from_evidence(
                    synthetic_evidence(mutate), self.bindings,
                    detail_task_id="detail", provenance_task_id="fault",
                )

    def test_rejects_derived_manifest_that_disagrees_with_detail(self):
        def alter_derived(value):
            value["derived"]["input_bytes"] += 1
            value["derived"]["sample_count"] += 1

        with self.assertRaises(ReportError):
            VerificationReport.from_evidence(
                synthetic_evidence(alter_derived), self.bindings,
                detail_task_id="detail", provenance_task_id="fault",
            )

    def test_rejects_invalid_provenance_ranges_and_minimum(self):
        def reverse_ranges(value):
            for name in ("source", "derived"):
                manifest = value[name]
                manifest["timestamp_start_utc"], manifest["timestamp_end_utc"] = (
                    manifest["timestamp_end_utc"], manifest["timestamp_start_utc"]
                )

        def corrupt_minimum(value):
            value["derived"]["minimum_link_margin_db"] = "not-a-decimal"

        for mutate in (reverse_ranges, corrupt_minimum):
            with self.subTest(mutate=mutate), self.assertRaises(ReportError):
                VerificationReport.from_evidence(
                    synthetic_evidence(mutate), self.bindings,
                    detail_task_id="detail", provenance_task_id="fault",
                )

    def test_rejects_replacement_index_beyond_manifest_sample_count(self):
        def add_impossible_replacement(value):
            value["fault_plan"]["replacements"].append({
                "sample_index": value["source"]["sample_count"] + 1,
                "link_margin_db": "1.0",
            })
            value["fault_plan_sha256"] = FaultPlan.from_json(
                json.dumps(value["fault_plan"])
            ).sha256

        with self.assertRaises(ReportError):
            VerificationReport.from_evidence(
                synthetic_evidence(add_impossible_replacement), self.bindings,
                detail_task_id="detail", provenance_task_id="fault",
            )

    def test_html_escapes_closing_tags_and_is_deterministic(self):
        def fail_with_markup():
            raise RuntimeError("</p><script>alert(1)</script>")

        evidence = run_with_evidence([
            Task("check", fail_with_markup),
            Task("detail", lambda: None, ("check",)),
        ])
        report = VerificationReport.from_evidence(
            evidence, self.bindings,
            detail_task_id="detail",
        )
        first = report.to_html()
        second = VerificationReport.from_json(report.to_json()).to_html()
        self.assertEqual(first, second)
        self.assertNotIn("<script>alert(1)</script>", first)
        self.assertIn("&lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;", first)
        self.assertNotIn("http://", first.lower())
        self.assertNotIn("https://", first.lower())

    def test_rejects_reason_that_contradicts_boolean_verdict(self):
        report = VerificationReport.from_evidence(
            synthetic_evidence(), self.bindings,
            detail_task_id="detail", provenance_task_id="fault",
        )
        document = report.to_dict()
        self.assertEqual("fail", document["requirement"]["verdict"])
        document["requirement"]["reason"] = "Check returned True"
        with self.assertRaises(ReportError):
            VerificationReport.from_json(json.dumps(document))

    def test_rejects_null_character_in_visible_text(self):
        report = VerificationReport.from_evidence(
            synthetic_evidence(), self.bindings,
            detail_task_id="detail", provenance_task_id="fault",
        )
        document = report.to_dict()
        document["requirement"]["reason"] = "invalid\x00html"
        with self.assertRaises(ReportError):
            VerificationReport.from_json(json.dumps(document))

    def test_rejects_report_above_resource_bound(self):
        report = VerificationReport.from_evidence(
            synthetic_evidence(), self.bindings,
            detail_task_id="detail", provenance_task_id="fault",
        )
        document = report.to_dict()
        document["requirement"]["reason"] = "x" * 4_200_000
        with self.assertRaisesRegex(ReportError, "exceeds"):
            VerificationReport.from_json(json.dumps(document))


if __name__ == "__main__":
    unittest.main()
