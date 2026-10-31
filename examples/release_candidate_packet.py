"""Assemble and inspect Chimera's bounded M4 review evidence packet.

The packet is a portable, candidate-bound review input.  It preserves generated
engineering records and an intentionally blank acceptance script, but it never
declares M4/M5 approval, a release, a tag, or human acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

from chimera.api import CompletedLinkRun, OperatorAPIError
from chimera.handoff import (
    ARTIFACT_NAMES, HandoffError, inspect_handoff_bundle,
)
from chimera.reports import ReportError, VerificationReport
from chimera.telemetry import TelemetryError, parse_link_csv
from examples.operator_acceptance_prep import _worksheet as _acceptance_worksheet


ROOT = Path(__file__).resolve().parents[1]
PACKET_ID = "p7-m4-review-evidence-packet-v1"
MANIFEST_NAME = "manifest.json"
ACCEPTANCE_SCRIPT_NAME = "M4-ACCEPTANCE-SCRIPT.md"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
MAX_SOURCE_FILE_BYTES = 2_097_152
MAX_PACKET_CONTENT_BYTES = 16_777_216
MAX_PACKET_FILE_BYTES = 20_971_520
MAX_PACKET_FILES = 128
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REQUIREMENT_ROW = re.compile(
    r"^\|\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[0-9]{3})\s*\|",
    re.MULTILINE,
)
_REGULAR_MODE = stat.S_IFREG | 0o644

ACCEPTANCE_SOURCE_SCOPE = "synthetic reference fixtures; no measured radio data"
ACCEPTANCE_IDENTITY_LIMIT = (
    "Git SHA and content hashes are identities, not signatures, trusted build "
    "attestation, execution authorship or measurement authenticity"
)
PERFORMANCE_SCOPE = (
    "local synthetic prototype workload; not hardware, production capacity, "
    "multi-user load, or a service-level objective"
)
THREAT_SCOPE = (
    "model structure, candidate binding and reference validity only; not a "
    "penetration test, vulnerability scan, control-effectiveness proof, "
    "security certification, residual-risk acceptance or phase approval"
)
READINESS_SCOPE = (
    "candidate-bound M4 review inputs only; not a live GitHub query, test-result "
    "claim, release declaration, phase closure, tag, deployment or human acceptance"
)
PACKET_SCOPE = (
    "portable exact-candidate M4 review inputs only; not a live GitHub query, "
    "CI result, release declaration, tag, deployment, phase closure or human acceptance"
)
PENDING_HUMAN_EVIDENCE = (
    "D-004 through D-006 interface decisions",
    "Leo operator walkthrough",
    "M4 entry-to-acceptance decision",
    "M5 final product acceptance",
    "Manual physical-device observations",
    "Screen-reader and WCAG observations",
    "Separate P3, P4 and P5 dispositions",
)

ASSESSMENT_NAMES = {
    "performance": "assessments/release-performance.json",
    "threat_model": "assessments/release-threat-model.json",
    "readiness": "assessments/release-readiness.json",
}
ACCEPTANCE_RUN_ARTIFACT_NAMES = (
    "bindings.json",
    "evidence.json",
    "evidence.sqlite",
    "journal.sqlite",
    "report.html",
    "report.json",
    "request.json",
)
ACCEPTANCE_RUN_LABELS = (
    "passing", "natural-failure", "synthetic-failure",
)
ACCEPTANCE_MALFORMED_CASES = (
    "malformed-value", "missing-column", "invalid-unit",
)
ACCEPTANCE_HANDOFF_NAMES = (
    "synthetic-failure-a.zip",
    "synthetic-failure-b.zip",
    "dashboard-synthetic-failure.zip",
)
ACCEPTANCE_WORKSPACE_NAMES = frozenset(
    {
        "acceptance-preparation.json",
        "operator-observations.md",
        "controls/missing-evidence-report.json",
        "controls/missing-evidence-report.html",
    }
    | {
        f"runs/{label}/{name}"
        for label in ACCEPTANCE_RUN_LABELS
        for name in ACCEPTANCE_RUN_ARTIFACT_NAMES
    }
    | {f"inputs/{case}.csv" for case in ACCEPTANCE_MALFORMED_CASES}
    | {f"handoffs/{name}" for name in ACCEPTANCE_HANDOFF_NAMES}
)
PERFORMANCE_METRICS = {
    "operator_run_p95_ms": ("operator_run", 3_000.0),
    "handoff_round_trip_p95_ms": ("handoff_round_trip", 1_000.0),
    "dashboard_snapshot_p95_ms": ("dashboard_snapshot", 3_000.0),
}
CANDIDATE_FILES = (
    "README.md",
    "docs/APPROVALS.md",
    "docs/MANUAL.md",
    "docs/QUALITY.md",
    "docs/REQUIREMENTS.md",
    "docs/THREAT_MODEL.md",
    "docs/release-readiness-v1.json",
    "docs/threat-model-v1.json",
    "docs/reviews/2026-10-24-p345-operator-acceptance.md",
)
ACCEPTANCE_FIELDS = {
    "schema_version", "record_type", "candidate_commit_sha",
    "candidate_checks", "generated_at_utc", "source_scope",
    "source_identity_limit", "engineering_status", "acceptance_status",
    "controls", "natural_reference", "synthetic_provenance",
    "malformed_inputs", "missing_evidence", "completed_resume", "runs",
    "handoff_manifest", "handoffs", "dashboard_download",
    "human_observations", "observation_worksheet",
}
PERFORMANCE_FIELDS = {
    "schema_version", "record_type", "workload_version",
    "candidate_commit_sha", "candidate_checks", "generated_at_utc", "clock",
    "environment", "workload", "targets_ms", "measurements",
    "target_results", "status", "scope",
}
THREAT_FIELDS = {
    "schema_version", "record_type", "model_id", "candidate_commit_sha",
    "candidate_checks", "generated_at_utc", "model", "evidence_files",
    "checks", "must_fix_before_m4", "status", "release_decision",
    "human_acceptance", "scope",
}
READINESS_FIELDS = {
    "schema_version", "record_type", "candidate_commit_sha",
    "candidate_checks", "generated_at_utc", "checks", "defects",
    "evidence_files", "guides", "human_acceptance", "m4_decision",
    "m5_decision", "manifest", "pending_human_evidence", "requirements",
    "scope", "status",
}
MANIFEST_FIELDS = {
    "schema_version", "record_type", "packet_id", "candidate_commit_sha",
    "candidate_checks", "generated_at_utc", "files", "source_records",
    "candidate_review_files", "checks", "release_blockers", "status",
    "m4_decision", "m5_decision", "human_acceptance", "scope",
}


class ReleaseCandidatePacketError(RuntimeError):
    """An M4 review packet could not be assembled or inspected safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseCandidatePacketError(message)


def _pretty(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False,
    ) + "\n").encode("utf-8")


def _compact(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ) + "\n").encode("utf-8")


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ReleaseCandidatePacketError(f"duplicate JSON field: {key}")
        document[key] = value
    return document


def _load_json_bytes(content: bytes, label: str, *, style: str) -> dict:
    _require(type(content) is bytes and 0 < len(content) <= MAX_SOURCE_FILE_BYTES,
             f"{label} size is outside the supported bound")
    try:
        document = json.loads(
            content.decode("utf-8"), object_pairs_hook=_reject_duplicate_fields,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ReleaseCandidatePacketError(
                    f"{label} contains non-finite JSON: {value}"
                )
            ),
        )
    except ReleaseCandidatePacketError:
        raise
    except (RecursionError, UnicodeError, ValueError) as exc:
        raise ReleaseCandidatePacketError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    _require(type(document) is dict, f"{label} must be a JSON object")
    expected = _pretty(document) if style == "pretty" else _compact(document)
    _require(content == expected, f"{label} must use canonical formatting")
    return document


def _object(value: object, keys: set[str], label: str) -> dict:
    _require(type(value) is dict, f"{label} must be an object")
    _require(set(value) == keys, f"{label} fields changed")
    return value


def _list(value: object, label: str) -> list:
    _require(type(value) is list, f"{label} must be a list")
    return value


def _utc_timestamp(value: object, label: str) -> str:
    _require(type(value) is str, f"{label} must be UTC timestamp text")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReleaseCandidatePacketError(
            f"{label} must be canonical UTC timestamp text"
        ) from exc
    _require(
        parsed.tzinfo == timezone.utc
        and parsed.isoformat(timespec="seconds").replace("+00:00", "Z") == value,
        f"{label} must be canonical UTC timestamp text",
    )
    return value


