import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chimera.dashboard import (CompletedRunWorkspace, DashboardApp, DashboardError,
                               serve_dashboard)
from chimera.cli import main
from chimera.operator import run_link_verification


FIXTURES = Path(__file__).parents[1] / "examples" / "fixtures"


def request(app, path="/", method="GET", query=""):
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    response["body"] = b"".join(app({
        "REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
    }, start_response))
    return response


class DashboardTests(unittest.TestCase):
    def _run(self, root: Path, name: str, fault: bool = False):
        result = run_link_verification(
            FIXTURES / "link_margin_passed.csv", root / name,
            threshold_db="3.0",
            fault_plan_path=(FIXTURES / "link_fault_plan.json") if fault else None,
        )
        return result

    def test_discovers_pass_fail_and_visible_invalid_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            passed = self._run(root, "passed")
            failed = self._run(root, "failed", fault=True)
            (root / "broken").mkdir()
            workspace = CompletedRunWorkspace.open(root)
            document = workspace.document()
            self.assertEqual(2, document["run_count"])
            self.assertEqual(1, document["invalid_count"])
            self.assertEqual({"pass", "fail"}, {
                item["verdict"] for item in document["runs"]
            })
            self.assertEqual("broken", document["invalid_entries"][0]["name"])
            self.assertIsNotNone(workspace.get(passed.run_id))
            self.assertIsNotNone(workspace.get(failed.run_id))

    def test_empty_workspace_has_accessible_index_and_canonical_api(self):
        with tempfile.TemporaryDirectory() as directory:
            app = DashboardApp(CompletedRunWorkspace.open(directory))
            page = request(app)
            self.assertEqual("200 OK", page["status"])
            self.assertIn(b'<html lang="en">', page["body"])
            self.assertIn(b"No runs match this view", page["body"])
            self.assertIn(b"<caption>", page["body"])
            self.assertIn("default-src 'none'", page["headers"]["Content-Security-Policy"])
            api = request(app, "/api/v1/runs")
            self.assertEqual(0, json.loads(api["body"])["run_count"])

    def test_index_views_filter_without_changing_validated_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            passed = self._run(root, "passed")
            failed = self._run(root, "failed", fault=True)
            (root / "broken").mkdir()
            app = DashboardApp(CompletedRunWorkspace.open(root))

            all_view = request(app)
            self.assertIn(b'aria-label="Run views"', all_view["body"])
            self.assertIn(b'aria-current="page">All validated (2)', all_view["body"])
            self.assertIn(passed.run_id.encode(), all_view["body"])
            self.assertIn(failed.run_id.encode(), all_view["body"])
            self.assertIn(b"broken", all_view["body"])

            pass_view = request(app, query="view=pass")
            self.assertIn(passed.run_id.encode(), pass_view["body"])
            self.assertNotIn(failed.run_id.encode(), pass_view["body"])
            self.assertNotIn(b"broken", pass_view["body"])
            fail_view = request(app, query="view=fail")
            self.assertNotIn(passed.run_id.encode(), fail_view["body"])
            self.assertIn(failed.run_id.encode(), fail_view["body"])
            synthetic_view = request(app, query="view=synthetic")
            self.assertNotIn(passed.run_id.encode(), synthetic_view["body"])
            self.assertIn(failed.run_id.encode(), synthetic_view["body"])
            invalid_view = request(app, query="view=invalid")
            self.assertNotIn(passed.run_id.encode(), invalid_view["body"])
            self.assertNotIn(failed.run_id.encode(), invalid_view["body"])
            self.assertIn(b"broken", invalid_view["body"])

            api = request(app, "/api/v1/runs")
            self.assertEqual(2, json.loads(api["body"])["run_count"])

    def test_index_rejects_ambiguous_or_unbounded_view_query(self):
        with tempfile.TemporaryDirectory() as directory:
            app = DashboardApp(CompletedRunWorkspace.open(directory))
            for query in (
                "view=", "view=unknown", "view=pass&view=fail", "extra=pass",
                "view=pass;extra=fail", "view=" + "p" * 65,
            ):
                with self.subTest(query=query):
                    response = request(app, query=query)
                    self.assertEqual("400 Bad Request", response["status"])
                    self.assertEqual(
                        b'{"error":"invalid dashboard view"}\n', response["body"]
                    )

    def test_list_detail_report_navigation_and_read_only_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._run(root, "one")
            app = DashboardApp(CompletedRunWorkspace.open(root))
            index = request(app)
            self.assertIn(result.run_id.encode(), index["body"])

            detail = request(app, f"/runs/{result.run_id}")
            self.assertEqual("200 OK", detail["status"])
            self.assertIn(b"Open readable report", detail["body"])
            self.assertIn(b"COM-LINK-001 evidence", detail["body"])
            self.assertIn(b"Threshold", detail["body"])
            report = request(app, f"/runs/{result.run_id}/report")
            self.assertIn(b"Chimera verification report", report["body"])
            canonical = request(app, f"/api/v1/runs/{result.run_id}/report")
            self.assertEqual(
                "pass", json.loads(canonical["body"])["requirement"]["verdict"]
            )
            evidence = request(app, f"/api/v1/runs/{result.run_id}/evidence")
            self.assertEqual(result.run_id, json.loads(evidence["body"])["run_id"])
            bindings = request(app, f"/api/v1/runs/{result.run_id}/bindings")
            self.assertEqual(
                [{"requirement_id": "COM-LINK-001", "task_id": "check"}],
                json.loads(bindings["body"])["bindings"],
            )
            handoff = request(app, f"/api/v1/runs/{result.run_id}/handoff")
            self.assertEqual("application/zip", handoff["headers"]["Content-Type"])
            self.assertEqual(
                f'attachment; filename="chimera-{result.run_id}-handoff.zip"',
                handoff["headers"]["Content-Disposition"],
            )
            self.assertTrue(handoff["body"].startswith(b"PK"))
            denied = request(app, method="POST")
            self.assertEqual("405 Method Not Allowed", denied["status"])
            self.assertEqual("GET", denied["headers"]["Allow"])
            self.assertNotIn("Access-Control-Allow-Origin", denied["headers"])
            self.assertEqual("404 Not Found", request(app, "/runs/not-a-run")["status"])

    def test_rejects_symlink_workspace_and_duplicate_run_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._run(root, "original")
            duplicate = root / "duplicate"
            duplicate.mkdir()
            for source in (root / "original").iterdir():
                if source.is_file():
                    (duplicate / source.name).write_bytes(source.read_bytes())
            workspace = CompletedRunWorkspace.open(root)
            document = workspace.document()
            self.assertEqual(0, document["run_count"])
            self.assertEqual(2, document["invalid_count"])
            self.assertIsNone(workspace.get(result.run_id))
            self.assertTrue(all("duplicate run_id" in item["reason"]
                                for item in document["invalid_entries"]))

            link = root.parent / f"{root.name}-link"
            link.symlink_to(root, target_is_directory=True)
            try:
                with self.assertRaisesRegex(DashboardError, "unavailable"):
                    CompletedRunWorkspace.open(link)
            finally:
                link.unlink()

    def test_server_uses_ipv4_loopback_and_validates_port(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("chimera.dashboard.make_server") as make_server:
                server = make_server.return_value.__enter__.return_value
                serve_dashboard(directory, 9877)
            self.assertEqual("127.0.0.1", make_server.call_args.args[0])
            self.assertEqual(9877, make_server.call_args.args[1])
            server.serve_forever.assert_called_once_with()
            for invalid in (True, 0, 65_536, "8765"):
                with self.subTest(port=invalid), self.assertRaises(DashboardError):
                    serve_dashboard(directory, invalid)

    def test_cli_uses_workspace_and_reports_invalid_root(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("chimera.cli.serve_dashboard") as serve:
                self.assertEqual(0, main([
                    "serve-dashboard", directory, "--port", "9988"
                ]))
            serve.assert_called_once_with(Path(directory), 9988)
        self.assertEqual(3, main(["serve-dashboard", "/not/present/chimera-workspace"]))


if __name__ == "__main__":
    unittest.main()
