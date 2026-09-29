from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from wsgiref.simple_server import WSGIRequestHandler, make_server

from chimera.dashboard import CompletedRunWorkspace, DashboardApp
from chimera.handoff import inspect_handoff_bundle
from chimera.operator import run_link_verification


FIXTURES = Path(__file__).parents[1] / "examples" / "fixtures"


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


class SemanticAudit(HTMLParser):
    """Small dependency-free audit for the dashboard's declared HTML contract."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.html_language = None
        self.main_count = 0
        self.h1_count = 0
        self.caption_count = 0
        self.scoped_headers = 0
        self.focus_rule = False
        self.links: list[dict[str, object]] = []
        self._link: dict[str, object] | None = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "html":
            self.html_language = values.get("lang")
        elif tag == "main":
            self.main_count += 1
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "caption":
            self.caption_count += 1
        elif tag == "th" and values.get("scope") == "col":
            self.scoped_headers += 1
        elif tag == "a":
            self._link = {"href": values.get("href"), "text": ""}

    def handle_endtag(self, tag):
        if tag == "a" and self._link is not None:
            self.links.append(self._link)
            self._link = None

    def handle_data(self, data):
        if self._link is not None:
            self._link["text"] = str(self._link["text"]) + data
        if "a:focus" in data and "outline:" in data:
            self.focus_rule = True

    def assert_accessible(self, case: unittest.TestCase):
        case.assertEqual("en", self.html_language)
        case.assertEqual(1, self.main_count)
        case.assertEqual(1, self.h1_count)
        case.assertGreaterEqual(self.caption_count, 1)
        case.assertGreaterEqual(self.scoped_headers, 3)
        case.assertTrue(self.focus_rule)
        case.assertTrue(self.links)
        case.assertTrue(all(item["href"] and str(item["text"]).strip()
                            for item in self.links))


class DashboardHTTPEndToEndTests(unittest.TestCase):
    def _get(self, base: str, path: str):
        with urlopen(base + path, timeout=2) as response:
            return response.status, dict(response.headers), response.read()

    def test_real_loopback_journey_preserves_audit_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_link_verification(
                FIXTURES / "link_margin_passed.csv", root / "synthetic-failure",
                threshold_db="3.0", fault_plan_path=FIXTURES / "link_fault_plan.json",
            )
            application = DashboardApp(CompletedRunWorkspace.open(root))
            server = make_server(
                "127.0.0.1", 0, application, handler_class=QuietHandler
            )
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                status, headers, index = self._get(base, "/")
                self.assertEqual(200, status)
                self.assertEqual("no-store", headers["Cache-Control"])
                self.assertIn(result.run_id.encode(), index)

                _, _, detail = self._get(base, f"/runs/{result.run_id}")
                self.assertIn(b"COM-LINK-001 evidence", detail)
                self.assertIn(b">2.0<", detail)

                _, _, report = self._get(
                    base, f"/api/v1/runs/{result.run_id}/report"
                )
                _, _, evidence = self._get(
                    base, f"/api/v1/runs/{result.run_id}/evidence"
                )
                _, _, bindings = self._get(
                    base, f"/api/v1/runs/{result.run_id}/bindings"
                )
                _, handoff_headers, handoff = self._get(
                    base, f"/api/v1/runs/{result.run_id}/handoff"
                )
                run_directory = root / "synthetic-failure"
                self.assertEqual((run_directory / "report.json").read_bytes(), report)
                self.assertEqual((run_directory / "evidence.json").read_bytes(), evidence)
                self.assertEqual((run_directory / "bindings.json").read_bytes(), bindings)
                self.assertEqual("fail", json.loads(report)["requirement"]["verdict"])
                self.assertEqual(result.run_id, json.loads(evidence)["run_id"])
                self.assertEqual(
                    [{"requirement_id": "COM-LINK-001", "task_id": "check"}],
                    json.loads(bindings)["bindings"],
                )
                self.assertEqual("application/zip", handoff_headers["Content-Type"])
                self.assertIn("attachment;", handoff_headers["Content-Disposition"])
                bundle_path = root / "downloaded.zip"
                bundle_path.write_bytes(handoff)
                self.assertEqual(result.run_id,
                                 inspect_handoff_bundle(bundle_path)["run_id"])
                with self.assertRaises(HTTPError) as missing:
                    self._get(base, "/api/v1/runs/not-a-run/evidence")
                self.assertEqual(404, missing.exception.code)
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()

    def test_index_and_detail_pass_structural_accessibility_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_link_verification(
                FIXTURES / "link_margin_passed.csv", root / "passing",
                threshold_db="3.0",
            )
            application = DashboardApp(CompletedRunWorkspace.open(root))
            for path in ("/", f"/runs/{result.run_id}"):
                response = {}

                def start(status, headers):
                    response["status"] = status

                body = b"".join(application({
                    "REQUEST_METHOD": "GET", "PATH_INFO": path,
                }, start)).decode("utf-8")
                audit = SemanticAudit()
                audit.feed(body)
                audit.assert_accessible(self)
                self.assertIn("PASS", body)


if __name__ == "__main__":
    unittest.main()
