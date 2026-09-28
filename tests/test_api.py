import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chimera import (CompletedLinkRun, CompletedRunApp, OperatorAPIError,
                     run_link_verification)
from chimera.cli import main


FIXTURES = Path(__file__).parents[1] / "examples" / "fixtures"


def request(app, path="/api/v1/run", method="GET"):
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    response["body"] = b"".join(app({
        "REQUEST_METHOD": method, "PATH_INFO": path,
    }, start_response))
    return response


class CompletedRunAPITests(unittest.TestCase):
    def _run(self, directory: str, fault: bool = False) -> Path:
        output = Path(directory, "run")
        run_link_verification(
            FIXTURES / "link_margin_passed.csv", output, threshold_db="3.0",
            fault_plan_path=(FIXTURES / "link_fault_plan.json") if fault else None,
        )
        return output

    def test_reopens_passing_artifacts_and_builds_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = CompletedLinkRun.open(self._run(directory))
            summary = completed.summary()
            self.assertEqual("pass", summary["verdict"])
            self.assertFalse(summary["synthetic"])
            self.assertEqual(completed.report.sha256, summary["report_sha256"])
            self.assertEqual("/report", summary["links"]["report_html"])

    def test_reopens_synthetic_failure_with_explicit_label(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = CompletedLinkRun.open(self._run(directory, fault=True))
            self.assertEqual("fail", completed.summary()["verdict"])
            self.assertTrue(completed.summary()["synthetic"])

    def test_wsgi_endpoints_are_read_only_and_hardened(self):
        with tempfile.TemporaryDirectory() as directory:
            app = CompletedRunApp(CompletedLinkRun.open(self._run(directory)))
            summary = request(app)
            self.assertEqual("200 OK", summary["status"])
            self.assertEqual("nosniff", summary["headers"]["X-Content-Type-Options"])
            self.assertEqual("no-store", summary["headers"]["Cache-Control"])
            self.assertEqual("pass", json.loads(summary["body"])["verdict"])

            report = request(app, "/api/v1/report")
            self.assertEqual("pass", json.loads(report["body"])["requirement"]["verdict"])
            html = request(app, "/report")
            self.assertEqual("200 OK", html["status"])
            self.assertIn("default-src 'none'", html["headers"]["Content-Security-Policy"])
            self.assertIn(b"Chimera verification report", html["body"])

            denied = request(app, method="POST")
            self.assertEqual("405 Method Not Allowed", denied["status"])
            self.assertEqual("GET", denied["headers"]["Allow"])
            self.assertNotIn("Access-Control-Allow-Origin", denied["headers"])
            self.assertEqual("404 Not Found", request(app, "/missing")["status"])

    def test_rejects_report_that_does_not_match_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self._run(directory)
            report = json.loads((output / "report.json").read_text())
            report["requirement"]["reason"] = "changed"
            (output / "report.json").write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(OperatorAPIError, "artifact|conflicts"):
                CompletedLinkRun.open(output)

    def test_rejects_request_threshold_that_does_not_match_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self._run(directory)
            saved = json.loads((output / "request.json").read_text())
            saved["threshold_db"] = "2.5"
            (output / "request.json").write_text(json.dumps(saved), encoding="utf-8")
            with self.assertRaisesRegex(OperatorAPIError, "threshold conflicts"):
                CompletedLinkRun.open(output)

    def test_rejects_noncanonical_uuid_spellings(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._run(directory)
            canonical = json.loads((source / "request.json").read_text())["run_id"]
            for index, changed in enumerate((
                    canonical.upper(), "{" + canonical + "}", canonical.replace("-", ""))):
                with self.subTest(changed=changed):
                    target = Path(directory, f"changed-{index}")
                    target.mkdir()
                    for artifact in source.iterdir():
                        if artifact.is_file():
                            (target / artifact.name).write_bytes(artifact.read_bytes())
                    request = json.loads((target / "request.json").read_text())
                    request["run_id"] = changed
                    (target / "request.json").write_text(
                        json.dumps(request), encoding="utf-8"
                    )
                    with self.assertRaisesRegex(
                            OperatorAPIError, "canonical lowercase UUID"):
                        CompletedLinkRun.open(target)

    def test_rejects_evidence_request_and_html_tampering(self):
        for filename in ("evidence.json", "request.json", "report.html"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                output = self._run(directory)
                path = output / filename
                path.write_bytes(path.read_bytes() + b"x")
                with self.assertRaises(OperatorAPIError):
                    CompletedLinkRun.open(output)

    def test_rejects_symbolic_link_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self._run(directory)
            target = Path(directory, "outside.json")
            target.write_text((output / "report.json").read_text(), encoding="utf-8")
            (output / "report.json").unlink()
            (output / "report.json").symlink_to(target)
            with self.assertRaisesRegex(OperatorAPIError, "regular file"):
                CompletedLinkRun.open(output)

    def test_rejects_oversized_artifact_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self._run(directory)
            (output / "request.json").write_bytes(b" " * 65_537)
            with self.assertRaisesRegex(OperatorAPIError, "exceeds"):
                CompletedLinkRun.open(output)

    def test_cli_server_uses_validated_run_and_fixed_loopback_implementation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self._run(directory)
            with patch("chimera.cli.serve_completed_run") as serve:
                self.assertEqual(0, main(["serve-link", str(output), "--port", "9999"]))
            serve.assert_called_once_with(output, 9999)

    def test_cli_rejects_invalid_completed_run_without_starting_server(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(3, main(["serve-link", directory, "--port", "8765"]))


if __name__ == "__main__":
    unittest.main()