def _generated_timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    return _utc_timestamp(value, "generated_at_utc")


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *arguments], cwd=ROOT, capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseCandidatePacketError(
            "Git checkout identity is unavailable"
        ) from exc


def _validate_candidate_checkout(candidate_commit: str) -> None:
    if type(candidate_commit) is not str or _COMMIT.fullmatch(candidate_commit) is None:
        raise ReleaseCandidatePacketError(
            "candidate commit must be a full lowercase 40-character Git SHA"
        )
    head = _git("rev-parse", "HEAD")
    actual = head.stdout.strip()
    if (head.returncode != 0 or _COMMIT.fullmatch(actual) is None
            or actual != candidate_commit):
        raise ReleaseCandidatePacketError(
            "candidate commit must equal the exact checked-out Git HEAD"
        )
    status_result = _git("status", "--porcelain", "--untracked-files=normal")
    if status_result.returncode != 0:
        raise ReleaseCandidatePacketError("Git checkout status is unavailable")
    if status_result.stdout:
        raise ReleaseCandidatePacketError(
            "release-candidate packet requires a clean checkout"
        )


def _has_symlink_ancestor(path: Path) -> bool:
    current = path.absolute()
    while True:
        if current.is_symlink():
            return True
        if current.parent == current:
            return False
        current = current.parent


