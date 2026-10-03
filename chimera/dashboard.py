"""Accessible read-only dashboard for a workspace of completed link runs."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from itertools import islice
import json
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import unquote
from wsgiref.simple_server import make_server

from .api import CompletedLinkRun, OperatorAPIError
from .handoff import handoff_bundle_bytes


MAX_WORKSPACE_ENTRIES = 1_000
MAX_QUERY_LENGTH = 64
_INDEX_VIEWS = ("all", "pass", "fail", "synthetic", "invalid")
_WORKSPACE_TOKEN = object()


class DashboardError(ValueError):
    """A completed-run workspace cannot be presented safely."""


def _canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def _display_name(name: str) -> str:
    """Make operating-system surrogate filenames safe for UTF-8 JSON and HTML."""
    return name.encode("utf-8", "backslashreplace").decode("utf-8")


@dataclass(frozen=True)
class InvalidRunEntry:
    """Visible discovery result for an entry that cannot be trusted as a run."""

    name: str
    reason: str

    def to_dict(self) -> dict:
        return {"name": self.name, "status": "invalid", "reason": self.reason}


class CompletedRunWorkspace:
    """Immutable startup snapshot of validated and rejected workspace entries."""

    def __init__(self, runs: dict[str, CompletedLinkRun],
                 invalid: tuple[InvalidRunEntry, ...], *, _token: object = None):
        if _token is not _WORKSPACE_TOKEN:
            raise TypeError(
                "CompletedRunWorkspace must be created with CompletedRunWorkspace.open"
            )
        self._runs = dict(runs)
        self._invalid = invalid

    @classmethod
    def open(cls, directory: str | Path) -> "CompletedRunWorkspace":
        root = Path(directory)
        if root.is_symlink() or not root.is_dir():
            raise DashboardError("Completed-run workspace is unavailable")
        try:
            entries = list(islice(root.iterdir(), MAX_WORKSPACE_ENTRIES + 1))
        except OSError as exc:
            raise DashboardError("Cannot inspect completed-run workspace") from exc
        if len(entries) > MAX_WORKSPACE_ENTRIES:
            raise DashboardError(
                f"Completed-run workspace exceeds {MAX_WORKSPACE_ENTRIES} entries"
            )
        entries.sort(key=lambda item: item.name)

        candidates: list[tuple[str, CompletedLinkRun]] = []
        invalid: list[InvalidRunEntry] = []
        for entry in entries:
            if entry.is_symlink() or not entry.is_dir():
                invalid.append(InvalidRunEntry(
                    _display_name(entry.name), "entry is not a regular run directory"
                ))
                continue
            try:
                completed = CompletedLinkRun.open(entry)
            except (OperatorAPIError, OSError) as exc:
                invalid.append(InvalidRunEntry(_display_name(entry.name), str(exc)))
                continue
            candidates.append((entry.name, completed))

        names_by_id: dict[str, list[str]] = {}
        for name, completed in candidates:
            names_by_id.setdefault(str(completed.request["run_id"]), []).append(name)
        duplicate_ids = {
            run_id for run_id, names in names_by_id.items() if len(names) != 1
        }
        runs: dict[str, CompletedLinkRun] = {}
        for name, completed in candidates:
            run_id = str(completed.request["run_id"])
            if run_id in duplicate_ids:
                invalid.append(InvalidRunEntry(
                    _display_name(name),
                    "duplicate run_id is ambiguous in this workspace"
                ))
            else:
                runs[run_id] = completed
        invalid.sort(key=lambda item: item.name)
        return cls(runs, tuple(invalid), _token=_WORKSPACE_TOKEN)

    def get(self, run_id: str) -> CompletedLinkRun | None:
        return self._runs.get(run_id)

    def document(self) -> dict:
        runs = []
        for run_id, completed in sorted(
                self._runs.items(),
                key=lambda item: (str(item[1].summary()["started_at"]), item[0]),
                reverse=True):
            summary = completed.summary()
            summary["links"] = {
                "detail_html": f"/runs/{run_id}",
                "report_json": f"/api/v1/runs/{run_id}/report",
                "report_html": f"/runs/{run_id}/report",
                "evidence_json": f"/api/v1/runs/{run_id}/evidence",
                "bindings_json": f"/api/v1/runs/{run_id}/bindings",
                "handoff_zip": f"/api/v1/runs/{run_id}/handoff",
            }
            runs.append(summary)
        return {
            "schema_version": 1,
            "resource_type": "completed-communications-link-workspace",
            "run_count": len(runs),
            "invalid_count": len(self._invalid),
            "runs": runs,
            "invalid_entries": [item.to_dict() for item in self._invalid],
        }


StartResponse = Callable[[str, list[tuple[str, str]]], object]


class DashboardApp:
    """Dependency-free, read-only WSGI dashboard with semantic HTML views."""

    def __init__(self, workspace: CompletedRunWorkspace):
        if not isinstance(workspace, CompletedRunWorkspace):
            raise TypeError("workspace must be a CompletedRunWorkspace")
        self._workspace = workspace

    @staticmethod
    def _response(start_response: StartResponse, status: str, content_type: str,
                  body: bytes, extra: Iterable[tuple[str, str]] = ()) -> list[bytes]:
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("X-Frame-Options", "DENY"),
        ]
        headers.extend(extra)
        start_response(status, headers)
        return [body]

    @staticmethod
    def _page(title: str, content: str) -> bytes:
        return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
                "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                f"<title>{escape(title)}</title><style>"
                "body{font-family:system-ui,sans-serif;line-height:1.5;max-width:72rem;"
                "margin:auto;padding:1rem;color:#172033;background:#fff}"
                "a{color:#0645ad}a:focus{outline:3px solid #ffbf47;outline-offset:2px}"
                "table{border-collapse:collapse;width:100%}th,td{border:1px solid #8b95a5;"
                "padding:.5rem;text-align:left;vertical-align:top}th{background:#eef2f7}"
                ".pass{color:#176b2c;font-weight:700}.fail,.invalid{color:#a52222;"
                "font-weight:700}code{overflow-wrap:anywhere}</style></head><body>"
                f"<main>{content}</main></body></html>").encode("utf-8")

    @staticmethod
    def _index_view(query: object) -> str | None:
        """Accept only one explicit bounded presentation filter."""
        if type(query) is not str or len(query) > MAX_QUERY_LENGTH:
            return None
        if query == "":
            return "all"
        if not query.startswith("view=") or "&" in query or ";" in query:
            return None
        view = query[5:]
        return view if view in _INDEX_VIEWS else None

    @staticmethod
    def _run_in_view(run: dict, view: str) -> bool:
        """Return whether a validated summary truthfully belongs to a view."""
        if view == "all":
            return True
        if view in ("pass", "fail"):
            return run["verdict"] == view
        if view == "synthetic":
            return bool(run["synthetic"])
        return False

    def _index_html(self, view: str = "all") -> bytes:
        document = self._workspace.document()
        all_runs = document["runs"]
        runs = [run for run in all_runs if self._run_in_view(run, view)]
        rows = []
        for run in runs:
            run_id = escape(run["run_id"])
            verdict = escape(run["verdict"])
            detail_query = "" if view == "all" else f"?view={view}"
            rows.append(
                "<tr>"
                f"<td><a href=\"/runs/{run_id}{detail_query}\"><code>{run_id}</code></a></td>"
                f"<td><span class=\"{verdict}\">{verdict.upper()}</span></td>"
                f"<td>{'yes' if run['synthetic'] else 'no'}</td>"
                f"<td>{escape(run['started_at'])}</td>"
                "</tr>"
            )
        if not rows:
            rows.append("<tr><td colspan=\"4\">No runs match this view.</td></tr>")
        invalid_rows = []
        for item in document["invalid_entries"]:
            invalid_rows.append(
                f"<li><strong>{escape(item['name'])}</strong>: "
                f"<span class=\"invalid\">invalid</span> — {escape(item['reason'])}</li>"
            )
        if view in ("all", "invalid"):
            invalid_section = (
                "<h2>Entries needing attention</h2><ul>" + "".join(invalid_rows) + "</ul>"
                if invalid_rows else
                "<h2>Entries needing attention</h2><p>None.</p>"
            )
        else:
            invalid_section = ""
        counts = {
            "all": len(all_runs),
            "pass": sum(run["verdict"] == "pass" for run in all_runs),
            "fail": sum(run["verdict"] == "fail" for run in all_runs),
            "synthetic": sum(bool(run["synthetic"]) for run in all_runs),
            "invalid": document["invalid_count"],
        }
        labels = {
            "all": "All validated", "pass": "PASS", "fail": "FAIL",
            "synthetic": "Synthetic", "invalid": "Needs attention",
        }
        links = []
        for name in _INDEX_VIEWS:
            href = "/" if name == "all" else f"/?view={name}"
            current = ' aria-current="page"' if name == view else ""
            links.append(
                f'<a href="{href}"{current}>{labels[name]} ({counts[name]})</a>'
            )
        view_label = labels[view]
        content = (
            "<h1>Chimera completed runs</h1>"
            "<p>This read-only view displays only cross-validated completed evidence. "
            "Invalid entries remain visible for investigation.</p>"
            "<nav aria-label=\"Run views\">" + " · ".join(links) + "</nav>"
            f"<p>Current view: <strong>{view_label}</strong></p>"
            f"<table><caption>Validated communications-link runs — {view_label}</caption>"
            "<thead><tr><th scope=\"col\">Run</th><th scope=\"col\">Verdict</th>"
            "<th scope=\"col\">Synthetic</th><th scope=\"col\">Started (UTC)</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>" +
            invalid_section
        )
        return self._page("Chimera completed runs", content)

    def _detail_html(self, completed: CompletedLinkRun, view: str = "all") -> bytes:
        summary = completed.summary()
        report = completed.report.to_dict()
        link = report["detail"]["link_margin"]
        run_id = escape(str(summary["run_id"]))
        verdict = escape(str(summary["verdict"]))
        findings = []
        for sample in link["failing_samples"]:
            findings.append(
                "<tr>"
                f"<td>{sample['sample_index']}</td>"
                f"<td>{escape(str(sample['timestamp_utc']))}</td>"
                f"<td>{escape(str(sample['link_margin_db']))}</td>"
                "</tr>"
            )
        findings_body = (
            "".join(findings) if findings
            else "<tr><td colspan=\"3\">No below-threshold samples.</td></tr>"
        )
        labels = {
            "all": "All completed runs", "pass": "PASS runs", "fail": "FAIL runs",
            "synthetic": "Synthetic runs", "invalid": "Entries needing attention",
        }
        return_href = "/" if view == "all" else f"/?view={view}"
        content = (
            f"<nav aria-label=\"Breadcrumb\"><a href=\"{return_href}\">"
            f"{labels[view]}</a></nav>"
            f"<h1>Run <code>{run_id}</code></h1>"
            f"<p>Status: <strong class=\"{verdict}\">{verdict.upper()}</strong></p>"
            "<dl>"
            f"<dt>Workflow</dt><dd>{escape(str(summary['workflow']))}</dd>"
            f"<dt>Synthetic input</dt><dd>{'yes' if summary['synthetic'] else 'no'}</dd>"
            f"<dt>Started (UTC)</dt><dd>{escape(str(summary['started_at']))}</dd>"
            f"<dt>Finished (UTC)</dt><dd>{escape(str(summary['finished_at']))}</dd>"
            f"<dt>Report SHA-256</dt><dd><code>{escape(str(summary['report_sha256']))}</code></dd>"
            "</dl>"
            "<h2>COM-LINK-001 evidence</h2><dl>"
            f"<dt>Threshold</dt><dd>{escape(str(link['threshold_db']))} dB</dd>"
            f"<dt>Minimum</dt><dd>{escape(str(link['minimum_link_margin_db']))} dB</dd>"
            f"<dt>Failing samples</dt><dd>{link['failure_count']}</dd>"
            "</dl><table><caption>Below-threshold samples</caption>"
            "<thead><tr><th scope=\"col\">Sample</th><th scope=\"col\">Time (UTC)</th>"
            "<th scope=\"col\">Link margin (dB)</th></tr></thead><tbody>"
            f"{findings_body}</tbody></table>"
            f"<p><a href=\"/runs/{run_id}/report\">Open readable report</a> · "
            f"<a href=\"/api/v1/runs/{run_id}/report\">Open canonical report JSON</a> · "
            f"<a href=\"/api/v1/runs/{run_id}/evidence\">Open portable evidence JSON</a> · "
            f"<a href=\"/api/v1/runs/{run_id}/bindings\">Open requirement bindings JSON</a> · "
            f"<a href=\"/api/v1/runs/{run_id}/handoff\">Download audit handoff ZIP</a>"
            "</p>"
        )
        return self._page(f"Chimera run {run_id}", content)

    def __call__(self, environ: dict, start_response: StartResponse) -> list[bytes]:
        if environ.get("REQUEST_METHOD") != "GET":
            return self._response(
                start_response, "405 Method Not Allowed",
                "application/json; charset=utf-8", b'{"error":"method not allowed"}\n',
                (("Allow", "GET"),),
            )
        path = environ.get("PATH_INFO", "")
        if path == "/":
            view = self._index_view(environ.get("QUERY_STRING", ""))
            if view is None:
                return self._response(
                    start_response, "400 Bad Request", "application/json; charset=utf-8",
                    b'{"error":"invalid dashboard view"}\n',
                )
            return self._response(
                start_response, "200 OK", "text/html; charset=utf-8",
                self._index_html(view), (("Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"),),
            )
        if path == "/api/v1/runs":
            body = (_canonical(self._workspace.document()) + "\n").encode("utf-8")
            return self._response(
                start_response, "200 OK", "application/json; charset=utf-8", body
            )
        parts = path.split("/")
        if len(parts) in (3, 4, 6) and parts[1] in ("runs", "api"):
            if parts[1] == "runs":
                run_id = unquote(parts[2])
                suffix = parts[3:] if len(parts) == 4 else []
            elif len(parts) == 6 and parts[2:4] == ["v1", "runs"]:
                run_id = unquote(parts[4])
                suffix = parts[5:]
            else:
                run_id, suffix = "", ["invalid"]
            completed = self._workspace.get(run_id)
            if completed is not None and not suffix:
                if parts[1] == "runs":
                    view = self._index_view(environ.get("QUERY_STRING", ""))
                    if view is None:
                        return self._response(
                            start_response, "400 Bad Request",
                            "application/json; charset=utf-8",
                            b'{"error":"invalid dashboard view"}\n',
                        )
                    if not self._run_in_view(completed.summary(), view):
                        return self._response(
                            start_response, "400 Bad Request",
                            "application/json; charset=utf-8",
                            b'{"error":"run not in dashboard view"}\n',
                        )
                    return self._response(
                        start_response, "200 OK", "text/html; charset=utf-8",
                        self._detail_html(completed, view), (("Content-Security-Policy",
                            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"),),
                    )
            if completed is not None and suffix == ["report"]:
                if parts[1] == "runs":
                    return self._response(
                        start_response, "200 OK", "text/html; charset=utf-8",
                        completed.report.to_html().encode("utf-8"),
                        (("Content-Security-Policy",
                          "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"),),
                    )
                body = (completed.report.to_json() + "\n").encode("utf-8")
                return self._response(
                    start_response, "200 OK", "application/json; charset=utf-8", body
                )
            if completed is not None and parts[1] == "api" and suffix == ["evidence"]:
                body = (completed.evidence.to_json() + "\n").encode("utf-8")
                return self._response(
                    start_response, "200 OK", "application/json; charset=utf-8", body
                )
            if completed is not None and parts[1] == "api" and suffix == ["bindings"]:
                body = (completed.bindings.to_json() + "\n").encode("utf-8")
                return self._response(
                    start_response, "200 OK", "application/json; charset=utf-8", body
                )
            if completed is not None and parts[1] == "api" and suffix == ["handoff"]:
                body = handoff_bundle_bytes(completed)
                return self._response(
                    start_response, "200 OK", "application/zip", body,
                    (("Content-Disposition",
                      f'attachment; filename="chimera-{run_id}-handoff.zip"'),),
                )
        return self._response(
            start_response, "404 Not Found", "application/json; charset=utf-8",
            b'{"error":"not found"}\n',
        )


def serve_dashboard(directory: str | Path, port: int = 8765) -> None:
    """Serve a validated workspace snapshot on IPv4 loopback until interrupted."""
    if type(port) is not int or not 1 <= port <= 65_535:
        raise DashboardError("port must be an integer from 1 through 65535")
    application = DashboardApp(CompletedRunWorkspace.open(directory))
    try:
        with make_server("127.0.0.1", port, application) as server:
            print(f"Chimera completed runs: http://127.0.0.1:{port}/")
            server.serve_forever()
    except OSError as exc:
        raise DashboardError("Cannot bind the loopback dashboard") from exc
