from contextlib import redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import subprocess
import sys
import unittest
from uuid import uuid4

from chimera import (ReportError, RequirementBindings, RunEvidence, Task,
                     VerificationReport, evaluate_link_margin, parse_link_csv,
                     run_with_evidence)


CSV_FAIL = (b"timestamp_utc,link_margin_db\n"
            b"2026-09-23T00:00:00Z,4.0\n2026-09-23T00:00:01Z,2.0\n")
CSV_PASS = CSV_FAIL.replace(b"2.0", b"3.0")


def evidence_document(tasks):
    now = datetime.now(timezone.utc).isoformat()
    return RunEvidence(json.dumps({
        "schema_version": 1, "run_id": str(uuid4()), "started_at": now,
        "finished_at": now, "tasks": tasks,
    }))


def successful_evidence(csv=CSV_FAIL):
    detail = evaluate_link_margin(parse_link_csv(csv), 3).to_dict()
    passed = detail["passed"]
    return run_with_evidence([
        Task("check", lambda: passed), Task("detail", lambda: detail, ("check",)),
    ])


class VerificationReportTests(unittest.TestCase):
    def setUp(self):
        self.bindings = RequirementBindings.from_mapping({"COM-LINK-001": "check"})

    def test_failed_report_round_trip_html_and_fixed_digest(self):
        evidence = successful_evidence()
        report = VerificationReport.from_evidence(
            RunEvidence.from_json(evidence.to_json()),
            RequirementBindings.from_json(self.bindings.to_json()),
            detail_task_id="detail",
        )
        reopened = VerificationReport.from_json(report.to_json())
        self.assertEqual(report, reopened)
        self.assertEqual(sha256(report.to_json().encode()).hexdigest(), report.sha256)
        document = report.to_dict()
        self.assertEqual("fail", document["requirement"]["verdict"])
        self.assertEqual(1, document["detail"]["link_margin"]["failure_count"])
        html = report.to_html()
        self.assertEqual(html, reopened.to_html())
        self.assertIn("FAIL", html)
        self.assertIn("2.0", html)
        self.assertIn(report.sha256, html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("http://", html.lower())
        self.assertNotIn("https://", html.lower())

    def test_pass_report_has_no_findings(self):
        report = VerificationReport.from_evidence(
            successful_evidence(CSV_PASS), self.bindings, detail_task_id="detail"
        )
        self.assertEqual("pass", report.to_dict()["requirement"]["verdict"])
        self.assertIn("No below-threshold samples", report.to_html())

    def test_missing_evidence_is_explicitly_unavailable_never_pass(self):
        evidence = evidence_document([
            {"task_id": "ingest", "status": "failed", "value": None,
             "error": "Malformed input", "dependencies": []},
            {"task_id": "check", "status": "blocked", "value": None,
             "error": "Unsuccessful dependencies: ingest", "dependencies": ["ingest"]},
            {"task_id": "detail", "status": "blocked", "value": None,
             "error": "Unsuccessful dependencies: check", "dependencies": ["check"]},
        ])
        report = VerificationReport.from_evidence(
            evidence, self.bindings, detail_task_id="detail"
        )
        document = report.to_dict()
        self.assertEqual("not_evaluated", document["requirement"]["verdict"])
        self.assertEqual("unavailable", document["detail"]["status"])
        self.assertIsNone(document["detail"]["link_margin"])
        self.assertIn("Detail unavailable", report.to_html())

    def test_html_escapes_untrusted_reason_and_identifiers(self):
        bindings = RequirementBindings.from_mapping({"COM-LINK-001": "<check&>"})
        evidence = evidence_document([
            {"task_id": "<check&>", "status": "failed", "value": None,
             "error": "<img src=x onerror=alert(1)>", "dependencies": []},
        ])
        report = VerificationReport.from_evidence(
            evidence, bindings, detail_task_id="<missing>"
        )
        html = report.to_html()
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("<check&>", html)

    def test_rejects_wrong_selection_types_and_missing_requested_provenance(self):
        evidence = successful_evidence()
        for args in ((None, self.bindings), (evidence, {})):
            with self.subTest(args), self.assertRaises(TypeError):
                VerificationReport.from_evidence(*args, detail_task_id="detail")
        for detail in ("", None, 3):
            with self.subTest(detail), self.assertRaises(ReportError):
                VerificationReport.from_evidence(
                    evidence, self.bindings, detail_task_id=detail  # type: ignore[arg-type]
                )
        with self.assertRaisesRegex(ReportError, "provenance"):
            VerificationReport.from_evidence(
                evidence, self.bindings, detail_task_id="detail", provenance_task_id="missing"
            )

    def test_requires_exact_com_link_binding_and_consistent_detail(self):
        evidence = successful_evidence()
        for mapping in ({}, {"OTHER": "check"},
                        {"COM-LINK-001": "check", "OTHER": "check"}):
            with self.subTest(mapping), self.assertRaises(ReportError):
                VerificationReport.from_evidence(
                    evidence, RequirementBindings.from_mapping(mapping), detail_task_id="detail"
                )
        wrong = run_with_evidence([
            Task("check", lambda: True),
            Task("detail", lambda: evaluate_link_margin(
                parse_link_csv(CSV_FAIL), 3).to_dict(), ("check",)),
        ])
        with self.assertRaisesRegex(ReportError, "conflicts"):
            VerificationReport.from_evidence(wrong, self.bindings, detail_task_id="detail")

    def test_rejects_tampered_and_duplicate_canonical_report(self):
        report = VerificationReport.from_evidence(
            successful_evidence(), self.bindings, detail_task_id="detail"
        )
        mutations = []
        for path, value in (("evidence_sha256", "0" * 63),
                            ("report_type", "arbitrary"), ("schema_version", 2)):
            document = report.to_dict()
            document[path] = value
            mutations.append(document)
        document = report.to_dict()
        document["requirement"]["verdict"] = "pass"
        mutations.append(document)
        document = report.to_dict()
        document["detail"]["status"] = "unavailable"
        mutations.append(document)
        for document in mutations:
            with self.subTest(document), self.assertRaises(ReportError):
                VerificationReport.from_json(json.dumps(document))
        duplicate = report.to_json()[:-1] + ',"schema_version":1}'
        with self.assertRaisesRegex(ReportError, "Duplicate"):
            VerificationReport.from_json(duplicate)
        for text in ("\ud800", " " * 4_194_305):
            with self.subTest(len(text)), self.assertRaises(ReportError):
                VerificationReport.from_json(text)
        document = report.to_dict()
        document["requirement"]["reason"] = "bad\u0000reason"
        with self.assertRaisesRegex(ReportError, "control"):
            VerificationReport.from_json(json.dumps(document))

    def test_demo_normal_and_optimized(self):
        from examples.report_demo import main
        output = io.StringIO()
        with redirect_stdout(output):
            main()
        self.assertIn("COM-LINK-001: FAIL", output.getvalue())
        result = subprocess.run(
            [sys.executable, "-O", "-m", "examples.report_demo"],
            capture_output=True, text=True, check=True,
        )
        self.assertIn("report generation invokes none", result.stdout)


if __name__ == "__main__":
    unittest.main()