def _outside_checkout(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    checkout = ROOT.resolve()
    _require(
        resolved != checkout and checkout not in resolved.parents,
        f"{label} must be outside the source checkout",
    )
    return resolved


def _safe_name(value: object, label: str) -> str:
    _require(type(value) is str and value and len(value) <= 240,
             f"{label} must be a bounded relative POSIX path")
    _require("\\" not in value and "\x00" not in value,
             f"{label} must be a relative POSIX path")
    path = PurePosixPath(value)
    _require(
        not path.is_absolute() and value == path.as_posix()
        and all(part not in ("", ".", "..") for part in path.parts),
        f"{label} must be a safe relative POSIX path",
    )
    return value


def _read_regular(path: Path, label: str,
                  maximum: int = MAX_SOURCE_FILE_BYTES) -> bytes:
    _require(not path.is_symlink() and path.is_file(),
             f"{label} must be a regular file")
    try:
        with path.open("rb") as stream:
            mode = os.fstat(stream.fileno()).st_mode
            _require(stat.S_ISREG(mode), f"{label} must be a regular file")
            content = stream.read(maximum + 1)
    except ReleaseCandidatePacketError:
        raise
    except OSError as exc:
        raise ReleaseCandidatePacketError(f"{label} is unavailable") from exc
    _require(0 < len(content) <= maximum,
             f"{label} size is outside the supported bound")
    return content


def _identity(path: str, content: bytes) -> dict:
    return {
        "path": path,
        "byte_count": len(content),
        "sha256": sha256(content).hexdigest(),
    }


def _validate_identity(value: object, content: bytes, label: str,
                       expected_path: str | None = None) -> str:
    item = _object(value, {"path", "byte_count", "sha256"}, label)
    path = _safe_name(item["path"], f"{label}.path")
    if expected_path is not None:
        _require(path == expected_path, f"{label}.path changed")
    _require(type(item["byte_count"]) is int
             and item["byte_count"] == len(content),
             f"{label}.byte_count does not match content")
    _require(type(item["sha256"]) is str
             and _SHA256.fullmatch(item["sha256"]) is not None
             and item["sha256"] == sha256(content).hexdigest(),
             f"{label}.sha256 does not match content")
    return path


def _validate_acceptance_artifact(value: object, files: dict[str, bytes],
                                  referenced: set[str], label: str) -> None:
    artifact = _object(value, {"path", "bytes", "sha256"}, label)
    path = _safe_name(artifact["path"], f"{label}.path")
    _require(path in files, f"{label} is missing from the acceptance workspace")
    _require(path not in referenced, f"duplicate acceptance artifact reference: {path}")
    content = files[path]
    _require(type(artifact["bytes"]) is int
             and artifact["bytes"] == len(content),
             f"{label}.bytes does not match workspace content")
    _require(type(artifact["sha256"]) is str
             and artifact["sha256"] == sha256(content).hexdigest(),
             f"{label}.sha256 does not match workspace content")
    referenced.add(path)


def _reopen_acceptance_run(files: dict[str, bytes], label: str) -> CompletedLinkRun:
    prefix = f"runs/{label}/"
    expected = {prefix + name for name in ARTIFACT_NAMES}
    _require(expected <= set(files),
             f"operator run {label} lacks portable completed artifacts")
    try:
        with tempfile.TemporaryDirectory(
                prefix="chimera-packet-completed-run-") as directory:
            root = Path(directory)
            for name in ARTIFACT_NAMES:
                (root / name).write_bytes(files[prefix + name])
            return CompletedLinkRun.open(root)
    except (OSError, OperatorAPIError) as exc:
        raise ReleaseCandidatePacketError(
            f"operator run {label} does not reopen as a completed run"
        ) from exc


def _inspect_acceptance_handoff(content: bytes, label: str) -> dict:
    try:
        with tempfile.TemporaryDirectory(
                prefix="chimera-packet-handoff-") as directory:
            path = Path(directory) / "handoff.zip"
            path.write_bytes(content)
            return inspect_handoff_bundle(path)
    except (OSError, HandoffError) as exc:
        raise ReleaseCandidatePacketError(
            f"operator handoff {label} does not reopen"
        ) from exc


def _validate_acceptance_workspace(files: dict[str, bytes],
                                   candidate_commit: str) -> dict:
    record_name = "acceptance-preparation.json"
    _require(record_name in files, "acceptance workspace lacks its engineering record")
    record = _load_json_bytes(
        files[record_name], "operator acceptance record", style="compact"
    )
    _object(record, ACCEPTANCE_FIELDS, "operator acceptance record")
    _require(type(record["schema_version"]) is int
             and record["schema_version"] == 1,
             "operator acceptance schema version changed")
    _require(record["record_type"] == "chimera.operator-acceptance-preparation",
             "operator acceptance record type changed")
    _require(record["candidate_commit_sha"] == candidate_commit,
             "operator acceptance candidate does not match packet candidate")
    _utc_timestamp(record["generated_at_utc"], "operator acceptance generated_at_utc")
    _require(record["engineering_status"] == "passed",
             "operator engineering preparation is not passed")
    _require(record["acceptance_status"] == "pending_human_observation",
             "operator acceptance status must remain pending")
    _require(record["source_scope"] == ACCEPTANCE_SOURCE_SCOPE
             and record["source_identity_limit"] == ACCEPTANCE_IDENTITY_LIMIT,
             "operator evidence scope or identity limitation changed")
    checks = _object(
        record["candidate_checks"],
        {"before_controls", "before_publication"},
        "operator candidate checks",
    )
    _require(set(checks.values()) == {"matched_clean_head"},
             "operator candidate checks are incomplete")
    controls = _list(record["controls"], "operator controls")
    _require(
        [item.get("control_id") if type(item) is dict else None
         for item in controls] == [f"P345-{number}" for number in range(1, 9)]
        and all(type(item) is dict and item.get("status") == "passed"
                for item in controls),
        "operator engineering controls are incomplete",
    )
    natural = _object(
        record["natural_reference"],
        {"sample_index", "link_margin_db", "threshold_db"},
        "operator natural-failure reference",
    )
    _require(natural == {
        "sample_index": 2,
        "link_margin_db": "2.0",
        "threshold_db": "3.0",
    }, "operator natural-failure reference changed")
    provenance = record["synthetic_provenance"]
    _require(type(provenance) is dict and provenance.get("synthetic") is True,
             "operator synthetic-failure provenance changed")
    human = _object(
        record["human_observations"],
        {"status", "keyboard_operator_journey", "desktop_browser_diversity",
         "physical_device", "screen_reader_wcag", "leo_validation",
         "phase_disposition"},
        "operator human observations",
    )
    _require(
        all(human[key] == "not_performed" for key in human
            if key != "phase_disposition")
        and human["phase_disposition"] == "pending",
        "operator human observations must remain unperformed and pending",
    )
    referenced: set[str] = set()
    runs = _list(record["runs"], "operator runs")
    _require(
        len(runs) == 3
        and {item.get("label") for item in runs if type(item) is dict}
        == set(ACCEPTANCE_RUN_LABELS),
        "operator PASS/natural-FAIL/synthetic-FAIL inventory changed",
    )
    expected_verdicts = {
        "passing": "pass", "natural-failure": "fail",
        "synthetic-failure": "fail",
    }
    reopened_runs = {}
    for index, run in enumerate(runs):
        _require(type(run) is dict and set(run) == {
            "label", "run_id", "verdict", "report_sha256", "artifacts"
        }, f"operator run {index} fields changed")
        _require(run["verdict"] == expected_verdicts[run["label"]],
                 f"operator run {run['label']} verdict changed")
        run_artifacts = _list(
            run["artifacts"], f"operator run {index} artifacts"
        )
        expected_artifact_paths = {
            f"runs/{run['label']}/{name}"
            for name in ACCEPTANCE_RUN_ARTIFACT_NAMES
        }
        actual_artifact_paths = [
            artifact.get("path") if type(artifact) is dict else None
            for artifact in run_artifacts
        ]
        _require(
            len(actual_artifact_paths) == len(expected_artifact_paths)
            and set(actual_artifact_paths) == expected_artifact_paths,
            f"operator run {run['label']} artifact inventory changed",
        )
        for artifact_index, artifact in enumerate(run_artifacts):
            _validate_acceptance_artifact(
                artifact, files, referenced,
                f"operator run {index} artifact {artifact_index}",
            )
        reopened = _reopen_acceptance_run(files, run["label"])
        reopened_document = reopened.report.to_dict()
        _require(run["run_id"] == reopened_document["run_id"]
                 and run["verdict"]
                 == reopened_document["requirement"]["verdict"]
                 and run["report_sha256"] == reopened.report.sha256,
                 f"operator run {run['label']} record conflicts with artifacts")
        expected_synthetic = run["label"] == "synthetic-failure"
        _require((reopened_document["provenance"] is not None)
                 == expected_synthetic,
                 f"operator run {run['label']} provenance changed")
        reopened_runs[run["label"]] = reopened
    natural_document = reopened_runs["natural-failure"].report.to_dict()
    synthetic_document = reopened_runs["synthetic-failure"].report.to_dict()
    natural_detail = natural_document["detail"]["link_margin"]
    _require(
        natural_detail["threshold_db"] == natural["threshold_db"]
        and natural_detail["minimum_link_margin_db"] == natural["link_margin_db"]
        and len(natural_detail["failing_samples"]) == 1
        and natural_detail["failing_samples"][0]["sample_index"]
        == natural["sample_index"],
        "operator natural-failure record conflicts with completed artifacts",
    )
    _require(synthetic_document["detail"]["link_margin"] == natural_detail
             and synthetic_document["provenance"] == provenance,
             "operator synthetic-failure record conflicts with completed artifacts")
    malformed = _list(record["malformed_inputs"], "malformed input records")
    _require(
        [item.get("case") if type(item) is dict else None for item in malformed]
        == list(ACCEPTANCE_MALFORMED_CASES),
        "malformed input inventory changed",
    )
    for index, item in enumerate(malformed):
        _require(type(item) is dict and set(item) == {
            "case", "exception", "error", "output_created", "input"
        }, f"malformed input {index} fields changed")
        _require(item["exception"] == "OperatorInputError"
                 and item["output_created"] is False,
                 f"malformed input {index} did not remain a refusal")
        _validate_acceptance_artifact(
            item["input"], files, referenced, f"malformed input {index} artifact"
        )
        input_path = item["input"]["path"]
        _require(
            input_path == f"inputs/{item['case']}.csv",
            f"malformed input {index} artifact path changed",
        )
        try:
            parse_link_csv(files[input_path])
        except TelemetryError:
            pass
        else:
            raise ReleaseCandidatePacketError(
                f"malformed input {index} is accepted by the product parser"
            )
    missing = _object(
        record["missing_evidence"],
        {"requirement_verdict", "detail_status", "artifacts"},
        "missing-evidence record",
    )
    _require(missing["requirement_verdict"] == "not_evaluated"
             and missing["detail_status"] == "unavailable",
             "missing evidence no longer remains unavailable/not evaluated")
    for index, artifact in enumerate(
            _list(missing["artifacts"], "missing-evidence artifacts")):
        _validate_acceptance_artifact(
            artifact, files, referenced, f"missing-evidence artifact {index}"
        )
    missing_paths = [item["path"] for item in missing["artifacts"]]
    _require(missing_paths == [
        "controls/missing-evidence-report.json",
        "controls/missing-evidence-report.html",
    ], "missing-evidence artifact inventory changed")
    try:
        missing_report = VerificationReport.from_json(
            files[missing_paths[0]].decode("utf-8")
        )
    except (UnicodeError, ReportError) as exc:
        raise ReleaseCandidatePacketError(
            "missing-evidence report does not reopen"
        ) from exc
    missing_document = missing_report.to_dict()
    _require(
        missing_document["requirement"]["verdict"]
        == missing["requirement_verdict"]
        and missing_document["detail"]["status"] == missing["detail_status"]
        and files[missing_paths[1]] == missing_report.to_html().encode("utf-8"),
        "missing-evidence artifacts conflict with the operator record",
    )
    resume = _object(
        record["completed_resume"],
        {"before_sha256", "after_sha256", "portable_artifacts_unchanged"},
        "completed-resume control",
    )
    before_resume = resume["before_sha256"]
    after_resume = resume["after_sha256"]
    _require(
        type(before_resume) is dict
        and set(before_resume) == set(ARTIFACT_NAMES)
        and before_resume == after_resume
        and resume["portable_artifacts_unchanged"] is True
        and all(type(name) is str and name
                and type(digest) is str and _SHA256.fullmatch(digest) is not None
                for name, digest in before_resume.items()),
        "completed resume did not preserve portable artifacts",
    )
    expected_resume = {
        name: sha256(files[f"runs/passing/{name}"]).hexdigest()
        for name in ARTIFACT_NAMES
    }
    _require(before_resume == expected_resume,
             "completed resume identities conflict with passing artifacts")
    handoffs = _list(record["handoffs"], "operator handoffs")
    _require(len(handoffs) == 3, "operator handoff inventory changed")
    handoff_paths = []
    for index, artifact in enumerate(handoffs):
        _validate_acceptance_artifact(
            artifact, files, referenced, f"operator handoff {index}"
        )
        handoff_paths.append(artifact["path"])
    _require(
        handoff_paths
        == [f"handoffs/{name}" for name in ACCEPTANCE_HANDOFF_NAMES]
        and len({files[path] for path in handoff_paths}) == 1,
        "operator handoffs are not byte-identical",
    )
    synthetic_run = next(item for item in runs if item["label"] == "synthetic-failure")
    handoff_manifest = record["handoff_manifest"]
    reopened_handoffs = [
        _inspect_acceptance_handoff(files[path], str(index))
        for index, path in enumerate(handoff_paths)
    ]
    _require(
        type(handoff_manifest) is dict
        and all(item == handoff_manifest for item in reopened_handoffs)
        and handoff_manifest.get("run_id") == synthetic_run["run_id"]
        and handoff_manifest.get("requirement_id") == "COM-LINK-001"
        and handoff_manifest.get("verdict") == "fail",
        "operator handoff manifest changed",
    )
    dashboard = _object(
        record["dashboard_download"],
        {"matches_file_export", "headers"},
        "operator dashboard download",
    )
    expected_headers = {
        "Content-Type": "application/zip",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Disposition": (
            f'attachment; filename="chimera-{synthetic_run["run_id"]}-handoff.zip"'
        ),
    }
    _require(
        dashboard["matches_file_export"] is True
        and dashboard["headers"] == expected_headers,
        "operator dashboard export control changed",
    )
    worksheet_artifact = record["observation_worksheet"]
    _validate_acceptance_artifact(
        worksheet_artifact, files, referenced,
        "operator observation worksheet",
    )
    _require(
        worksheet_artifact["path"] == "operator-observations.md",
        "operator observation worksheet path changed",
    )
    _require(set(files) == referenced | {record_name},
             "acceptance workspace contains missing or unexpected files")
    _require(
        set(files) == ACCEPTANCE_WORKSPACE_NAMES,
        "acceptance workspace version-1 member allowlist changed",
    )
    worksheet_path = record["observation_worksheet"]["path"]
    try:
        worksheet = files[worksheet_path].decode("utf-8")
    except UnicodeError as exc:
        raise ReleaseCandidatePacketError(
            "operator observation worksheet is not UTF-8"
        ) from exc
    _require(
        worksheet == _acceptance_worksheet(candidate_commit),
        "operator observation worksheet is not the canonical blank candidate form",
    )
    _require("- [x]" not in worksheet.lower(),
             "operator observation worksheet contains a completed checkbox")
    return record


