"""Real Chromium checks for the bounded local dashboard.

This suite is intentionally outside ``tests`` so Project Chimera retains zero runtime
dependencies. The dedicated CI job installs a pinned Playwright test tool and Chromium.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
from threading import Thread
import unittest
from wsgiref.simple_server import WSGIRequestHandler, make_server

from playwright.sync_api import sync_playwright

from chimera.dashboard import CompletedRunWorkspace, DashboardApp
from chimera.handoff import inspect_handoff_bundle
from chimera.operator import run_link_verification


FIXTURES = Path(__file__).parents[1] / "examples" / "fixtures"


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


class DashboardBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temporary = tempfile.TemporaryDirectory()
        cls.workspace = Path(cls._temporary.name)
        cls.passing = run_link_verification(
            FIXTURES / "link_margin_passed.csv", cls.workspace / "passing",
            threshold_db="3.0",
        )
        cls.natural_failure = run_link_verification(
            FIXTURES / "link_margin_failed.csv", cls.workspace / "natural-failure",
            threshold_db="3.0",
        )
        cls.synthetic_failure = run_link_verification(
            FIXTURES / "link_margin_passed.csv", cls.workspace / "synthetic-failure",
            threshold_db="3.0", fault_plan_path=FIXTURES / "link_fault_plan.json",
        )
        broken = cls.workspace / "broken-entry"
        broken.mkdir()
        (broken / "request.json").write_text("{}\n", encoding="utf-8")

        application = DashboardApp(CompletedRunWorkspace.open(cls.workspace))
        cls.server = make_server(
            "127.0.0.1", 0, application, handler_class=QuietHandler
        )
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.thread.join(timeout=2)
        cls.server.server_close()
        cls._temporary.cleanup()

    def test_desktop_keyboard_investigation_and_handoff(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 800})
        console_errors: list[str] = []
        page_errors: list[str] = []
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error" else None,
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        try:
            response = page.goto(self.base + "/", wait_until="networkidle")
            self.assertIsNotNone(response)
            self.assertEqual(200, response.status)
            self.assertEqual("no-store", response.headers["cache-control"])
            self.assertEqual("nosniff", response.headers["x-content-type-options"])
            self.assertEqual("DENY", response.headers["x-frame-options"])
            self.assertIn("default-src 'none'", response.headers["content-security-policy"])
            self.assertEqual("Chimera completed runs", page.title())
            self.assertTrue(page.get_by_role(
                "heading", name="Chimera completed runs", exact=True
            ).is_visible())
            self.assertTrue(page.get_by_role(
                "heading", name="Entries needing attention", exact=True
            ).is_visible())
            self.assertTrue(page.get_by_text("broken-entry", exact=True).is_visible())

            # Native tab order reaches the five bounded views without a pointer.
            page.locator("h1").click()
            page.keyboard.press("Tab")
            active = page.evaluate(
                "() => ({tag: document.activeElement.tagName, "
                "text: document.activeElement.textContent.trim()})"
            )
            self.assertEqual({"tag": "A", "text": "All validated (3)"}, active)
            page.keyboard.press("Tab")
            page.keyboard.press("Tab")
            active = page.evaluate(
                "() => ({tag: document.activeElement.tagName, "
                "text: document.activeElement.textContent.trim(), "
                "outline: getComputedStyle(document.activeElement).outlineStyle, "
                "width: getComputedStyle(document.activeElement).outlineWidth})"
            )
            self.assertEqual("A", active["tag"])
            self.assertEqual("FAIL (2)", active["text"])
            self.assertEqual("solid", active["outline"])
            self.assertGreaterEqual(float(active["width"].removesuffix("px")), 3.0)
            page.keyboard.press("Enter")
            page.wait_for_url(self.base + "/?view=fail")
            self.assertEqual(
                "FAIL (2)",
                page.locator('a[aria-current="page"]').inner_text(),
            )
            self.assertTrue(page.get_by_text("Current view: FAIL", exact=True).is_visible())

            run_link = page.get_by_role(
                "link", name=self.synthetic_failure.run_id, exact=True
            )
            run_link.focus()
            page.keyboard.press("Enter")
            page.wait_for_url(
                self.base + f"/runs/{self.synthetic_failure.run_id}?view=fail"
            )
            self.assertTrue(page.get_by_text("Status: FAIL", exact=True).is_visible())
            self.assertTrue(page.get_by_role(
                "heading", name="COM-LINK-001 evidence", exact=True
            ).is_visible())
            self.assertTrue(page.get_by_role("cell", name="2.0", exact=True).is_visible())
            self.assertTrue(page.get_by_text("yes", exact=True).is_visible())

            breadcrumb = page.get_by_role("link", name="FAIL runs", exact=True)
            breadcrumb.focus()
            with page.expect_navigation(wait_until="networkidle"):
                page.keyboard.press("Enter")
            self.assertEqual(self.base + "/?view=fail", page.url)

            page.goto(
                self.base + f"/runs/{self.synthetic_failure.run_id}?view=fail",
                wait_until="networkidle",
            )
            download_link = page.get_by_role(
                "link", name="Download audit handoff ZIP", exact=True
            )
            download_link.focus()
            with page.expect_download() as download_info:
                page.keyboard.press("Enter")
            download = download_info.value
            self.assertEqual(
                f"chimera-{self.synthetic_failure.run_id}-handoff.zip",
                download.suggested_filename,
            )
            download_path = download.path()
            self.assertIsNotNone(download_path)
            manifest = inspect_handoff_bundle(Path(download_path))
            self.assertEqual(self.synthetic_failure.run_id, manifest["run_id"])
            self.assertEqual("COM-LINK-001", manifest["requirement_id"])
            self.assertEqual("fail", manifest["verdict"])
            self.assertEqual([], console_errors)
            self.assertEqual([], page_errors)
        finally:
            page.close()

    def test_mobile_width_list_and_detail_do_not_overflow(self):
        page = self.browser.new_page(viewport={"width": 390, "height": 844})
        try:
            paths = (
                "/",
                "/?view=fail",
                f"/runs/{self.natural_failure.run_id}?view=fail",
            )
            for path in paths:
                response = page.goto(self.base + path, wait_until="networkidle")
                self.assertIsNotNone(response)
                self.assertEqual(200, response.status)
                dimensions = page.evaluate(
                    "() => ({innerWidth: window.innerWidth, "
                    "scrollWidth: document.documentElement.scrollWidth, "
                    "bodyFont: parseFloat(getComputedStyle(document.body).fontSize)})"
                )
                self.assertEqual(390, dimensions["innerWidth"])
                self.assertLessEqual(
                    dimensions["scrollWidth"], dimensions["innerWidth"], path
                )
                self.assertGreaterEqual(dimensions["bodyFont"], 16.0)
            self.assertTrue(page.get_by_role(
                "link", name="FAIL runs", exact=True
            ).is_visible())
            self.assertTrue(page.get_by_role(
                "table", name="Below-threshold samples", exact=True
            ).is_visible())
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()
