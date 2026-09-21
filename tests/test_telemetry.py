import tempfile
import unittest
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

from chimera import (EvidenceStore, InputIdentity, JournalPlan, JournalTask, LinkSample,
                     LinkTelemetry, RequirementBindings, TelemetryError,
                     assess_requirements, export_journal_evidence,
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
            counts = {"ingest": 0, "check": 0}

            def ingest():
                counts["ingest"] += 1
                return load_link_csv(path, expected_sha256=identity.sha256).manifest()

            def check():
                counts["check"] += 1
                return link_margin_passes(
                    load_link_csv(path, expected_sha256=identity.sha256), 3.0)

            tasks = (JournalTask("ingest", ingest, "csv:" + identity.sha256),
                     JournalTask("config", lambda: {
                         "rule": "minimum_link_margin_gte",
                         "threshold_db": "3.0",
                         "unit": "dB",
                     }, "margin-config:3.0"),
                     JournalTask("check", check, "margin:3:" + identity.sha256,
                                 ("config", "ingest")))
            plan = JournalPlan.from_tasks(tasks)
            journal_path = Path(directory, "journal.sqlite")
            run = run_journaled(journal_path, tasks)
            evidence = export_journal_evidence(journal_path, run.run_id, plan)
            bindings = RequirementBindings.from_mapping({"COM-LINK-001": "check"})
            with EvidenceStore(Path(directory, "evidence.sqlite")) as store:
                store.save(evidence, bindings)
                reopened = store.load(run.run_id, bindings.sha256)
            self.assertEqual("fail", assess_requirements(*reopened).outcomes[0].verdict)
            self.assertEqual({"ingest": 1, "check": 1}, counts)
            evidence_tasks = {
                item["task_id"]: item for item in evidence.to_dict()["tasks"]
            }
            ingest_value = evidence_tasks["ingest"]["value"]
            self.assertEqual(identity.sha256, ingest_value["input_sha256"])
            self.assertEqual("2.999999999999999999999999999999",
                             ingest_value["minimum_link_margin_db"])
            self.assertEqual("3.0", evidence_tasks["config"]["value"]["threshold_db"])

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

    def test_malformed_input_is_error_and_check_is_not_evaluated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, HEADER + "bad-time,2\n")
            identity = identify_link_csv(path)
            tasks = (JournalTask(
                "ingest", lambda: load_link_csv(path, expected_sha256=identity.sha256).manifest(),
                "csv:" + identity.sha256),
                JournalTask("check", lambda: True, "margin:3:" + identity.sha256,
                            ("ingest",)))
            plan = JournalPlan.from_tasks(tasks)
            journal_path = Path(directory, "journal.sqlite")
            run = run_journaled(journal_path, tasks)
            evidence = export_journal_evidence(journal_path, run.run_id, plan)
            assessment = assess_requirements(
                evidence, RequirementBindings.from_mapping({"COM-LINK-001": "check"}))
            document = evidence.to_dict()
            self.assertEqual("failed", document["tasks"][0]["status"])
            self.assertEqual("blocked", document["tasks"][1]["status"])
            self.assertEqual("not_evaluated", assessment.outcomes[0].verdict)


if __name__ == "__main__":
    unittest.main()