def _validate_performance(record: dict, candidate_commit: str) -> list[str]:
    _object(record, PERFORMANCE_FIELDS, "performance record")
    _require(type(record["schema_version"]) is int
             and record["schema_version"] == 1,
             "performance schema version changed")
    _require(record["record_type"] == "chimera.release-performance-baseline"
             and record["workload_version"] == "p7-local-prototype-v1",
             "performance record contract changed")
    _require(record["clock"] == "time.perf_counter_ns monotonic elapsed time"
             and record["scope"] == PERFORMANCE_SCOPE,
             "performance clock or scope changed")
    _require(record["candidate_commit_sha"] == candidate_commit,
             "performance candidate does not match packet candidate")
    _utc_timestamp(record["generated_at_utc"], "performance generated_at_utc")
    checks = _object(
        record["candidate_checks"],
        {"before_measurement", "before_publication"},
        "performance candidate checks",
    )
    _require(set(checks.values()) == {"matched_clean_head"},
             "performance candidate checks are incomplete")
    environment = _object(
        record["environment"],
        {"python_implementation", "python_version", "operating_system",
         "kernel_release", "machine", "logical_cpu_count"},
        "performance environment",
    )
    _require(
        all(type(environment[key]) is str and environment[key]
            for key in ("python_implementation", "python_version",
                        "operating_system", "kernel_release", "machine"))
        and (environment["logical_cpu_count"] is None
             or (type(environment["logical_cpu_count"]) is int
                 and environment["logical_cpu_count"] > 0)),
        "performance environment values changed",
    )
    _require(record["workload"] == {
        "source": "generated synthetic communications CSV",
        "sample_count": 10_000,
        "workspace_runs": 10,
        "handoff_iterations": 10,
        "dashboard_iterations": 5,
        "threshold_db": "3.0",
        "minimum_link_margin_db": "2.0",
        "expected_verdict": "fail",
    }, "performance workload changed")
    targets = _object(
        record["targets_ms"], set(PERFORMANCE_METRICS),
        "performance targets",
    )
    measurements = _object(
        record["measurements"],
        {group for group, _ in PERFORMANCE_METRICS.values()},
        "performance measurements",
    )
    results = _object(
        record["target_results"],
        set(PERFORMANCE_METRICS),
        "performance target results",
    )
    statuses = []
    blockers = []
    for metric, item in results.items():
        _require(type(item) is dict and set(item) == {
            "observed_ms", "target_ms", "status"
        }, f"performance result fields changed: {metric}")
        group, fixed_target = PERFORMANCE_METRICS[metric]
        observed = item["observed_ms"]
        target = item["target_ms"]
        measurement = _object(
            measurements[group],
            {"samples_ms", "p50_ms", "p95_ms", "max_ms"},
            f"performance measurement {group}",
        )
        samples = measurement["samples_ms"]
        expected_sample_count = 5 if group == "dashboard_snapshot" else 10
        _require(
            type(samples) is list and len(samples) == expected_sample_count
            and all(type(value) in (int, float) and math.isfinite(value)
                    and value >= 0 for value in samples),
            f"performance samples are invalid: {metric}",
        )
        ordered = sorted(samples)
        derived_p50 = ordered[max(1, math.ceil(0.50 * len(ordered))) - 1]
        derived_p95 = ordered[max(1, math.ceil(0.95 * len(ordered))) - 1]
        _require(measurement["p50_ms"] == derived_p50
                 and measurement["p95_ms"] == derived_p95
                 and measurement["max_ms"] == max(samples),
                 f"performance summary is inconsistent: {metric}")
        _require(type(observed) in (int, float) and math.isfinite(observed)
                 and observed >= 0 and observed == measurement["p95_ms"],
                 f"performance observed value is inconsistent: {metric}")
        _require(type(target) in (int, float) and math.isfinite(target)
                 and target == fixed_target and targets[metric] == fixed_target,
                 f"performance target changed: {metric}")
        derived_status = "passed" if observed <= target else "failed"
        _require(item["status"] == derived_status,
                 f"performance result status is inconsistent: {metric}")
        statuses.append(item["status"])
        if item["status"] == "failed":
            blockers.append(f"performance:{metric}")
    expected_status = "passed" if all(item == "passed" for item in statuses) else "failed"
    _require(record["status"] == expected_status,
             "performance aggregate status is inconsistent")
    return blockers


def _validate_threat(record: dict, candidate_commit: str,
                     candidate_files: dict[str, bytes]) -> list[str]:
    _object(record, THREAT_FIELDS, "threat-model record")
    _require(type(record["schema_version"]) is int
             and record["schema_version"] == 1,
             "threat-model schema version changed")
    _require(record["record_type"] == "chimera.release-threat-model-assessment"
             and record["model_id"] == "p7-local-prototype-threat-model-v1",
             "threat-model record type changed")
    _require(record["scope"] == THREAT_SCOPE,
             "threat-model scope changed")
    _require(record["candidate_commit_sha"] == candidate_commit,
             "threat-model candidate does not match packet candidate")
    _utc_timestamp(record["generated_at_utc"], "threat-model generated_at_utc")
    checks = _object(
        record["candidate_checks"],
        {"before_assessment", "before_publication"},
        "threat-model candidate checks",
    )
    _require(set(checks.values()) == {"matched_clean_head"},
             "threat-model candidate checks are incomplete")
    _require(record["release_decision"] == "pending_m4_review"
             and record["human_acceptance"] == "not_granted",
             "threat-model review/acceptance state must remain pending")
    blockers = _list(record["must_fix_before_m4"], "threat-model blockers")
    _require(all(type(item) is str and item for item in blockers),
             "threat-model blockers must be nonempty identifiers")
    expected = "blocked_by_open_release_threat" if blockers else "model_complete"
    _require(record["status"] == expected,
             "threat-model aggregate status is inconsistent")
    control_checks = _list(record["checks"], "threat-model checks")
    _require(
        [item.get("id") if type(item) is dict else None
         for item in control_checks]
        == [f"THREAT-{number:03d}" for number in range(1, 6)],
        "threat-model check inventory changed",
    )
    _require(
        all(type(item) is dict and set(item) == {
            "id", "status", "description"
        } for item in control_checks)
        and all(item["status"] == "passed" for item in control_checks[:4])
        and control_checks[4]["status"] == (
            "blocked" if blockers else "passed"
        ),
        "threat-model check statuses are inconsistent",
    )
    model = record["model"]
    model_bytes = candidate_files["docs/threat-model-v1.json"]
    _require(type(model) is dict and set(model) == {
        "path", "byte_count", "sha256", "asset_count", "actor_count",
        "trust_boundary_count", "threat_count", "control_count",
        "evidence_file_count", "disposition_counts",
    } and model["path"] == "docs/threat-model-v1.json"
             and model["byte_count"] == len(model_bytes)
             and model["sha256"] == sha256(model_bytes).hexdigest(),
             "threat-model source identity does not match candidate")
    model_document = _load_json_bytes(
        model_bytes, "candidate threat-model document", style="pretty"
    )
    _require(model_document.get("schema_version") == 1
             and model_document.get("record_type")
             == "chimera.local-prototype-threat-model"
             and model_document.get("model_id") == record["model_id"],
             "candidate threat-model document contract changed")
    assets = _list(model_document.get("assets"), "candidate threat-model assets")
    actors = _list(model_document.get("actors"), "candidate threat-model actors")
    boundaries = _list(
        model_document.get("trust_boundaries"),
        "candidate threat-model trust boundaries",
    )
    threats = _list(model_document.get("threats"), "candidate threat-model threats")
    evidence_paths: set[str] = set()
    control_ids: set[str] = set()
    dispositions: dict[str, int] = {}
    for threat_index, threat in enumerate(threats):
        _require(type(threat) is dict,
                 f"candidate threat-model threat {threat_index} changed")
        disposition = threat.get("engineering_disposition")
        _require(type(disposition) is str and disposition,
                 f"candidate threat-model disposition {threat_index} changed")
        dispositions[disposition] = dispositions.get(disposition, 0) + 1
        for control_index, control in enumerate(_list(
                threat.get("controls"),
                f"candidate threat-model threat {threat_index} controls")):
            _require(type(control) is dict
                     and type(control.get("id")) is str
                     and control["id"] not in control_ids,
                     f"candidate threat-model control {threat_index}:{control_index} changed")
            control_ids.add(control["id"])
            paths = _list(
                control.get("evidence_paths"),
                f"candidate threat-model control {control['id']} evidence",
            )
            _require(all(type(path) is str for path in paths),
                     f"candidate threat-model control {control['id']} evidence changed")
            evidence_paths.update(paths)
    review = model_document.get("release_review")
    _require(type(review) is dict
             and review.get("must_fix_before_m4") == blockers
             and review.get("decision_status") == "pending_m4_review"
             and review.get("human_acceptance") == "not_granted",
             "candidate threat-model release review is inconsistent")
    expected_counts = {
        "asset_count": len(assets),
        "actor_count": len(actors),
        "trust_boundary_count": len(boundaries),
        "threat_count": len(threats),
        "control_count": len(control_ids),
        "evidence_file_count": len(evidence_paths),
        "disposition_counts": dispositions,
    }
    _require(all(model[key] == value for key, value in expected_counts.items()),
             "threat-model summary does not match candidate model")
    evidence = _list(record["evidence_files"], "threat-model evidence files")
    observed_paths = []
    for index, item in enumerate(evidence):
        _require(type(item) is dict and set(item) == {
            "path", "byte_count", "sha256"
        }, f"threat-model evidence identity {index} changed")
        path = _safe_name(item["path"], f"threat-model evidence identity {index}.path")
        _require(type(item["byte_count"]) is int and item["byte_count"] > 0
                 and type(item["sha256"]) is str
                 and _SHA256.fullmatch(item["sha256"]) is not None,
                 f"threat-model evidence identity {index} is invalid")
        observed_paths.append(path)
    _require(observed_paths == sorted(evidence_paths),
             "threat-model evidence inventory does not match candidate model")
    return [f"threat:{item}" for item in blockers]


