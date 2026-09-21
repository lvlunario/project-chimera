import tempfile
import unittest
import json
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

from chimera import (EvidenceStore, InputIdentity, JournalPlan, JournalTask,
                     LinkMarginReport, LinkSample, LinkTelemetry,
                     RequirementBindings, TelemetryError, assess_requirements,
                     evaluate_link_margin, export_journal_evidence,
                     identify_link_csv, link_margin_passes, load_link_csv,
                     run_journaled)


HEADER = "timestamp_utc,link_margin_db\n"


class TelemetryTests(unittest.TestCase):
    def write(self, directory: str, content: str | bytes) -> Path:
        path = Path(directory, "telemetry.csv")
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="")
        return path

    def test_valid_identity_manifest_and_threshold_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, HEADER +
                              "2026-09-21T00:00:00Z,3.0\n"
                              "2026-09-21T00:00:01+00:00,4.25\n")
            identity = identify_link_csv(path)
            telemetry = load_link_csv(path, expected_sha256=identity.sha256)
            self.assertEqual(identity.sha256, telemetry.input_sha256)
            self.assertEqual(identity.byte_length, telemetry.input_bytes)
            self.assertEqual(Decimal("3.0"), telemetry.minimum_link_margin_db)
            self.assertTrue(link_margin_passes(telemetry, 3))
            self.assertFalse(link_margin_passes(telemetry, 3.01))
            manifest = telemetry.manifest()
            self.assertEqual("3.0", manifest["minimum_link_margin_db"])
            manifest["sample_count"] = 0
            self.assertEqual(2, telemetry.manifest()["sample_count"])

    def test_exact_bytes_have_distinct_identity_but_same_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            lf = self.write(directory, HEADER + "2026-09-21T00:00:00Z,3\n")
            lf_data = lf.read_bytes()
            left = load_link_csv(lf)
            crlf = Path(directory, "crlf.csv")
            crlf.write_bytes(lf_data.replace(b"\n", b"\r\n"))
            right = load_link_csv(crlf)
            self.assertNotEqual(left.input_sha256, right.input_sha256)
            self.assertEqual(left.samples, right.samples)

    def test_report_preserves_every_failure_and_round_trips_canonically(self):
        with tempfile.TemporaryDirectory() as directory:
            telemetry = load_link_csv(self.write(
                directory, HEADER +
                "2026-09-21T00:00:00Z,2.999999999999999999999999999999\n"
                "2026-09-21T00:00:01Z,3.0\n"
                "2026-09-21T00:00:02Z,-1.25\n"
            ))
            report = evaluate_link_margin(telemetry, Decimal("3.0"))
            self.assertFalse(report.passed)
            document = report.to_dict()
            self.assertEqual(2, document["failure_count"])
            self.assertEqual([1, 3], [
                item["sample_index"] for item in document["failing_samples"]
            ])
            self.assertEqual(
                ["2.999999999999999999999999999999", "-1.25"],
                [item["link_margin_db"] for item in document["failing_samples"]],
            )
            reopened = LinkMarginReport.from_json(report.to_json())
            self.assertEqual(report, reopened)
            detached = report.to_dict()
            detached["failing_samples"].clear()
            self.assertEqual(2, report.to_dict()["failure_count"])

    def test_passing_report_has_no_findings_and_boundary_passes(self):
        fixture = Path(__file__).parents[1] / "examples/fixtures/link_margin_passed.csv"
        report = evaluate_link_margin(load_link_csv(fixture), 3)
        self.assertTrue(report.passed)
        self.assertEqual(0, report.to_dict()["failure_count"])
        self.assertEqual([], report.to_dict()["failing_samples"])
        self.assertEqual("3", report.to_dict()["threshold_db"])

    def test_report_rejects_tampering_and_duplicate_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            report = evaluate_link_margin(load_link_csv(self.write(
                directory, HEADER + "2026-09-21T00:00:00Z,2\n"
            )), 3)
            document = report.to_dict()
            mutations = []
            for field, value in (
                ("passed", True), ("failure_count", 0),
                ("minimum_link_margin_db", "2.5"), ("threshold_db", "2"),
            ):
                changed = report.to_dict()
                changed[field] = value
                mutations.append(changed)
            changed = report.to_dict()
            changed["failing_samples"][0]["link_margin_db"] = "3"
            mutations.append(changed)
            changed = report.to_dict()
            changed["unexpected"] = True
            mutations.append(changed)
            for changed in mutations:
                with self.subTest(changed), self.assertRaises(TelemetryError):
                    LinkMarginReport.from_json(json.dumps(changed))
            duplicate = report.to_json()[:-1] + ',"passed":false}'
            with self.assertRaisesRegex(TelemetryError, "Duplicate"):
                LinkMarginReport.from_json(duplicate)
            self.assertEqual(1, document["failure_count"])

    def test_rejects_missing_wrong_and_empty_schema(self):
        invalid = ("", "timestamp_utc,margin_db\n2026-09-21T00:00:00Z,3\n",
                   HEADER, HEADER + "\n", HEADER + "2026-09-21T00:00:00Z\n",
                   HEADER + "2026-09-21T00:00:00Z,3,extra\n")
        for content in invalid:
            with self.subTest(repr(content)), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(TelemetryError):
                    load_link_csv(self.write(directory, content))

    def test_rejects_encoding_bom_and_malformed_csv(self):
        invalid = (b"\xff\xfe", b"\xef\xbb\xbftimestamp_utc,link_margin_db\n",
                   b'timestamp_utc,link_margin_db\n"unterminated,3\n')
        for content in invalid:
            with self.subTest(content), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(TelemetryError):
                    load_link_csv(self.write(directory, content))

    def test_rejects_invalid_or_non_increasing_timestamps(self):
        timestamps = ("not-a-time", "2026-09-21T00:00:00", "2026-09-21T08:00:00+08:00",
                      " 2026-09-21T00:00:00Z", "2026-09-21T00:00:00Z ",
                      "2026-09-21 00:00:00Z", "20260921T000000Z",
                      "2026-W39-1T00:00:00Z", "2026-09-21T00:00:00+00",
                      "2026-09-21T00:00:00-00:00",
                      "2026-09-21T00:00:00.1234567Z")
        for timestamp in timestamps:
            with self.subTest(timestamp), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(TelemetryError):
                    load_link_csv(self.write(directory, HEADER + f"{timestamp},3\n"))
        for second in ("2026-09-21T00:00:00Z", "2026-09-20T23:59:59Z"):
            with self.subTest(second), tempfile.TemporaryDirectory() as directory:
                content = HEADER + "2026-09-21T00:00:00Z,3\n" + f"{second},4\n"
                with self.assertRaises(TelemetryError):
                    load_link_csv(self.write(directory, content))

    def test_rejects_invalid_margins_and_thresholds(self):
        for margin in ("", " 3", "3 ", "nan", "inf", "-inf", "nope", "1_000",
                       "٠.٥", "１２"):
            with self.subTest(margin), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(TelemetryError):
                    load_link_csv(self.write(
                        directory, HEADER + f"2026-09-21T00:00:00Z,{margin}\n"))
        with tempfile.TemporaryDirectory() as directory:
            telemetry = load_link_csv(self.write(
                directory, HEADER + "2026-09-21T00:00:00Z,3\n"))
            for threshold in (True, float("nan"), float("inf"), "3"):
                with self.subTest(threshold), self.assertRaises(TelemetryError):
                    link_margin_passes(telemetry, threshold)
            precise = self.write(
                directory,
                HEADER + "2026-09-21T00:00:00Z,2.999999999999999999999999999999\n",
            )
            self.assertFalse(link_margin_passes(load_link_csv(precise), 3.0))
            self.assertFalse(link_margin_passes(telemetry, 10**10000))

    def test_public_value_constructors_reject_unvalidated_state(self):
        for call in (
            lambda: InputIdentity("A" * 64, 1),
            lambda: InputIdentity("0" * 64, True),
            lambda: LinkSample("not-utc", 3.0),
            lambda: LinkSample(1, Decimal("3")),
            lambda: LinkSample(b"2026-09-21T00:00:00Z", Decimal("3")),
            lambda: LinkSample("2026-09-21T00:00:00Z", Decimal("NaN")),
            lambda: LinkSample("2026-09-21T00:00:00Z", 10**10000),
            lambda: LinkTelemetry("0" * 64, 1, ()),
            lambda: LinkTelemetry("0" * 64, 1, (object(),)),
            lambda: LinkTelemetry("0" * 64, 1, (
                LinkSample("2026-09-21T00:00:01Z", Decimal("3.0")),
                LinkSample("2026-09-21T00:00:00Z", Decimal("3.0")))),
        ):
            with self.subTest(call), self.assertRaises(TelemetryError):
                call()

    def test_rejects_changed_identity_and_invalid_expected_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, HEADER + "2026-09-21T00:00:00Z,3\n")
            identity = identify_link_csv(path)
            path.write_text(HEADER + "2026-09-21T00:00:00Z,2\n", encoding="utf-8")
            with self.assertRaisesRegex(TelemetryError, "identity changed"):
                load_link_csv(path, expected_sha256=identity.sha256)
            for digest in ("", "A" * 64, "g" * 64, 3):
                with self.subTest(digest), self.assertRaises(TelemetryError):
                    load_link_csv(path, expected_sha256=digest)  # type: ignore[arg-type]

    def test_size_and_row_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            exact = self.write(directory, b"x" * 1_048_576)
            self.assertEqual(1_048_576, identify_link_csv(exact).byte_length)
            path = self.write(directory, b"x" * (1_048_576 + 1))
            with self.assertRaisesRegex(TelemetryError, "exceeds"):
                identify_link_csv(path)
        with tempfile.TemporaryDirectory() as directory:
            rows = [HEADER]
            start = 1_700_000_000
            for offset in range(10_000):
                rows.append(
                    f"{datetime.fromtimestamp(start + offset, timezone.utc).isoformat()},3\n"
                )
            path = self.write(directory, "".join(rows))
            self.assertEqual(10_000, len(load_link_csv(path).samples))
            rows.append(
                f"{datetime.fromtimestamp(start + 10_000, timezone.utc).isoformat()},3\n"
            )
            path = self.write(directory, "".join(rows))
            with self.assertRaisesRegex(TelemetryError, "samples"):
                load_link_csv(path)

    def test_completed_journal_export_storage_and_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, HEADER +
                              "2026-09-21T00:00:00Z,4\n"
                              "2026-09-21T00:00:01Z,2.999999999999999999999999999999\n")
            identity = identify_link_csv(path)
            counts = {"ingest": 0, "check": 0, "report": 0}

            def ingest():
                counts["ingest"] += 1
                return load_link_csv(path, expected_sha256=identity.sha256).manifest()

            def check():
                counts["check"] += 1
                return link_margin_passes(
                    load_link_csv(path, expected_sha256=identity.sha256), 3.0)

            def report():
                counts["report"] += 1
                return evaluate_link_margin(
                    load_link_csv(path, expected_sha256=identity.sha256), 3.0
                ).to_dict()

            tasks = (JournalTask("ingest", ingest, "csv:" + identity.sha256),
                     JournalTask("config", lambda: {
                         "rule": "minimum_link_margin_gte",
                         "threshold_db": "3.0",
                         "unit": "dB",
                     }, "margin-config:3.0"),
                     JournalTask("check", check, "margin:3:" + identity.sha256,
                                 ("config", "ingest")),
                     JournalTask("report", report, "report:3:" + identity.sha256,
                                 ("check",)))
            plan = JournalPlan.from_tasks(tasks)
            journal_path = Path(directory, "journal.sqlite")
            run = run_journaled(journal_path, tasks)
            evidence = export_journal_evidence(journal_path, run.run_id, plan)
            bindings = RequirementBindings.from_mapping({"COM-LINK-001": "check"})
            with EvidenceStore(Path(directory, "evidence.sqlite")) as store:
                store.save(evidence, bindings)
                reopened = store.load(run.run_id, bindings.sha256)
            self.assertEqual("fail", assess_requirements(*reopened).outcomes[0].verdict)
            self.assertEqual({"ingest": 1, "check": 1, "report": 1}, counts)
            evidence_tasks = {
                item["task_id"]: item for item in evidence.to_dict()["tasks"]
            }
            ingest_value = evidence_tasks["ingest"]["value"]
            self.assertEqual(identity.sha256, ingest_value["input_sha256"])
            self.assertEqual("2.999999999999999999999999999999",
                             ingest_value["minimum_link_margin_db"])
            self.assertEqual("3.0", evidence_tasks["config"]["value"]["threshold_db"])
            report_value = evidence_tasks["report"]["value"]
            self.assertEqual("succeeded", evidence_tasks["report"]["status"])
            self.assertFalse(report_value["passed"])
            self.assertEqual(1, report_value["failure_count"])
            self.assertEqual(
                "2.999999999999999999999999999999",
                report_value["failing_samples"][0]["link_margin_db"],
            )
            self.assertEqual(report_value, LinkMarginReport.from_json(
                json.dumps(report_value)
            ).to_dict())

    def test_file_change_between_ingest_and_check_is_error_never_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            original = HEADER + "2026-09-21T00:00:00Z,4\n"
            path = self.write(directory, original)
            identity = identify_link_csv(path)

            def ingest():
                manifest = load_link_csv(path, expected_sha256=identity.sha256).manifest()
                path.write_text(HEADER + "2026-09-21T00:00:00Z,5\n", encoding="utf-8")
                return manifest

            tasks = (JournalTask("ingest", ingest, "csv:" + identity.sha256),
                     JournalTask("check", lambda: link_margin_passes(
                         load_link_csv(path, expected_sha256=identity.sha256), 3.0),
                         "margin:3:" + identity.sha256, ("ingest",)))
            plan = JournalPlan.from_tasks(tasks)
            journal_path = Path(directory, "journal.sqlite")
            run = run_journaled(journal_path, tasks)
            evidence = export_journal_evidence(journal_path, run.run_id, plan)
            document = evidence.to_dict()
            self.assertEqual("succeeded", document["tasks"][0]["status"])
            self.assertEqual("failed", document["tasks"][1]["status"])
            self.assertIn("identity changed", document["tasks"][1]["error"])
            assessment = assess_requirements(
                evidence, RequirementBindings.from_mapping({"COM-LINK-001": "check"}))
            self.assertEqual("error", assessment.outcomes[0].verdict)

    def test_file_change_after_failed_check_prevents_mismatched_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, HEADER + "2026-09-21T00:00:00Z,2\n")
            identity = identify_link_csv(path)

            def check():
                result = link_margin_passes(
                    load_link_csv(path, expected_sha256=identity.sha256), 3
                )
                path.write_text(
                    HEADER + "2026-09-21T00:00:00Z,4\n", encoding="utf-8"
                )
                return result

            tasks = (
                JournalTask("ingest", lambda: load_link_csv(
                    path, expected_sha256=identity.sha256
                ).manifest(), "csv:" + identity.sha256),
                JournalTask("check", check, "margin:3:" + identity.sha256, ("ingest",)),
                JournalTask("report", lambda: evaluate_link_margin(
                    load_link_csv(path, expected_sha256=identity.sha256), 3
                ).to_dict(), "report:3:" + identity.sha256, ("check",)),
            )
            plan = JournalPlan.from_tasks(tasks)
            journal_path = Path(directory, "journal.sqlite")
            run = run_journaled(journal_path, tasks)
            evidence = export_journal_evidence(journal_path, run.run_id, plan)
            document = evidence.to_dict()
            self.assertEqual("succeeded", document["tasks"][1]["status"])
            self.assertIs(document["tasks"][1]["value"], False)
            self.assertEqual("failed", document["tasks"][2]["status"])
            self.assertIn("identity changed", document["tasks"][2]["error"])
            assessment = assess_requirements(
                evidence, RequirementBindings.from_mapping({"COM-LINK-001": "check"})
            )
            self.assertEqual("fail", assessment.outcomes[0].verdict)

    def test_malformed_input_is_error_and_check_is_not_evaluated(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(__file__).parents[1] / "examples/fixtures/link_margin_malformed.csv"
            path = Path(directory, "telemetry.csv")
            path.write_bytes(fixture.read_bytes())
            identity = identify_link_csv(path)
            tasks = (JournalTask(
                "ingest", lambda: load_link_csv(path, expected_sha256=identity.sha256).manifest(),
                "csv:" + identity.sha256),
                JournalTask("check", lambda: True, "margin:3:" + identity.sha256,
                            ("ingest",)),
                JournalTask("report", lambda: {"should": "not run"},
                            "report:3:" + identity.sha256, ("check",)))
            plan = JournalPlan.from_tasks(tasks)
            journal_path = Path(directory, "journal.sqlite")
            run = run_journaled(journal_path, tasks)
            evidence = export_journal_evidence(journal_path, run.run_id, plan)
            assessment = assess_requirements(
                evidence, RequirementBindings.from_mapping({"COM-LINK-001": "check"}))
            document = evidence.to_dict()
            self.assertEqual("failed", document["tasks"][0]["status"])
            self.assertEqual("blocked", document["tasks"][1]["status"])
            self.assertEqual("blocked", document["tasks"][2]["status"])
            self.assertEqual("not_evaluated", assessment.outcomes[0].verdict)


if __name__ == "__main__":
    unittest.main()
