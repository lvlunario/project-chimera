import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from chimera.dashboard import CompletedRunWorkspace, DashboardApp, MAX_WORKSPACE_ENTRIES
from chimera.bindings import RequirementBindings
from chimera.evidence import RunEvidence
from chimera.operator import run_link_verification
from chimera.reports import VerificationReport


FIXTURES = Path(__file__).parents[1] / "examples" / "fixtures"


def response(app, path):
    result = {}

    def start(status, headers):
        result["status"] = status
        result["headers"] = dict(headers)

    result["body"] = b"".join(app({
        "REQUEST_METHOD": "GET", "PATH_INFO": path,
    }, start))
    return result


class DashboardIndependentQATests(unittest.TestCase):
    def test_invalid_artifact_is_visible_but_never_routable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "tampered"
            result = run_link_verification(
                FIXTURES / "link_margin_passed.csv", output, threshold_db="3.0"
            )
            (output / "report.html").write_text("changed", encoding="utf-8")
            workspace = CompletedRunWorkspace.open(root)
            document = workspace.document()
            self.assertEqual(0, document["run_count"])
            self.assertEqual(1, document["invalid_count"])
            self.assertIn("Saved HTML conflicts", document["invalid_entries"][0]["reason"])
            app = DashboardApp(workspace)
            self.assertEqual(
                "404 Not Found", response(app, f"/runs/{result.run_id}")["status"]
            )

    def test_names_and_validation_errors_are_html_escaped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "<bad&name>").mkdir()
            body = response(DashboardApp(CompletedRunWorkspace.open(root)), "/")["body"]
            self.assertNotIn(b"<bad&name>", body)
            self.assertIn(b"&lt;bad&amp;name&gt;", body)

    def test_workspace_entry_bound_prevents_unbounded_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumed = []

            def entries():
                for index in range(MAX_WORKSPACE_ENTRIES + 500):
                    consumed.append(index)
                    yield root / f"entry-{index:04d}"

            with patch("pathlib.Path.iterdir", return_value=entries()):
                with self.assertRaisesRegex(ValueError, "exceeds"):
                    CompletedRunWorkspace.open(root)
            self.assertEqual(MAX_WORKSPACE_ENTRIES + 1, len(consumed))

    def test_non_utf8_entry_name_cannot_break_json_or_html(self):
        if os.name != "posix":
            self.skipTest("byte filenames require POSIX")
        with tempfile.TemporaryDirectory() as directory:
            raw = os.fsencode(directory) + b"/bad-\xff"
            descriptor = os.open(raw, os.O_WRONLY | os.O_CREAT, 0o600)
            os.close(descriptor)
            app = DashboardApp(CompletedRunWorkspace.open(directory))
            api = response(app, "/api/v1/runs")
            page = response(app, "/")
            self.assertEqual("200 OK", api["status"])
            self.assertEqual("200 OK", page["status"])
            self.assertEqual(
                "bad-\\udcff",
                json.loads(api["body"])["invalid_entries"][0]["name"],
            )

    def test_workspace_snapshot_cannot_bypass_open_validation(self):
        with self.assertRaises(TypeError):
            CompletedRunWorkspace({}, ())

    def test_json_is_deterministic_for_one_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_link_verification(
                FIXTURES / "link_margin_passed.csv", root / "run", threshold_db="3.0"
            )
            app = DashboardApp(CompletedRunWorkspace.open(root))
            first = response(app, "/api/v1/runs")["body"]
            second = response(app, "/api/v1/runs")["body"]
            self.assertEqual(first, second)
            self.assertEqual(1, json.loads(first)["schema_version"])

    def test_alternate_uuid_spelling_cannot_bypass_duplicate_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original"
            run_link_verification(
                FIXTURES / "link_margin_passed.csv", original, threshold_db="3.0"
            )
            alternate = root / "uppercase-id"
            shutil.copytree(original, alternate)

            request = json.loads((alternate / "request.json").read_text())
            request["run_id"] = request["run_id"].upper()
            (alternate / "request.json").write_text(
                json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            evidence_document = json.loads((alternate / "evidence.json").read_text())
            evidence_document["run_id"] = evidence_document["run_id"].upper()
            evidence = RunEvidence.from_json(json.dumps(evidence_document))
            bindings = RequirementBindings.from_json(
                (alternate / "bindings.json").read_text(encoding="utf-8")
            )
            report = VerificationReport.from_evidence(
                evidence, bindings, detail_task_id="detail"
            )
            (alternate / "evidence.json").write_text(
                evidence.to_json() + "\n", encoding="utf-8"
            )
            (alternate / "report.json").write_text(
                report.to_json() + "\n", encoding="utf-8"
            )
            (alternate / "report.html").write_text(
                report.to_html(), encoding="utf-8"
            )

            document = CompletedRunWorkspace.open(root).document()
            self.assertEqual(1, document["run_count"])
            self.assertEqual(1, document["invalid_count"])
            self.assertIn(
                "canonical lowercase UUID", document["invalid_entries"][0]["reason"]
            )


if __name__ == "__main__":
    unittest.main()
