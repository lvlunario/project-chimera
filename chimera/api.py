"""Read-only local API for completed communications verification runs."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Iterable, Mapping
from uuid import UUID
from wsgiref.simple_server import make_server

from .bindings import BindingError, RequirementBindings
from .evidence import EvidenceError, RunEvidence
from .journal import JournalPlan, JournalTask
from .reports import MAX_REPORT_BYTES, ReportError, VerificationReport
from .telemetry import TelemetryError, _decimal


MAX_REQUEST_BYTES = 65_536
MAX_BINDINGS_BYTES = 65_536
MAX_EVIDENCE_BYTES = 4_194_304
MAX_HTML_BYTES = 8_388_608
_COMPLETED_RUN_TOKEN = object()


class OperatorAPIError(ValueError):
    """A completed run cannot be exposed without weakening its integrity."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise OperatorAPIError(f"Duplicate request field: {key}")
        result[key] = value
    return result


def _read_regular(directory: Path, name: str, limit: int) -> bytes:
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise OperatorAPIError(f"{name} must be a regular file")
    try:
        with path.open("rb") as stream:
            content = stream.read(limit + 1)
    except OSError as exc:
        raise OperatorAPIError(f"{name} is unavailable") from exc
    if len(content) > limit:
        raise OperatorAPIError(f"{name} exceeds {limit} bytes")
    return content


def _utf8(content: bytes, name: str) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OperatorAPIError(f"{name} must be UTF-8") from exc