def _validate_readiness(record: dict, candidate_commit: str,
                        candidate_files: dict[str, bytes]) -> list[str]:
    _object(record, READINESS_FIELDS, "release-readiness record")
    _require(type(record["schema_version"]) is int
             and record["schema_version"] == 1,
             "release-readiness schema version changed")
    _require(record["record_type"] == "chimera.release-readiness-assessment",
             "release-readiness record type changed")
    _require(record["scope"] == READINESS_SCOPE,
             "release-readiness scope changed")
    _require(record["candidate_commit_sha"] == candidate_commit,
             "release-readiness candidate does not match packet candidate")
    generated_at = _utc_timestamp(
        record["generated_at_utc"], "release-readiness generated_at_utc"
    )
    candidate_checks = _object(
        record["candidate_checks"],
        {"before_assessment", "before_publication"},
        "release-readiness candidate checks",
    )
    _require(set(candidate_checks.values()) == {"matched_clean_head"},
             "release-readiness candidate checks are incomplete")
    _require(record["m4_decision"] == "pending"
             and record["m5_decision"] == "pending"
             and record["human_acceptance"] == "not_granted",
             "release-readiness decisions/acceptance must remain pending")
    defects = record["defects"]
    _require(type(defects) is dict
             and type(defects.get("open_release_blockers")) is list,
             "release-readiness defect inventory changed")
    blockers = defects["open_release_blockers"]
    _require(all(type(item) is int and item > 0 for item in blockers)
             and blockers == sorted(set(blockers)),
             "release-readiness blockers must be sorted unique issue numbers")
    snapshot_at = _utc_timestamp(
        defects.get("snapshot_at_utc"),
        "release-readiness defect snapshot_at_utc",
    )
    _require(datetime.fromisoformat(snapshot_at) <= datetime.fromisoformat(generated_at),
             "release-readiness defect snapshot is later than assessment")
    expected = "release_blockers_present" if blockers else "review_inputs_complete"
    _require(record["status"] == expected,
             "release-readiness aggregate status is inconsistent")
    control_checks = _list(record["checks"], "release-readiness checks")
    _require(
        [item.get("id") if type(item) is dict else None
         for item in control_checks]
        == [f"READINESS-{number:03d}" for number in range(1, 6)],
        "release-readiness check inventory changed",
    )
    _require(
        all(type(item) is dict and set(item) == {
            "id", "status", "description"
        } for item in control_checks)
        and control_checks[1]["status"] == (
            "blocked" if blockers else "passed"
        )
        and all(item["status"] == "passed"
                for index, item in enumerate(control_checks) if index != 1),
        "release-readiness check statuses are inconsistent",
    )
    manifest = record["manifest"]
    manifest_bytes = candidate_files["docs/release-readiness-v1.json"]
    _require(type(manifest) is dict and set(manifest) == {
        "id", "path", "byte_count", "sha256"
    }
             and manifest.get("id") == "p7-local-prototype-release-readiness-v1"
             and manifest.get("path") == "docs/release-readiness-v1.json"
             and manifest.get("byte_count") == len(manifest_bytes)
             and manifest.get("sha256") == sha256(manifest_bytes).hexdigest(),
             "release-readiness manifest identity does not match candidate")
    manifest_document = _load_json_bytes(
        manifest_bytes, "candidate release-readiness manifest", style="pretty"
    )
    _require(manifest_document.get("schema_version") == 1
             and manifest_document.get("record_type")
             == "chimera.local-prototype-release-readiness"
             and manifest_document.get("manifest_id") == manifest["id"],
             "candidate release-readiness manifest contract changed")
    groups = _list(
        manifest_document.get("requirement_groups"),
        "candidate release-readiness requirement groups",
    )
    covered_ids = []
    group_ids = []
    expected_evidence_paths: set[str] = set()
    for index, group in enumerate(groups):
        _require(type(group) is dict and set(group) == {
            "group_id", "requirement_ids", "evidence_paths"
        }, f"candidate release-readiness group {index} changed")
        group_ids.append(group["group_id"])
        ids = _list(group["requirement_ids"], f"candidate readiness group {index} IDs")
        paths = _list(
            group["evidence_paths"], f"candidate readiness group {index} evidence"
        )
        _require(ids == sorted(set(ids))
                 and all(type(item) is str for item in ids)
                 and paths == sorted(set(paths))
                 and all(type(item) is str for item in paths),
                 f"candidate release-readiness group {index} inventory changed")
        covered_ids.extend(ids)
        expected_evidence_paths.update(paths)
    _require(group_ids == sorted(set(group_ids)),
             "candidate release-readiness group inventory changed")
    try:
        requirements_text = candidate_files["docs/REQUIREMENTS.md"].decode("utf-8")
    except UnicodeError as exc:
        raise ReleaseCandidatePacketError(
            "candidate requirements document is not UTF-8"
        ) from exc
    declared_ids = sorted(_REQUIREMENT_ROW.findall(requirements_text))
    _require(bool(declared_ids) and len(declared_ids) == len(set(declared_ids))
             and sorted(covered_ids) == declared_ids
             and len(covered_ids) == len(set(covered_ids)),
             "release-readiness requirement coverage is incomplete")
    requirements = _object(
        record["requirements"],
        {"covered_count", "declared_count", "group_count"},
        "release-readiness requirement summary",
    )
    _require(requirements == {
        "covered_count": len(declared_ids),
        "declared_count": len(declared_ids),
        "group_count": len(groups),
    }, "release-readiness requirement summary does not match candidate")

    snapshot = manifest_document.get("defect_snapshot")
    _require(type(snapshot) is dict
             and snapshot.get("observed_at_utc") == snapshot_at
             and type(snapshot.get("open_defects")) is list,
             "release-readiness defect snapshot does not match candidate")
    snapshot_blockers = []
    for index, defect in enumerate(snapshot["open_defects"]):
        _require(type(defect) is dict
                 and type(defect.get("issue_number")) is int
                 and type(defect.get("release_blocker")) is bool
                 and type(defect.get("evidence_paths")) is list,
                 f"candidate defect snapshot item {index} changed")
        expected_evidence_paths.update(defect["evidence_paths"])
        if defect["release_blocker"]:
            snapshot_blockers.append(defect["issue_number"])
    _require(defects == {
        "open_count": len(snapshot["open_defects"]),
        "open_release_blockers": snapshot_blockers,
        "snapshot_at_utc": snapshot_at,
    }, "release-readiness defect summary does not match candidate")

    guide_checks = _list(
        manifest_document.get("guide_checks"),
        "candidate release-readiness guide checks",
    )
    guide_summaries = []
    heading_count = 0
    for index, guide in enumerate(guide_checks):
        _require(type(guide) is dict and set(guide) == {
            "guide_id", "path", "required_headings"
        }, f"candidate release-readiness guide {index} changed")
        path = guide["path"]
        headings = _list(
            guide["required_headings"], f"candidate readiness guide {index} headings"
        )
        _require(path in candidate_files and bool(headings)
                 and all(type(item) is str for item in headings),
                 f"candidate release-readiness guide {index} is unavailable")
        try:
            lines = candidate_files[path].decode("utf-8").splitlines()
        except UnicodeError as exc:
            raise ReleaseCandidatePacketError(
                f"candidate release-readiness guide is not UTF-8: {path}"
            ) from exc
        position = -1
        for heading in headings:
            try:
                position = lines.index(heading, position + 1)
            except ValueError as exc:
                raise ReleaseCandidatePacketError(
                    f"candidate release-readiness guide lacks heading: {heading}"
                ) from exc
        expected_evidence_paths.add(path)
        heading_count += len(headings)
        guide_summaries.append({
            "guide_id": guide["guide_id"],
            "heading_count": len(headings),
            "path": path,
        })
    _require(record["guides"] == {
        "guide_count": len(guide_checks),
        "required_heading_count": heading_count,
        "summaries": guide_summaries,
    }, "release-readiness guide summary does not match candidate")

    review = manifest_document.get("release_review")
    _require(type(review) is dict
             and review.get("human_acceptance") == "not_granted"
             and review.get("m4_decision") == "pending"
             and review.get("m5_decision") == "pending"
             and review.get("open_release_blockers") == blockers
             and review.get("pending_human_evidence")
             == list(PENDING_HUMAN_EVIDENCE)
             and record["pending_human_evidence"]
             == list(PENDING_HUMAN_EVIDENCE),
             "release-readiness pending review inputs changed")

    evidence = _list(record["evidence_files"], "release-readiness evidence files")
    identities = {}
    for index, item in enumerate(evidence):
        _require(type(item) is dict and set(item) == {
            "path", "byte_count", "sha256"
        }, f"release-readiness evidence identity {index} changed")
        path = _safe_name(
            item["path"], f"release-readiness evidence identity {index}.path"
        )
        _require(path not in identities,
                 f"duplicate release-readiness evidence identity: {path}")
        _require(type(item["byte_count"]) is int and item["byte_count"] > 0
                 and type(item["sha256"]) is str
                 and _SHA256.fullmatch(item["sha256"]) is not None,
                 f"release-readiness evidence identity {index} is invalid")
        identities[path] = item
    _require(list(identities) == sorted(expected_evidence_paths),
             "release-readiness evidence inventory does not match candidate")
    for path, content in candidate_files.items():
        item = identities.get(path)
        _require(type(item) is dict
                 and item.get("byte_count") == len(content)
                 and item.get("sha256") == sha256(content).hexdigest(),
                 f"release-readiness identity is missing or changed: {path}")
    return [f"readiness:{item}" for item in blockers]


