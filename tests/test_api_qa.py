import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chimera import (CompletedLinkRun, OperatorAPIError, RequirementBindings,
                     RunEvidence, VerificationReport, run_link_verification,
                     serve_completed_run)


FIXTURES = Path(__file__).parents[1] / "examples" / "fixtures"


class CompletedRunIndependentQATests(unittest.TestCase):
    def _run(self, directory: str, threshold: str = "3.0") -> Path:
        output = Path(directory, "run")
        run_link_verification(
            FIXTURES / "link_margin_passed.csv", output,
            threshold_db=threshold,
        )
        return output

    @staticmethod
    def _rewrite_report(output: Path, evidence_document: dict) -> None:
        evidence = RunEvidence.from_json(json.dumps(evidence_document))
        bindings = RequirementBindings.from_json(
            (output / "bindings.json").read_text(encoding="utf-8")
        )
        report = VerificationReport.from_evidence(
            evidence, bindings, detail_task_id="detail"
        )
        (output / "evidence.json").write_text(
            evidence.to_json() + "\n", encoding="utf-8"
        )
        (output / "report.json").write_text(
            report.to_json() + "\n", encoding="utf-8"
        )
        (output / "report.html").write_text(report.to_html(), encoding="utf-8")

    def test_rejects_non_synthetic_detail_from_different_input(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self._run(directory)
            evidence = json.loads((output / "evidence.json").read_text())
            detail = next(
                task for task in evidence["tasks"] if task["task_id"] == "detail"
            )
            detail["value"]["input_sha256"] = "0" * 64
            self._rewrite_report(output, evidence)
            with self.assertRaisesRegex(OperatorAPIError, "input|source"):
                CompletedLinkRun.open(output)

    def test_rejects_request_journal_plan_digest_not_derived_from_request(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self._run(directory)
            request = json.loads((output / "request.json").read_text())
            request["journal_plan_sha256"] = "0" * 64
            (output / "request.json").write_text(
                json.dumps(request), encoding="utf-8"
            )
            with self.assertRaisesRegex(OperatorAPIError, "journal plan"):
                CompletedLinkRun.open(output)

    def test_valid_equivalent_decimal_spellings_reopen(self):
        for threshold in ("+3.0", "3.00", "3e0"):
            with self.subTest(threshold=threshold), tempfile.TemporaryDirectory() as directory:
                completed = CompletedLinkRun.open(self._run(directory, threshold))
                self.assertEqual("pass", completed.summary()["verdict"])

    def test_rejects_unexpected_completed_evidence_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self._run(directory)
            evidence = json.loads((output / "evidence.json").read_text())
            evidence["tasks"].append({
                "task_id": "unrequested", "status": "succeeded", "value": True,
                "error": None, "dependencies": [],
            })
            self._rewrite_report(output, evidence)
            with self.assertRaisesRegex(OperatorAPIError, "task graph"):
                CompletedLinkRun.open(output)

    def test_completed_view_cannot_be_forged_or_mutated_through_request(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = CompletedLinkRun.open(self._run(directory))
            with self.assertRaises(TypeError):
                completed.request["workflow"] = "changed"
            with self.assertRaises(TypeError):
                CompletedLinkRun(
                    dict(completed.request), completed.evidence,
                    completed.bindings, completed.report,
                )

    def test_server_uses_only_ipv4_loopback_and_validates_port(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self._run(directory)
            with patch("chimera.api.make_server") as make_server:
                server = make_server.return_value.__enter__.return_value
                serve_completed_run(output, 9876)
            self.assertEqual("127.0.0.1", make_server.call_args.args[0])
            self.assertEqual(9876, make_server.call_args.args[1])
            server.serve_forever.assert_called_once_with()
            for invalid in (True, 0, 65_536, "8765"):
                with self.subTest(port=invalid), self.assertRaises(OperatorAPIError):
                    serve_completed_run(output, invalid)


if __name__ == "__main__":
    unittest.main()