def _digest(value: object, label: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise OperatorAPIError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _request(text: str) -> dict:
    try:
        document = json.loads(text, object_pairs_hook=_unique_object)
    except OperatorAPIError:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise OperatorAPIError(f"Invalid request.json: {exc}") from exc
    expected = {
        "schema_version", "workflow", "source_sha256", "source_bytes",
        "threshold_db", "fault_plan_sha256", "journal_plan_sha256", "run_id",
    }
    if type(document) is not dict or set(document) != expected:
        raise OperatorAPIError("Invalid request.json fields")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise OperatorAPIError("Unsupported request schema_version")
    if document["workflow"] != "communications-link-verification":
        raise OperatorAPIError("Unsupported request workflow")
    _digest(document["source_sha256"], "source_sha256")
    _digest(document["journal_plan_sha256"], "journal_plan_sha256")
    fault_digest = document["fault_plan_sha256"]
    if fault_digest is not None:
        _digest(fault_digest, "fault_plan_sha256")
    if (type(document["source_bytes"]) is not int
            or not 1 <= document["source_bytes"] <= 1_048_576):
        raise OperatorAPIError("source_bytes is outside the supported range")
    threshold = document["threshold_db"]
    if (type(threshold) is not str or not threshold or threshold != threshold.strip()
            or len(threshold) > 128 or not threshold.isascii()):
        raise OperatorAPIError("threshold_db must be unpadded ASCII decimal text")
    try:
        _decimal(threshold, "threshold_db")
    except TelemetryError as exc:
        raise OperatorAPIError(str(exc)) from exc
    try:
        UUID(document["run_id"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise OperatorAPIError("run_id must be a UUID string") from exc
    return document


def _journal_plan(request: dict) -> JournalPlan:
    """Rebuild the operator plan identity without accepting or running callbacks."""
    source = request["source_sha256"]
    threshold = request["threshold_db"]
    fault = request["fault_plan_sha256"]
    if fault is None:
        first_id = "input"
        identity = f"source={source};threshold={threshold}"
        first_operation = "chimera.link.input:v1;" + identity
    else:
        first_id = "fault"
        identity = f"source={source};fault={fault};threshold={threshold}"
        first_operation = "chimera.link.fault:v1;" + identity
    inert = lambda: None
    return JournalPlan.from_tasks((
        JournalTask(first_id, inert, first_operation),
        JournalTask("check", inert, "chimera.link.check:v1;" + identity,
                    (first_id,)),
        JournalTask("detail", inert, "chimera.link.detail:v1;" + identity,
                    ("check",)),
    ))


def _canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True, init=False)
class CompletedLinkRun:
    """Cross-validated, callback-free view of a completed link run."""

    request: Mapping[str, object]
    evidence: RunEvidence
    bindings: RequirementBindings
    report: VerificationReport

    def __init__(self, request: dict, evidence: RunEvidence,
                 bindings: RequirementBindings, report: VerificationReport, *,
                 _token: object = None):
        if _token is not _COMPLETED_RUN_TOKEN:
            raise TypeError("CompletedLinkRun must be created with CompletedLinkRun.open")
        object.__setattr__(self, "request", MappingProxyType(dict(request)))
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "report", report)

    @classmethod
    def open(cls, directory: str | Path) -> "CompletedLinkRun":
        root = Path(directory)
        if root.is_symlink() or not root.is_dir():
            raise OperatorAPIError("Completed run directory is unavailable")
        try:
            request = _request(_utf8(
                _read_regular(root, "request.json", MAX_REQUEST_BYTES), "request.json"
            ))
            evidence = RunEvidence.from_json(_utf8(
                _read_regular(root, "evidence.json", MAX_EVIDENCE_BYTES), "evidence.json"
            ))
            bindings = RequirementBindings.from_json(_utf8(
                _read_regular(root, "bindings.json", MAX_BINDINGS_BYTES), "bindings.json"
            ))
            saved_report = VerificationReport.from_json(_utf8(
                _read_regular(root, "report.json", MAX_REPORT_BYTES), "report.json"
            ))
        except (BindingError, EvidenceError, ReportError) as exc:
            raise OperatorAPIError(f"Invalid completed-run artifact: {exc}") from exc

        expected_plan = _journal_plan(request)
        if expected_plan.sha256 != request["journal_plan_sha256"]:
            raise OperatorAPIError(
                "Saved request threshold conflicts with journal plan, or another "
                "plan identity changed"
            )

        evidence_document = evidence.to_dict()
        if evidence_document["run_id"] != request["run_id"]:
            raise OperatorAPIError("Request run_id conflicts with evidence")
        expected_graph = [
            (task.task_id, list(task.dependencies)) for task in expected_plan.tasks
        ]
        actual_graph = [
            (task["task_id"], task["dependencies"])
            for task in evidence_document["tasks"]
        ]
        if actual_graph != expected_graph:
            raise OperatorAPIError("Completed evidence task graph conflicts with request")
        if bindings.to_mapping() != {"COM-LINK-001": "check"}:
            raise OperatorAPIError("Completed bindings conflict with operator workflow")
        tasks = {item["task_id"]: item for item in evidence_document["tasks"]}
        synthetic = request["fault_plan_sha256"] is not None
        input_task_id = "fault" if synthetic else "input"
        input_task = tasks.get(input_task_id)
        if input_task is None or input_task["status"] != "succeeded":
            raise OperatorAPIError("Completed input provenance is unavailable")
        manifest = input_task["value"]
        try:
            if synthetic:
                if (type(manifest) is not dict
                        or manifest["source"]["input_sha256"] != request["source_sha256"]
                        or manifest["source"]["input_bytes"] != request["source_bytes"]
                        or manifest["fault_plan_sha256"] != request["fault_plan_sha256"]):
                    raise OperatorAPIError("Saved request conflicts with fault provenance")
            elif (type(manifest) is not dict
                    or manifest["input_sha256"] != request["source_sha256"]
                    or manifest["input_bytes"] != request["source_bytes"]):
                raise OperatorAPIError("Saved request conflicts with input provenance")
        except (KeyError, TypeError) as exc:
            raise OperatorAPIError("Input provenance is malformed") from exc

        try:
            recomputed = VerificationReport.from_evidence(
                evidence, bindings, detail_task_id="detail",
                provenance_task_id="fault" if synthetic else None,
            )
        except ReportError as exc:
            raise OperatorAPIError(f"Cannot reproduce report: {exc}") from exc
        if recomputed != saved_report:
            raise OperatorAPIError("Saved report conflicts with reopened evidence")
        report_document = saved_report.to_dict()
        if report_document["run_id"] != request["run_id"]:
            raise OperatorAPIError("Saved report run_id conflicts with request")
        detail = report_document["detail"]
        if detail["status"] != "available":
            raise OperatorAPIError("Saved request threshold conflicts with report")
        try:
            threshold_matches = (
                _decimal(detail["link_margin"]["threshold_db"], "threshold_db")
                == _decimal(request["threshold_db"], "threshold_db")
            )
        except TelemetryError as exc:  # Both artifacts were validated above.
            raise OperatorAPIError(f"Invalid completed-run threshold: {exc}") from exc
        if not threshold_matches:
            raise OperatorAPIError("Saved request threshold conflicts with report")
        if not synthetic and (
                detail["link_margin"]["input_sha256"] != request["source_sha256"]
                or detail["link_margin"]["input_bytes"] != request["source_bytes"]):
            raise OperatorAPIError("Report input identity conflicts with saved source")

        saved_html = _read_regular(root, "report.html", MAX_HTML_BYTES)
        expected_html = recomputed.to_html().encode("utf-8")
        if saved_html != expected_html:
            raise OperatorAPIError("Saved HTML conflicts with canonical report")
        return cls(
            request, evidence, bindings, recomputed,
            _token=_COMPLETED_RUN_TOKEN,
        )

    def summary(self) -> dict:
        report = self.report.to_dict()
        return {
            "schema_version": 1,
            "resource_type": "completed-communications-link-run",
            "run_id": report["run_id"],
            "workflow": self.request["workflow"],
            "verdict": report["requirement"]["verdict"],
            "synthetic": report["provenance"] is not None,
            "started_at": report["started_at"],
            "finished_at": report["finished_at"],
            "source_sha256": self.request["source_sha256"],
            "evidence_sha256": report["evidence_sha256"],
            "bindings_sha256": report["bindings_sha256"],
            "report_sha256": self.report.sha256,
            "links": {"report_json": "/api/v1/report", "report_html": "/report"},
        }


StartResponse = Callable[[str, list[tuple[str, str]]], object]


class CompletedRunApp:
    """Minimal WSGI application with no mutation or cross-origin interface."""

    def __init__(self, completed_run: CompletedLinkRun):
        if not isinstance(completed_run, CompletedLinkRun):
            raise TypeError("completed_run must be a CompletedLinkRun")
        self._run = completed_run

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

    def __call__(self, environ: dict, start_response: StartResponse) -> list[bytes]:
        if environ.get("REQUEST_METHOD") != "GET":
            body = b'{"error":"method not allowed"}\n'
            return self._response(
                start_response, "405 Method Not Allowed", "application/json; charset=utf-8",
                body, (("Allow", "GET"),),
            )
        path = environ.get("PATH_INFO", "")
        if path == "/api/v1/run":
            body = (_canonical(self._run.summary()) + "\n").encode("utf-8")
            return self._response(
                start_response, "200 OK", "application/json; charset=utf-8", body
            )
        if path == "/api/v1/report":
            body = (self._run.report.to_json() + "\n").encode("utf-8")
            return self._response(
                start_response, "200 OK", "application/json; charset=utf-8", body
            )
        if path == "/report":
            body = self._run.report.to_html().encode("utf-8")
            return self._response(
                start_response, "200 OK", "text/html; charset=utf-8", body,
                (("Content-Security-Policy",
                  "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"),),
            )
        body = b'{"error":"not found"}\n'
        return self._response(
            start_response, "404 Not Found", "application/json; charset=utf-8", body
        )


def serve_completed_run(directory: str | Path, port: int = 8765) -> None:
    """Serve one validated completed run on IPv4 loopback until interrupted."""
    if type(port) is not int or not 1 <= port <= 65_535:
        raise OperatorAPIError("port must be an integer from 1 through 65535")
    application = CompletedRunApp(CompletedLinkRun.open(directory))
    try:
        with make_server("127.0.0.1", port, application) as server:
            print(f"Chimera completed run: http://127.0.0.1:{port}/report")
            server.serve_forever()
    except OSError as exc:
        raise OperatorAPIError("Cannot bind the loopback operator API") from exc
