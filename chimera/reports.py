"""Canonical communications verification reports and deterministic HTML views."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from uuid import UUID

from .bindings import RequirementBindings
from .evidence import RunEvidence
from .telemetry import LinkMarginReport, TelemetryError, _decimal
from .verdicts import assess_requirements


MAX_REPORT_BYTES = 4_194_304


class ReportError(ValueError):
    """A report is incomplete, inconsistent, malformed, or unsupported."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReportError(f"Duplicate report field: {key}")
        result[key] = value
    return result


def _fields(value: object, expected: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise ReportError(f"Invalid {label} fields")
    return value


def _digest(value: object, label: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ReportError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ReportError(f"{label} must be nonempty text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ReportError(f"{label} must be valid UTF-8 text") from exc
    if any((ord(character) < 32 and character not in "\t\n\r")
           or 127 <= ord(character) <= 159 for character in value):
        raise ReportError(f"{label} contains unsupported control characters")
    return value


def _timestamp(value: object, label: str) -> str:
    if type(value) is not str:
        raise ReportError(f"{label} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReportError(f"{label} must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ReportError(f"{label} must be a UTC timestamp")
    return value


def _canonical(document: dict) -> str:
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def _provenance_summary(value: object) -> tuple[dict, dict]:
    document = _fields(value, {
        "schema_version", "synthetic", "procedure", "source", "fault_plan",
        "fault_plan_sha256", "derived",
    }, "fault provenance")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ReportError("Unsupported fault provenance schema_version")
    if document["synthetic"] is not True:
        raise ReportError("Fault provenance must be explicitly synthetic")
    if document["procedure"] != "chimera.synthetic.sample-replacement-v1":
        raise ReportError("Unsupported fault provenance procedure")
    source = _fields(document["source"], {
        "schema_version", "media_type", "input_sha256", "input_bytes", "sample_count",
        "timestamp_start_utc", "timestamp_end_utc", "link_margin_unit",
        "minimum_link_margin_db",
    }, "source manifest")
    derived = _fields(document["derived"], set(source), "derived manifest")
    for label, manifest in (("source", source), ("derived", derived)):
        if (type(manifest["schema_version"]) is not int
                or manifest["schema_version"] != 1
                or manifest["media_type"] != "text/csv"
                or manifest["link_margin_unit"] != "dB"
                or type(manifest["input_bytes"]) is not int
                or not 0 <= manifest["input_bytes"] <= 1_048_576
                or type(manifest["sample_count"]) is not int
                or not 1 <= manifest["sample_count"] <= 10_000
                or type(manifest["minimum_link_margin_db"]) is not str):
            raise ReportError(f"Invalid {label} manifest values")
        start = _timestamp(manifest["timestamp_start_utc"], f"{label} timestamp_start_utc")
        end = _timestamp(manifest["timestamp_end_utc"], f"{label} timestamp_end_utc")
        if datetime.fromisoformat(end) < datetime.fromisoformat(start):
            raise ReportError(f"{label} manifest time range is reversed")
        try:
            _decimal(manifest["minimum_link_margin_db"],
                     f"{label} minimum_link_margin_db")
        except TelemetryError as exc:
            raise ReportError(f"Invalid {label} manifest minimum: {exc}") from exc
    if (source["sample_count"] != derived["sample_count"]
            or source["timestamp_start_utc"] != derived["timestamp_start_utc"]
            or source["timestamp_end_utc"] != derived["timestamp_end_utc"]):
        raise ReportError("Replacement provenance changed sample count or time range")
    # Reopen the plan through its public contract to verify content identity.
    from .faults import FaultPlan
    plan_document = _fields(document["fault_plan"], {
        "schema_version", "model", "replacements",
    }, "fault plan")
    try:
        plan = FaultPlan(_canonical(plan_document))
    except (ReportError, ValueError, TypeError) as exc:
        raise ReportError(f"Invalid fault plan provenance: {exc}") from exc
    if _digest(document["fault_plan_sha256"], "fault_plan_sha256") != plan.sha256:
        raise ReportError("Fault plan digest conflicts with plan content")
    replacements = plan.to_dict()["replacements"]
    if replacements and replacements[-1]["sample_index"] > source["sample_count"]:
        raise ReportError("Fault plan replacement exceeds source sample count")
    summary = {
        "synthetic": True,
        "procedure": document["procedure"],
        "source_sha256": _digest(source["input_sha256"], "source input_sha256"),
        "fault_plan_sha256": plan.sha256,
        "derived_sha256": _digest(derived["input_sha256"], "derived input_sha256"),
    }
    return summary, derived


@dataclass(frozen=True)
class VerificationReport:
    """Immutable canonical report; HTML is a presentation of this JSON contract."""

    _json: str

    def __post_init__(self) -> None:
        if type(self._json) is not str:
            raise ReportError("Verification report input must be JSON text")
        try:
            encoded = self._json.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ReportError("Verification report must be valid UTF-8 text") from exc
        if len(encoded) > MAX_REPORT_BYTES:
            raise ReportError(f"Verification report exceeds {MAX_REPORT_BYTES} bytes")
        try:
            document = json.loads(self._json, object_pairs_hook=_unique_object)
        except ReportError:
            raise
        except (ValueError, TypeError, RecursionError) as exc:
            raise ReportError(f"Invalid verification report JSON: {exc}") from exc
        document = _fields(document, {
            "schema_version", "report_type", "run_id", "started_at", "finished_at",
            "evidence_sha256", "bindings_sha256", "requirement", "detail",
            "provenance",
        }, "verification report")
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise ReportError("Unsupported verification report schema_version")
        if document["report_type"] != "communications-link-verification":
            raise ReportError("Unsupported verification report type")
        try:
            if type(document["run_id"]) is not str:
                raise ValueError
            UUID(document["run_id"])
        except ValueError as exc:
            raise ReportError("run_id must be a UUID string") from exc
        started = _timestamp(document["started_at"], "started_at")
        finished = _timestamp(document["finished_at"], "finished_at")
        if datetime.fromisoformat(finished) < datetime.fromisoformat(started):
            raise ReportError("finished_at precedes started_at")
        _digest(document["evidence_sha256"], "evidence_sha256")
        _digest(document["bindings_sha256"], "bindings_sha256")

        requirement = _fields(document["requirement"], {
            "requirement_id", "task_id", "verdict", "reason",
        }, "requirement")
        if requirement["requirement_id"] != "COM-LINK-001":
            raise ReportError("Report requires COM-LINK-001")
        _text(requirement["task_id"], "Requirement task_id")
        if not requirement["task_id"].strip():
            raise ReportError("Requirement task_id must be nonempty")
        if requirement["verdict"] not in {"pass", "fail", "error", "not_evaluated"}:
            raise ReportError("Invalid requirement verdict")
        _text(requirement["reason"], "Requirement reason")
        if (requirement["verdict"] == "pass"
                and requirement["reason"] != "Check returned True"):
            raise ReportError("PASS reason conflicts with Boolean verdict")
        if (requirement["verdict"] == "fail"
                and requirement["reason"] != "Check returned False"):
            raise ReportError("FAIL reason conflicts with Boolean verdict")

        detail = _fields(document["detail"], {"status", "reason", "link_margin"}, "detail")
        if detail["status"] == "available":
            if detail["reason"] is not None or type(detail["link_margin"]) is not dict:
                raise ReportError("Available detail requires link_margin and no reason")
            try:
                link_report = LinkMarginReport(_canonical(detail["link_margin"]))
            except TelemetryError as exc:
                raise ReportError(f"Invalid link-margin detail: {exc}") from exc
            expected = "pass" if link_report.passed else "fail"
            if requirement["verdict"] != expected:
                raise ReportError("Requirement verdict conflicts with link-margin detail")
        elif detail["status"] == "unavailable":
            if detail["link_margin"] is not None:
                raise ReportError("Unavailable detail requires a nonempty reason")
            _text(detail["reason"], "Unavailable detail reason")
            if requirement["verdict"] in {"pass", "fail"}:
                raise ReportError("Pass/fail verdict requires available detail")
        else:
            raise ReportError("Invalid detail status")

        provenance = document["provenance"]
        if provenance is not None:
            provenance = _fields(provenance, {
                "synthetic", "procedure", "source_sha256", "fault_plan_sha256",
                "derived_sha256",
            }, "provenance")
            if provenance["synthetic"] is not True:
                raise ReportError("Provenance must remain explicitly synthetic")
            if provenance["procedure"] != "chimera.synthetic.sample-replacement-v1":
                raise ReportError("Unsupported provenance procedure")
            for name in ("source_sha256", "fault_plan_sha256", "derived_sha256"):
                _digest(provenance[name], name)
            if (detail["status"] == "available"
                    and provenance["derived_sha256"] != detail["link_margin"]["input_sha256"]):
                raise ReportError("Derived provenance conflicts with link-margin input")
        canonical = _canonical(document)
        try:
            canonical_bytes = canonical.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ReportError("Canonical report must be valid UTF-8 text") from exc
        if len(canonical_bytes) > MAX_REPORT_BYTES:
            raise ReportError(f"Canonical report exceeds {MAX_REPORT_BYTES} bytes")
        object.__setattr__(self, "_json", canonical)

    @classmethod
    def from_json(cls, text: str) -> "VerificationReport":
        return cls(text)

    @classmethod
    def from_evidence(
        cls, evidence: RunEvidence, bindings: RequirementBindings, *,
        detail_task_id: str, provenance_task_id: str | None = None,
    ) -> "VerificationReport":
        """Build from validated reopened evidence; no task callback is accepted."""
        if not isinstance(evidence, RunEvidence):
            raise TypeError("evidence must be validated RunEvidence")
        if not isinstance(bindings, RequirementBindings):
            raise TypeError("bindings must be validated RequirementBindings")
        if type(detail_task_id) is not str or not detail_task_id.strip():
            raise ReportError("detail_task_id must be nonempty")
        if provenance_task_id is not None and (
                type(provenance_task_id) is not str or not provenance_task_id.strip()):
            raise ReportError("provenance_task_id must be nonempty when supplied")
        assessment = assess_requirements(evidence, bindings)
        if (len(assessment.outcomes) != 1
                or assessment.outcomes[0].requirement_id != "COM-LINK-001"):
            raise ReportError("Report requires exactly one COM-LINK-001 binding")
        outcome = assessment.outcomes[0]
        evidence_document = evidence.to_dict()
        tasks = {item["task_id"]: item for item in evidence_document["tasks"]}
        detail_task = tasks.get(detail_task_id)
        if detail_task is not None and detail_task["status"] == "succeeded":
            try:
                detail_report = LinkMarginReport(_canonical(detail_task["value"])).to_dict()
            except (TelemetryError, TypeError, ValueError) as exc:
                raise ReportError(f"Invalid succeeded detail task: {exc}") from exc
            detail = {"status": "available", "reason": None, "link_margin": detail_report}
        else:
            if detail_task is None:
                reason = f"Detail task {detail_task_id} is absent from run evidence"
            else:
                reason = detail_task["error"]
            detail = {"status": "unavailable", "reason": reason, "link_margin": None}

        provenance = None
        derived_manifest = None
        if provenance_task_id is not None:
            provenance_task = tasks.get(provenance_task_id)
            if provenance_task is None or provenance_task["status"] != "succeeded":
                raise ReportError("Requested provenance task is unavailable")
            provenance, derived_manifest = _provenance_summary(provenance_task["value"])
        if detail["status"] == "available" and derived_manifest is not None:
            link = detail["link_margin"]
            if (derived_manifest["input_sha256"] != link["input_sha256"]
                    or derived_manifest["input_bytes"] != link["input_bytes"]
                    or derived_manifest["sample_count"] != link["sample_count"]
                    or derived_manifest["minimum_link_margin_db"]
                    != link["minimum_link_margin_db"]):
                raise ReportError("Derived manifest conflicts with link-margin detail")
        document = {
            "schema_version": 1,
            "report_type": "communications-link-verification",
            "run_id": evidence_document["run_id"],
            "started_at": evidence_document["started_at"],
            "finished_at": evidence_document["finished_at"],
            "evidence_sha256": sha256(evidence.to_json().encode("utf-8")).hexdigest(),
            "bindings_sha256": bindings.sha256,
            "requirement": {
                "requirement_id": outcome.requirement_id,
                "task_id": outcome.task_id,
                "verdict": outcome.verdict,
                "reason": outcome.reason,
            },
            "detail": detail,
            "provenance": provenance,
        }
        return cls(_canonical(document))

    def to_json(self) -> str:
        return self._json

    def to_dict(self) -> dict:
        return json.loads(self._json)

    @property
    def sha256(self) -> str:
        return sha256(self._json.encode("utf-8")).hexdigest()

    def to_html(self) -> str:
        """Render deterministic self-contained HTML; JSON remains authoritative."""
        document = self.to_dict()
        requirement = document["requirement"]
        detail = document["detail"]
        provenance = document["provenance"]
        status_class = "status-" + requirement["verdict"].replace("_", "-")
        if detail["status"] == "available":
            link = detail["link_margin"]
            summary = (
                f"<dl><dt>Threshold</dt><dd>{escape(link['threshold_db'])} dB</dd>"
                f"<dt>Minimum</dt><dd>{escape(link['minimum_link_margin_db'])} dB</dd>"
                f"<dt>Samples</dt><dd>{link['sample_count']}</dd>"
                f"<dt>Input SHA-256</dt><dd><code>{link['input_sha256']}</code></dd></dl>"
            )
            rows = "".join(
                "<tr>" + f"<td>{item['sample_index']}</td>"
                + f"<td>{escape(item['timestamp_utc'])}</td>"
                + f"<td>{escape(item['link_margin_db'])}</td>" + "</tr>"
                for item in link["failing_samples"]
            )
            findings = ("<p>No below-threshold samples.</p>" if not rows else
                        "<table><thead><tr><th>Sample</th><th>UTC timestamp</th>"
                        "<th>Margin (dB)</th></tr></thead><tbody>" + rows + "</tbody></table>")
        else:
            summary = "<p class=unavailable>Detail unavailable: " + escape(detail["reason"]) + "</p>"
            findings = ""
        provenance_html = "<p>No synthetic fault provenance supplied.</p>"
        if provenance is not None:
            provenance_html = (
                "<p><strong>Synthetic data:</strong> yes</p><dl>"
                f"<dt>Procedure</dt><dd>{escape(provenance['procedure'])}</dd>"
                f"<dt>Source SHA-256</dt><dd><code>{provenance['source_sha256']}</code></dd>"
                f"<dt>Fault plan SHA-256</dt><dd><code>{provenance['fault_plan_sha256']}</code></dd>"
                f"<dt>Derived SHA-256</dt><dd><code>{provenance['derived_sha256']}</code></dd></dl>"
            )
        canonical_json = escape(self._json)
        return (
            "<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
            "<meta http-equiv=Content-Security-Policy "
            "content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>Chimera verification report</title><style>"
            "body{font-family:system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;"
            "color:#172033}code{overflow-wrap:anywhere}dl{display:grid;grid-template-columns:12rem 1fr;gap:.4rem}"
            "dt{font-weight:700}dd{margin:0}table{border-collapse:collapse;width:100%}th,td{border:1px solid #aab3c2;"
            "padding:.5rem;text-align:left}.verdict{display:inline-block;padding:.3rem .7rem;border-radius:.4rem;"
            "font-weight:800}.status-pass{background:#d7f5df;color:#135c2b}.status-fail{background:#ffe0e0;color:#8a1717}"
            ".status-error,.status-not-evaluated{background:#fff0c7;color:#6d4b00}.unavailable{border-left:.3rem solid #b7791f;padding:.6rem}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f9;padding:1rem}"
            "</style></head><body><main><h1>Chimera verification report</h1>"
            f"<p>Run <code>{escape(document['run_id'])}</code></p>"
            f"<p class=\"verdict {status_class}\">{escape(requirement['verdict'].upper())}</p>"
            f"<p><strong>{escape(requirement['requirement_id'])}</strong> — {escape(requirement['reason'])}</p>"
            "<h2>Link-margin result</h2>" + summary + findings
            + "<h2>Provenance</h2>" + provenance_html
            + "<h2>Evidence identity</h2><dl>"
            f"<dt>Started</dt><dd>{escape(document['started_at'])}</dd>"
            f"<dt>Finished</dt><dd>{escape(document['finished_at'])}</dd>"
            f"<dt>Evidence SHA-256</dt><dd><code>{document['evidence_sha256']}</code></dd>"
            f"<dt>Bindings SHA-256</dt><dd><code>{document['bindings_sha256']}</code></dd>"
            f"<dt>Report SHA-256</dt><dd><code>{self.sha256}</code></dd></dl>"
            "<details><summary>Canonical report JSON</summary><pre>" + canonical_json
            + "</pre></details><p><small>Generated deterministically from validated reopened evidence. "
            "Hashes identify content; they are not digital signatures.</small></p></main></body></html>"
        )
