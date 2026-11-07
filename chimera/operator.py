"""Integrated local operator workflow for communications-link verification."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .bindings import BindingError, RequirementBindings
from .faults import (MAX_PLAN_BYTES, FaultError, FaultPlan, fault_manifest,
                     inject_link_csv)
from .journal import (JournalError, JournalPlan, JournalTask, export_journal_evidence,
                      resume_journaled, run_journaled)
from .reports import ReportError, VerificationReport
from .storage import EvidenceStore, StorageError
from .telemetry import (MAX_INPUT_BYTES, TelemetryError, _decimal,
                        evaluate_link_margin, link_margin_passes, parse_link_csv)


class OperatorError(RuntimeError):
    """An integrated operator request cannot be completed safely."""


class OperatorInputError(OperatorError):
    """Operator input is malformed, unavailable, or inconsistent."""


class OperatorOutputError(OperatorError):
    """Operator output exists with different content or cannot be written."""


@dataclass(frozen=True)
class LinkRunResult:
    run_id: str
    verdict: str
    evidence_path: Path
    report_json_path: Path
    report_html_path: Path
    report_sha256: str


def _read_bounded(path: str | Path, limit: int, label: str) -> bytes:
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(limit + 1)
    except (OSError, TypeError, ValueError) as exc:
        raise OperatorInputError(f"{label} is unavailable") from exc
    if len(data) > limit:
        raise OperatorInputError(f"{label} exceeds {limit} bytes")
    return data


def _threshold(text: str) -> Decimal:
    if type(text) is not str or not text or text != text.strip() or len(text) > 128:
        raise OperatorInputError("threshold_db must be unpadded decimal text")
    try:
        return _decimal(text, "threshold_db")
    except TelemetryError as exc:
        raise OperatorInputError(str(exc)) from exc


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _publish(path: Path, content: str) -> None:
    """Create one UTF-8 artifact, or accept an exact existing artifact on resume."""
    encoded = content.encode("utf-8")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise OperatorOutputError(f"Output is not a regular file: {path.name}")
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise OperatorOutputError(f"Cannot inspect existing output: {path.name}") from exc
        if existing != encoded:
            raise OperatorOutputError(f"Existing output conflicts: {path.name}")
        return
    try:
        with path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise OperatorOutputError(f"Cannot write output: {path.name}") from exc


def _reject_symlinks(directory: Path) -> None:
    try:
        if any(item.is_symlink() for item in directory.iterdir()):
            raise OperatorOutputError("Output directory contains a symbolic link")
    except OSError as exc:
        raise OperatorOutputError("Cannot inspect output directory") from exc


def _tasks(source: bytes, threshold_text: str,
           plan: FaultPlan | None) -> tuple[JournalTask, ...]:
    source_sha = sha256(source).hexdigest()
    threshold = _threshold(threshold_text)
    if plan is None:
        data = source
        identity = f"source={source_sha};threshold={threshold_text}"

        def input_manifest():
            return parse_link_csv(source, expected_sha256=source_sha).manifest()

        first = JournalTask("input", input_manifest,
                            "chimera.link.input:v1;" + identity)
        dependency = "input"
    else:
        data = inject_link_csv(source, plan, expected_sha256=source_sha)
        identity = (f"source={source_sha};fault={plan.sha256};"
                    f"threshold={threshold_text}")

        def input_manifest():
            return fault_manifest(source, plan, expected_sha256=source_sha)

        first = JournalTask("fault", input_manifest,
                            "chimera.link.fault:v1;" + identity)
        dependency = "fault"

    def check():
        return link_margin_passes(parse_link_csv(data), threshold)

    def detail():
        return evaluate_link_margin(parse_link_csv(data), threshold).to_dict()

    return (
        first,
        JournalTask("check", check, "chimera.link.check:v1;" + identity,
                    (dependency,)),
        JournalTask("detail", detail, "chimera.link.detail:v1;" + identity,
                    ("check",)),
    )


def _run_link_verification(
    source_path: str | Path, output_directory: str | Path, *,
    threshold_db: str, fault_plan_path: str | Path | None = None,
    resume_run_id: str | None = None,
) -> LinkRunResult:
    """Run or safely resume the bounded durable communications operator journey.

    The caller supplies the same source, threshold, and optional fault plan when
    resuming. Their identities are part of the durable plan; changed inputs fail
    before any pending callback is allowed to run.
    """
    source = _read_bounded(source_path, MAX_INPUT_BYTES, "Telemetry input")
    # Validate before creating output state.
    try:
        parse_link_csv(source)
    except TelemetryError as exc:
        raise OperatorInputError(f"Invalid telemetry input: {exc}") from exc
    threshold = _threshold(threshold_db)
    plan = None
    if fault_plan_path is not None:
        raw_plan = _read_bounded(fault_plan_path, MAX_PLAN_BYTES, "Fault plan")
        try:
            plan = FaultPlan.from_json(raw_plan.decode("utf-8"))
        except (UnicodeDecodeError, FaultError) as exc:
            raise OperatorInputError(f"Invalid fault plan: {exc}") from exc
        try:
            inject_link_csv(source, plan)
        except (FaultError, TelemetryError) as exc:
            raise OperatorInputError(f"Fault plan cannot apply: {exc}") from exc
    tasks = _tasks(source, threshold_db, plan)
    journal_plan = JournalPlan.from_tasks(tasks)
    source_sha = sha256(source).hexdigest()
    request = {
        "schema_version": 1,
        "workflow": "communications-link-verification",
        "source_sha256": source_sha,
        "source_bytes": len(source),
        "threshold_db": threshold_db,
        "fault_plan_sha256": None if plan is None else plan.sha256,
        "journal_plan_sha256": journal_plan.sha256,
    }
    output = Path(output_directory)
    if resume_run_id is None:
        try:
            output.mkdir()
        except FileExistsError as exc:
            raise OperatorOutputError("Output directory already exists") from exc
        except OSError as exc:
            raise OperatorOutputError("Cannot create output directory") from exc
        run_id = str(uuid4())
        request["run_id"] = run_id
        _publish(output / "request.json", _canonical(request) + "\n")
        inspection = run_journaled(output / "journal.sqlite", tasks, run_id=run_id)
    else:
        run_id = resume_run_id
        request["run_id"] = run_id
        if output.is_symlink() or not output.is_dir():
            raise OperatorOutputError("Resume output directory is unavailable")
        _reject_symlinks(output)
        request_path = output / "request.json"
        if not request_path.is_file():
            raise OperatorOutputError("Saved operator request is unavailable")
        try:
            saved_request = request_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise OperatorOutputError("Saved operator request is unavailable") from exc
        if saved_request != _canonical(request) + "\n":
            raise OperatorInputError("Resume inputs conflict with the saved operator request")
        inspection = resume_journaled(output / "journal.sqlite", run_id, tasks)
    if inspection.state != "completed":
        raise OperatorError(f"Run requires attention: {inspection.state}")

    evidence = export_journal_evidence(
        output / "journal.sqlite", run_id, journal_plan
    )
    bindings = RequirementBindings.from_mapping({"COM-LINK-001": "check"})
    with EvidenceStore(output / "evidence.sqlite") as store:
        store.save(evidence, bindings)
    with EvidenceStore(output / "evidence.sqlite") as store:
        reopened_evidence, reopened_bindings = store.load(run_id, bindings.sha256)
    evidence_tasks = {
        item["task_id"]: item for item in reopened_evidence.to_dict()["tasks"]
    }
    provenance_task = "fault" if plan is not None and (
        evidence_tasks["fault"]["status"] == "succeeded"
    ) else None
    report = VerificationReport.from_evidence(
        reopened_evidence, reopened_bindings,
        detail_task_id="detail", provenance_task_id=provenance_task,
    )
    _publish(output / "evidence.json", reopened_evidence.to_json() + "\n")
    _publish(output / "bindings.json", reopened_bindings.to_json() + "\n")
    _publish(output / "report.json", report.to_json() + "\n")
    _publish(output / "report.html", report.to_html())
    # Ensure the CLI/result uses the same canonical threshold accepted above.
    del threshold
    return LinkRunResult(
        run_id=run_id,
        verdict=report.to_dict()["requirement"]["verdict"],
        evidence_path=output / "evidence.json",
        report_json_path=output / "report.json",
        report_html_path=output / "report.html",
        report_sha256=report.sha256,
    )


def run_link_verification(
    source_path: str | Path, output_directory: str | Path, *,
    threshold_db: str, fault_plan_path: str | Path | None = None,
    resume_run_id: str | None = None,
) -> LinkRunResult:
    """Normalize storage/integrity failures at the public operator boundary."""
    try:
        return _run_link_verification(
            source_path, output_directory, threshold_db=threshold_db,
            fault_plan_path=fault_plan_path, resume_run_id=resume_run_id,
        )
    except OperatorError:
        raise
    except (BindingError, FaultError, JournalError, ReportError, StorageError,
            TelemetryError, sqlite3.Error, OSError) as exc:
        raise OperatorError(f"{type(exc).__name__}: {exc}") from exc