def _candidate_file_bytes() -> dict[str, bytes]:
    result = {}
    for relative in CANDIDATE_FILES:
        result[relative] = _read_regular(
            ROOT / relative, f"candidate review file {relative}"
        )
    return result


def _workspace_file_bytes(root: Path) -> dict[str, bytes]:
    _require(not root.is_symlink() and root.is_dir(),
             "operator acceptance workspace must be a regular directory")
    _outside_checkout(root, "operator acceptance workspace")
    _require(not _has_symlink_ancestor(root),
             "operator acceptance workspace cannot use symbolic links")
    files: dict[str, bytes] = {}
    total = 0
    try:
        entries = sorted(root.rglob("*"), key=lambda item: item.as_posix())
    except OSError as exc:
        raise ReleaseCandidatePacketError(
            "operator acceptance workspace is unavailable"
        ) from exc
    for entry in entries:
        relative = entry.relative_to(root).as_posix()
        _safe_name(relative, "operator acceptance workspace path")
        _require(not entry.is_symlink(),
                 "operator acceptance workspace contains a symbolic link")
        if entry.is_dir():
            continue
        content = _read_regular(
            entry, f"operator acceptance workspace file {relative}"
        )
        files[relative] = content
        total += len(content)
        _require(len(files) <= MAX_PACKET_FILES
                 and total <= MAX_PACKET_CONTENT_BYTES,
                 "operator acceptance workspace exceeds packet bounds")
    _require(bool(files), "operator acceptance workspace is empty")
    return files


def _acceptance_script(candidate_commit: str) -> bytes:
    return f"""# Chimera M4 acceptance script

**NOT PERFORMED.** This script is bound to candidate `{candidate_commit}` and contains no
human observations, M4 permission, M5 acceptance, merge authorization or release decision.

## Preconditions

- [ ] Use a trusted local host with no sensitive data and the exact clean candidate above.
- [ ] Use Python 3.11 or 3.12; record OS, Python, browser and assistive technology versions.
- [ ] Inspect this packet with `python -m examples.release_candidate_packet inspect PACKET`.
- [ ] Extract with the same command's `--extract-to NEW_DIRECTORY` option; do not use a
      directory that already exists or contains user data.

## Engineering verification

- [ ] From the exact checkout, run `python -m unittest discover -s tests -v` and
      `scripts/verify_clean_install.sh`; link the exact CI run and record actual results.
- [ ] Review `assessments/release-performance.json`; confirm every target result is passed
      and treat it only as a synthetic local regression budget.
- [ ] Review `assessments/release-threat-model.json`; confirm there are no unresolved
      `must_fix_before_m4` items and explicitly review residual risks/boundary assumptions.
- [ ] Review `assessments/release-readiness.json`; refresh the dated GitHub defect snapshot
      immediately before disposition and confirm requirement/guide coverage remains complete.
- [ ] Review `operator-acceptance/acceptance-preparation.json`; confirm eight P345 controls
      passed while human observations remain `not_performed` and phase disposition pending.

## Operator validation

- [ ] Start `python -m chimera.cli serve-dashboard EXTRACTED_PACKET/operator-acceptance/runs
      --port 8765` from the exact checkout and complete the guided operator worksheet.
- [ ] Inspect PASS, natural FAIL, synthetic FAIL, malformed-input refusal, missing evidence,
      completed resume, report/handoff agreement and downloaded handoff reinspection.
- [ ] Record actual keyboard, desktop-browser, physical-device, screen-reader/WCAG and
      operator-usability observations. Open defects for unresolved findings.
- [ ] Confirm limitations, exclusions and remaining noncritical issues are understandable.

## Decision record — intentionally blank

- Reviewer and method:
- Review date/time and timezone:
- Exact candidate and CI links:
- Checklist actual results:
- Residual-risk disposition:
- Open defects, severity, owner and due date:
- M4 decision: pending / approve / approve with conditions / request changes / defer
- Conditions, owner and due date:
- Actual response (verbatim):
- M5 product acceptance: pending; M4 does not grant M5 acceptance
""".encode("utf-8")


def _source_record_summary(path: str, content: bytes, status: str) -> dict:
    result = _identity(path, content)
    result["status"] = status
    return result


def _manifest(candidate_commit: str, generated_at_utc: str,
              files: dict[str, bytes], source_records: dict,
              release_blockers: list[str]) -> dict:
    checks = [
        {"id": "PACKET-001", "status": "passed",
         "description": "all source records identify the exact candidate"},
        {"id": "PACKET-002", "status": "passed",
         "description": "operator evidence is complete while human observations remain pending"},
        {"id": "PACKET-003",
         "status": "blocked" if release_blockers else "passed",
         "description": "performance, threat and readiness release controls are explicit"},
        {"id": "PACKET-004", "status": "passed",
         "description": "candidate review guides and manifests have exact identities"},
        {"id": "PACKET-005", "status": "passed",
         "description": "the bounded archive indexes every non-manifest member"},
        {"id": "PACKET-006", "status": "passed",
         "description": "M4, M5 and human acceptance remain explicitly pending"},
    ]
    return {
        "schema_version": 1,
        "record_type": "chimera.release-candidate-evidence-packet",
        "packet_id": PACKET_ID,
        "candidate_commit_sha": candidate_commit,
        "candidate_checks": {
            "before_assembly": "matched_clean_head",
            "before_publication": "matched_clean_head",
        },
        "generated_at_utc": generated_at_utc,
        "files": [_identity(path, files[path]) for path in sorted(files)],
        "source_records": source_records,
        "candidate_review_files": [
            f"candidate/{path}" for path in CANDIDATE_FILES
        ],
        "checks": checks,
        "release_blockers": release_blockers,
        "status": ("blocked_by_release_controls" if release_blockers
                   else "packet_complete_for_m4_review"),
        "m4_decision": "pending",
        "m5_decision": "pending",
        "human_acceptance": "not_granted",
        "scope": PACKET_SCOPE,
    }


def _zip_bytes(manifest: dict, files: dict[str, bytes]) -> bytes:
    destination = io.BytesIO()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in [(MANIFEST_NAME, _pretty(manifest)), *[
                (path, files[path]) for path in sorted(files)]]:
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = _REGULAR_MODE << 16
            archive.writestr(info, content)
    content = destination.getvalue()
    _require(0 < len(content) <= MAX_PACKET_FILE_BYTES,
             "release-candidate packet exceeds its file-size bound")
    return content


def _write_packet(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ReleaseCandidatePacketError(
            "release-candidate packet output already exists or is a symbolic link"
        ) from exc
    except OSError as exc:
        try:
            if path.is_file() and not path.is_symlink():
                path.unlink()
        except OSError:
            pass
        raise ReleaseCandidatePacketError(
            "cannot publish release-candidate packet"
        ) from exc


def _read_packet(path: Path) -> tuple[dict, dict[str, bytes]]:
    content = _read_regular(path, "release-candidate packet", MAX_PACKET_FILE_BYTES)
    members: dict[str, bytes] = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            _require(not archive.comment, "release-candidate packet has an archive comment")
            for info in archive.infolist():
                name = _safe_name(info.filename, "release-candidate packet member")
                _require(name not in members,
                         f"duplicate release-candidate packet member: {name}")
                _require(not info.is_dir(),
                         "release-candidate packet cannot contain directory entries")
                _require(info.date_time == FIXED_ZIP_TIME,
                         f"release-candidate packet timestamp changed: {name}")
                _require(info.compress_type == zipfile.ZIP_STORED
                         and info.compress_size == info.file_size,
                         f"release-candidate packet member must be stored: {name}")
                _require(info.flag_bits & 0x1 == 0,
                         f"release-candidate packet member is encrypted: {name}")
                _require(info.create_system == 3
                         and (info.external_attr >> 16) == _REGULAR_MODE,
                         f"release-candidate packet member mode changed: {name}")
                _require(not info.extra and not info.comment,
                         f"release-candidate packet member metadata changed: {name}")
                _require(0 < info.file_size <= MAX_SOURCE_FILE_BYTES,
                         f"release-candidate packet member size is invalid: {name}")
                data = archive.read(info)
                _require(len(data) == info.file_size,
                         f"release-candidate packet member is truncated: {name}")
                members[name] = data
                total += len(data)
                _require(len(members) <= MAX_PACKET_FILES
                         and total <= MAX_PACKET_CONTENT_BYTES,
                         "release-candidate packet content exceeds bounds")
            names = set(members)
            for name in names:
                parent = PurePosixPath(name).parent
                while parent != PurePosixPath("."):
                    _require(
                        parent.as_posix() not in names,
                        "release-candidate packet has a file/path-prefix collision",
                    )
                    parent = parent.parent
    except ReleaseCandidatePacketError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ReleaseCandidatePacketError(
            "release-candidate packet is not a valid bounded ZIP"
        ) from exc
    _require(MANIFEST_NAME in members,
             "release-candidate packet lacks its manifest")
    manifest = _load_json_bytes(
        members.pop(MANIFEST_NAME), "release-candidate packet manifest", style="pretty"
    )
    return manifest, members


def _validate_manifest_and_members(manifest: dict,
                                   members: dict[str, bytes]) -> dict:
    _object(manifest, MANIFEST_FIELDS, "release-candidate packet manifest")
    _require(type(manifest["schema_version"]) is int
             and manifest["schema_version"] == 1,
             "release-candidate packet schema version changed")
    _require(manifest["record_type"] == "chimera.release-candidate-evidence-packet"
             and manifest["packet_id"] == PACKET_ID,
             "release-candidate packet contract changed")
    candidate = manifest["candidate_commit_sha"]
    _require(type(candidate) is str and _COMMIT.fullmatch(candidate) is not None,
             "release-candidate packet has an invalid candidate SHA")
    packet_generated = _utc_timestamp(
        manifest["generated_at_utc"], "packet generated_at_utc"
    )
    candidate_checks = _object(
        manifest["candidate_checks"],
        {"before_assembly", "before_publication"},
        "packet candidate checks",
    )
    _require(set(candidate_checks.values()) == {"matched_clean_head"},
             "packet candidate checks are incomplete")
    identities = _list(manifest["files"], "packet file identities")
    _require(len(identities) == len(members),
             "packet file identity count does not match archive")
    seen = set()
    for index, item in enumerate(identities):
        _require(type(item) is dict and "path" in item,
                 f"packet file identity {index} is invalid")
        path = item["path"]
        _require(path in members and path not in seen,
                 f"packet file identity is missing or duplicate: {path}")
        _validate_identity(item, members[path], f"packet file identity {index}")
        seen.add(path)
    _require(seen == set(members), "packet archive has an unindexed member")
    _require(members.get(ACCEPTANCE_SCRIPT_NAME) == _acceptance_script(candidate),
             "M4 acceptance script changed or contains a completed response")
    workspace = {
        path.removeprefix("operator-acceptance/"): content
        for path, content in members.items()
        if path.startswith("operator-acceptance/")
    }
    acceptance = _validate_acceptance_workspace(workspace, candidate)
    candidate_files = {}
    for relative in CANDIDATE_FILES:
        packet_path = f"candidate/{relative}"
        _require(packet_path in members,
                 f"packet lacks candidate review file: {relative}")
        candidate_files[relative] = members[packet_path]
    performance_bytes = members.get(ASSESSMENT_NAMES["performance"])
    threat_bytes = members.get(ASSESSMENT_NAMES["threat_model"])
    readiness_bytes = members.get(ASSESSMENT_NAMES["readiness"])
    _require(all(type(item) is bytes for item in (
        performance_bytes, threat_bytes, readiness_bytes,
    )), "packet lacks one or more release assessments")
    performance = _load_json_bytes(
        performance_bytes, "performance record", style="compact"
    )
    threat = _load_json_bytes(threat_bytes, "threat-model record", style="pretty")
    readiness = _load_json_bytes(
        readiness_bytes, "release-readiness record", style="pretty"
    )
    expected_members = {
        ACCEPTANCE_SCRIPT_NAME,
        *ASSESSMENT_NAMES.values(),
        *(f"candidate/{path}" for path in CANDIDATE_FILES),
        *(f"operator-acceptance/{path}" for path in workspace),
    }
    _require(set(members) == expected_members,
             "release-candidate packet member inventory changed")
    packet_time = datetime.fromisoformat(packet_generated)
    for label, record in (
        ("operator acceptance", acceptance),
        ("performance", performance),
        ("threat-model", threat),
        ("release-readiness", readiness),
    ):
        source_generated = _utc_timestamp(
            record["generated_at_utc"], f"{label} generated_at_utc"
        )
        _require(datetime.fromisoformat(source_generated) <= packet_time,
                 f"{label} was generated after the packet")
    blockers = []
    blockers.extend(_validate_performance(performance, candidate))
    blockers.extend(_validate_threat(threat, candidate, candidate_files))
    blockers.extend(_validate_readiness(readiness, candidate, candidate_files))
    _require(manifest["release_blockers"] == blockers,
             "packet release-blocker summary is inconsistent")
    expected_status = ("blocked_by_release_controls" if blockers
                       else "packet_complete_for_m4_review")
    _require(manifest["status"] == expected_status,
             "packet aggregate status is inconsistent")
    _require(manifest["m4_decision"] == "pending"
             and manifest["m5_decision"] == "pending"
             and manifest["human_acceptance"] == "not_granted",
             "packet decisions/acceptance must remain pending")
    _require(manifest["scope"] == PACKET_SCOPE,
             "release-candidate packet scope changed")
    checks = _list(manifest["checks"], "packet checks")
    _require([item.get("id") if type(item) is dict else None for item in checks]
             == [f"PACKET-{number:03d}" for number in range(1, 7)],
             "packet check inventory changed")
    packet_003 = checks[2]
    _require(packet_003.get("status") == ("blocked" if blockers else "passed")
             and all(item.get("status") == "passed"
                     for index, item in enumerate(checks) if index != 2),
             "packet check statuses are inconsistent")
    source_records = _object(
        manifest["source_records"],
        {"operator_acceptance", "performance", "threat_model", "readiness"},
        "packet source records",
    )
    expected_sources = {
        "operator_acceptance": (
            "operator-acceptance/acceptance-preparation.json",
            workspace["acceptance-preparation.json"], acceptance["engineering_status"],
        ),
        "performance": (
            ASSESSMENT_NAMES["performance"], performance_bytes, performance["status"],
        ),
        "threat_model": (
            ASSESSMENT_NAMES["threat_model"], threat_bytes, threat["status"],
        ),
        "readiness": (
            ASSESSMENT_NAMES["readiness"], readiness_bytes, readiness["status"],
        ),
    }
    for key, (path, content, status_value) in expected_sources.items():
        item = source_records[key]
        _require(type(item) is dict and set(item) == {
            "path", "byte_count", "sha256", "status"
        }, f"packet source record fields changed: {key}")
        _validate_identity(
            {name: item[name] for name in ("path", "byte_count", "sha256")},
            content, f"packet source record {key}", path,
        )
        _require(item["status"] == status_value,
                 f"packet source status changed: {key}")
    _require(manifest["candidate_review_files"]
             == [f"candidate/{path}" for path in CANDIDATE_FILES],
             "packet candidate review-file inventory changed")
    return manifest


def inspect_packet(packet: str | Path) -> dict:
    """Inspect a packet without requiring its source checkout."""
    manifest, members = _read_packet(Path(packet))
    return _validate_manifest_and_members(manifest, members)


def assemble_packet(
    output: str | Path, *, candidate_commit: str,
    acceptance_workspace: str | Path, performance_record: str | Path,
    threat_record: str | Path, readiness_record: str | Path,
    generated_at_utc: str | None = None,
) -> dict:
    """Assemble existing exact-candidate records into one self-checking ZIP."""
    _validate_candidate_checkout(candidate_commit)
    target = Path(output)
    if target.is_symlink() or target.exists():
        raise ReleaseCandidatePacketError(
            "release-candidate packet output already exists or is a symbolic link"
        )
    if _has_symlink_ancestor(target.parent) or not target.parent.is_dir():
        raise ReleaseCandidatePacketError(
            "release-candidate packet output parent is unavailable"
        )
    resolved = _outside_checkout(target, "release-candidate packet output")
    generated = _generated_timestamp(generated_at_utc)
    workspace_files = _workspace_file_bytes(Path(acceptance_workspace))
    acceptance = _validate_acceptance_workspace(workspace_files, candidate_commit)
    candidate_files = _candidate_file_bytes()
    performance_content = _read_regular(
        Path(performance_record), "performance record"
    )
    threat_content = _read_regular(Path(threat_record), "threat-model record")
    readiness_content = _read_regular(
        Path(readiness_record), "release-readiness record"
    )
    performance = _load_json_bytes(
        performance_content, "performance record", style="compact"
    )
    threat = _load_json_bytes(threat_content, "threat-model record", style="pretty")
    readiness = _load_json_bytes(
        readiness_content, "release-readiness record", style="pretty"
    )
    blockers = []
    blockers.extend(_validate_performance(performance, candidate_commit))
    blockers.extend(_validate_threat(threat, candidate_commit, candidate_files))
    blockers.extend(_validate_readiness(readiness, candidate_commit, candidate_files))
    generated_time = datetime.fromisoformat(generated)
    for name, record in (
        ("operator acceptance", acceptance), ("performance", performance),
        ("threat-model", threat), ("release-readiness", readiness),
    ):
        source_time = datetime.fromisoformat(record["generated_at_utc"])
        _require(source_time <= generated_time,
                 f"{name} record cannot be newer than the packet")
    files = {
        f"operator-acceptance/{path}": content
        for path, content in workspace_files.items()
    }
    files.update({
        ASSESSMENT_NAMES["performance"]: performance_content,
        ASSESSMENT_NAMES["threat_model"]: threat_content,
        ASSESSMENT_NAMES["readiness"]: readiness_content,
        ACCEPTANCE_SCRIPT_NAME: _acceptance_script(candidate_commit),
    })
    files.update({
        f"candidate/{path}": content for path, content in candidate_files.items()
    })
    _require(len(files) + 1 <= MAX_PACKET_FILES
             and sum(len(content) for content in files.values())
             <= MAX_PACKET_CONTENT_BYTES,
             "release-candidate packet content exceeds bounds")
    source_records = {
        "operator_acceptance": _source_record_summary(
            "operator-acceptance/acceptance-preparation.json",
            workspace_files["acceptance-preparation.json"],
            acceptance["engineering_status"],
        ),
        "performance": _source_record_summary(
            ASSESSMENT_NAMES["performance"], performance_content,
            performance["status"],
        ),
        "threat_model": _source_record_summary(
            ASSESSMENT_NAMES["threat_model"], threat_content, threat["status"],
        ),
        "readiness": _source_record_summary(
            ASSESSMENT_NAMES["readiness"], readiness_content, readiness["status"],
        ),
    }
    manifest = _manifest(
        candidate_commit, generated, files, source_records, blockers
    )
    packet_content = _zip_bytes(manifest, files)
    _validate_candidate_checkout(candidate_commit)
    _write_packet(resolved, packet_content)
    try:
        inspected = inspect_packet(resolved)
    except BaseException:
        try:
            if resolved.is_file() and not resolved.is_symlink():
                resolved.unlink()
        except OSError:
            pass
        raise
    _require(inspected == manifest,
             "published release-candidate packet did not reopen identically")
    return manifest


def extract_packet(packet: str | Path, output: str | Path) -> dict:
    """Validate and safely extract a packet into a new outside-checkout directory."""
    manifest, members = _read_packet(Path(packet))
    manifest = _validate_manifest_and_members(manifest, members)
    target = Path(output)
    if target.is_symlink() or target.exists():
        raise ReleaseCandidatePacketError(
            "packet extraction output already exists or is a symbolic link"
        )
    if _has_symlink_ancestor(target.parent) or not target.parent.is_dir():
        raise ReleaseCandidatePacketError("packet extraction parent is unavailable")
    resolved = _outside_checkout(target, "packet extraction output")
    try:
        resolved.mkdir(mode=0o700)
    except (FileExistsError, OSError) as exc:
        raise ReleaseCandidatePacketError(
            "cannot initialize packet extraction output"
        ) from exc
    marker = resolved / ".PUBLISHING"
    try:
        marker.write_text(
            "Packet extraction incomplete; do not use this directory.\n",
            encoding="utf-8",
        )
        all_members = {MANIFEST_NAME: _pretty(manifest), **members}
        for name in sorted(all_members):
            destination = resolved.joinpath(*PurePosixPath(name).parts)
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(all_members[name])
        marker.unlink()
    except BaseException as exc:
        if isinstance(exc, ReleaseCandidatePacketError):
            raise
        raise ReleaseCandidatePacketError(
            "packet extraction is incomplete; .PUBLISHING remains"
        ) from exc
    return manifest


def _print_result(manifest: dict, packet: Path) -> int:
    for check in manifest["checks"]:
        label = "PASS" if check["status"] == "passed" else "BLOCKED"
        print(f"{label} {check['id']}: {check['description']}")
    print(f"candidate-commit: {manifest['candidate_commit_sha']}")
    print(f"packet-sha256: {sha256(packet.read_bytes()).hexdigest()}")
    print(f"release-candidate-packet: {packet.resolve(strict=False)}")
    print("M4 review packet only; M4/M5 decisions and human acceptance remain pending")
    return 0 if manifest["status"] == "packet_complete_for_m4_review" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="assemble or inspect Chimera's bounded M4 evidence packet"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="assemble an exact-candidate packet")
    build.add_argument("--candidate-commit", required=True)
    build.add_argument("--acceptance-workspace", type=Path, required=True)
    build.add_argument("--performance-record", type=Path, required=True)
    build.add_argument("--threat-record", type=Path, required=True)
    build.add_argument("--readiness-record", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    inspect = commands.add_parser("inspect", help="inspect and optionally extract a packet")
    inspect.add_argument("packet", type=Path)
    inspect.add_argument("--extract-to", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            manifest = assemble_packet(
                args.output,
                candidate_commit=args.candidate_commit,
                acceptance_workspace=args.acceptance_workspace,
                performance_record=args.performance_record,
                threat_record=args.threat_record,
                readiness_record=args.readiness_record,
            )
            packet = args.output
        else:
            manifest = inspect_packet(args.packet)
            if args.extract_to is not None:
                extract_packet(args.packet, args.extract_to)
                print(f"extracted-packet: {args.extract_to.resolve(strict=False)}")
            packet = args.packet
    except ReleaseCandidatePacketError as exc:
        print(f"chimera release candidate packet: {exc}", file=sys.stderr)
        return 2
    return _print_result(manifest, packet)


if __name__ == "__main__":
    raise SystemExit(main())
