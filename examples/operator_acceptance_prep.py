"""Prepare persistent P3/P4/P5 engineering evidence for an operator review.

This repository-level tool records automated controls and an empty observation
worksheet. It never records human observations or phase acceptance on their behalf.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from uuid import uuid4

from chimera import RequirementBindings, RunEvidence, VerificationReport
from chimera.dashboard import CompletedRunWorkspace, DashboardApp
from chimera.handoff import create_handoff_bundle, inspect_handoff_bundle
from chimera.operator import OperatorInputError, run_link_verification


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PORTABLE_ARTIFACTS = (
    "request.json", "evidence.json", "bindings.json", "report.json", "report.html",
)
_COMMIT = re.compile(r"[0-9a-f]{40}")


class AcceptancePreparationError(RuntimeError):
    """An exact, non-overwriting acceptance workspace could not be prepared."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptancePreparationError(message)


def _canonical(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ) + "\n").encode("utf-8")


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *arguments], cwd=ROOT, capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AcceptancePreparationError("Git checkout identity is unavailable") from exc


def _validate_candidate_checkout(candidate_commit: str) -> None:
    if type(candidate_commit) is not str or _COMMIT.fullmatch(candidate_commit) is None:
        raise AcceptancePreparationError(
            "candidate commit must be a full lowercase 40-character Git SHA"
        )
    head = _git("rev-parse", "HEAD")
    actual = head.stdout.strip()
    if (head.returncode != 0 or _COMMIT.fullmatch(actual) is None
            or actual != candidate_commit):
        raise AcceptancePreparationError(
            "candidate commit must equal the exact checked-out Git HEAD"
        )
    status = _git("status", "--porcelain", "--untracked-files=normal")
    if status.returncode != 0:
        raise AcceptancePreparationError("Git checkout status is unavailable")
    if status.stdout:
        raise AcceptancePreparationError(
            "acceptance preparation requires a clean checkout at the candidate commit"
        )


def _request(app: DashboardApp, path: str) -> dict:
    response: dict = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    response["body"] = b"".join(app({
        "REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": "",
    }, start_response))
    return response


def _artifact(path: Path, root: Path) -> dict:
    _require(not path.is_symlink() and path.is_file(),
             f"Acceptance artifact is unavailable: {path.name}")
    content = path.read_bytes()
    relative = path.relative_to(root).as_posix()
    relative_path = Path(relative)
    _require(not relative_path.is_absolute() and ".." not in relative_path.parts,
             "Acceptance artifact path is not safely relative")
    return {
        "path": relative,
        "bytes": len(content),
        "sha256": sha256(content).hexdigest(),
    }


def _all_run_artifacts(directory: Path, root: Path) -> list[dict]:
    try:
        entries = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise AcceptancePreparationError("Cannot inspect prepared run artifacts") from exc
    return [_artifact(item, root) for item in entries]


def _portable_identities(directory: Path) -> dict[str, str]:
    return {
        name: sha256((directory / name).read_bytes()).hexdigest()
        for name in PORTABLE_ARTIFACTS
    }


def _worksheet(candidate_commit: str) -> str:
    return f"""# P3/P4/P5 operator observation worksheet

**NOT PERFORMED.** This generated worksheet contains no human observations,
approval or phase disposition. Complete it only while reviewing the exact candidate.

- Candidate commit: `{candidate_commit}`
- Engineering preparation record: `acceptance-preparation.json`
- Reviewer:
- Review date/time and timezone:
- Operating system and desktop browser:
- Screen reader and version, if used:

## Guided operator journey

- [ ] Confirm `acceptance-preparation.json` reports eight passed engineering controls and
      `acceptance_status` remains `pending_human_observation`.
- [ ] From this exact checkout, start
      `python -m chimera.cli serve-dashboard <acceptance-output>/runs --port 8765` on the
      same computer. The loopback-only prototype is not reachable from a separate phone.
- [ ] Using only Tab, Shift+Tab and Enter, select FAIL, open the synthetic failure,
      return to FAIL, reopen it and download the audit handoff ZIP.
- [ ] Confirm COM-LINK-001 is FAIL, threshold is 3.0 dB, minimum is 2.0 dB and the
      failing sample is understandable.
- [ ] Run `python -m chimera.cli inspect-link <downloaded-zip>` from this exact checkout
      and compare its run ID/verdict with the dashboard and file handoff.
- [ ] Inspect the PASS and natural FAIL runs; confirm labels and the next action are
      understandable without developer assistance.
- [ ] Review the stored error text for all three malformed-input controls. If useful, rerun
      `python -m chimera.cli verify-link <acceptance-output>/inputs/CASE.csv`
      with `--threshold-db 3.0` and a new outside-checkout `--output`; confirm no run state.
- [ ] Inspect `controls/missing-evidence-report.json`; confirm COM-LINK-001 is
      `not_evaluated` and engineering detail is `unavailable`, never PASS.

## Actual observations — leave blank until personally performed

Keyboard-only journey:

Desktop browser diversity (browser/version and result):

Physical-device observation within the declared loopback boundary:

Screen-reader observation (for example NVDA/Windows or VoiceOver/macOS):

WCAG observations; this worksheet does not itself establish conformance:

Labels, navigation or instructions that were confusing:

Defects opened (ID, severity, owner and due date):

Assisted steps, if any:

## Phase disposition — pending until Leo responds

- P3 verification/validation: pending
- P4 verification/validation: pending
- P5 verification/validation: pending
- Decision: pending / approve / approve with conditions / request changes / defer
- Conditions, owner and due date:
- Actual response (verbatim) and response date/time:
"""


def _build_staging(stage: Path, candidate_commit: str,
                   generated_at_utc: str) -> dict:
    runs = stage / "runs"
    inputs = stage / "inputs"
    handoffs = stage / "handoffs"
    review_controls = stage / "controls"
    runs.mkdir()
    inputs.mkdir()
    handoffs.mkdir()
    review_controls.mkdir()

    passed = run_link_verification(
        FIXTURES / "link_margin_passed.csv", runs / "passing", threshold_db="3.0",
    )
    _require(passed.verdict == "pass", "Passing reference did not produce PASS")

    natural = run_link_verification(
        FIXTURES / "link_margin_failed.csv", runs / "natural-failure",
        threshold_db="3.0",
    )
    natural_report = json.loads(natural.report_json_path.read_text(encoding="utf-8"))
    natural_detail = natural_report["detail"]["link_margin"]
    _require(natural.verdict == "fail", "Natural failing reference did not produce FAIL")
    _require(natural_detail["threshold_db"] == "3.0",
             "Natural failure threshold changed")
    _require(natural_detail["minimum_link_margin_db"] == "2.0",
             "Natural failure minimum changed")
    _require(natural_detail["failing_samples"] == [{
        "sample_index": 2,
        "timestamp_utc": "2026-09-21T00:00:01+00:00",
        "link_margin_db": "2.0",
    }], "Natural failing-sample reference changed")

    synthetic = run_link_verification(
        FIXTURES / "link_margin_passed.csv", runs / "synthetic-failure",
        threshold_db="3.0", fault_plan_path=FIXTURES / "link_fault_plan.json",
    )
    synthetic_report = json.loads(
        synthetic.report_json_path.read_text(encoding="utf-8")
    )
    _require(synthetic.verdict == "fail", "Synthetic fault did not produce FAIL")
    _require(synthetic_report["detail"]["link_margin"] == natural_detail,
             "Synthetic and natural failure engineering results disagree")
    provenance = synthetic_report["provenance"]
    _require(provenance["synthetic"] is True,
             "Synthetic failure lost its source label")
    _require(len({passed.run_id, natural.run_id, synthetic.run_id}) == 3,
             "Prepared runs do not have unique identities")

    invalid_inputs = {
        "malformed-value": (FIXTURES / "link_margin_malformed.csv").read_bytes(),
        "missing-column": b"timestamp_utc\n2026-09-21T00:00:00+00:00\n",
        "invalid-unit": (b"timestamp_utc,link_margin_mw\n"
                         b"2026-09-21T00:00:00+00:00,4.0\n"),
    }
    malformed_results = []
    for name, content in invalid_inputs.items():
        source = inputs / f"{name}.csv"
        source.write_bytes(content)
        attempted_output = runs / name
        try:
            run_link_verification(source, attempted_output, threshold_db="3.0")
        except OperatorInputError as exc:
            error_text = str(exc)
            _require(error_text and len(error_text) <= 512 and "\n" not in error_text,
                     f"{name} error text is not bounded")
            _require(str(stage) not in error_text and str(ROOT) not in error_text,
                     f"{name} error text exposed a local path")
            malformed_results.append({
                "case": name,
                "exception": type(exc).__name__,
                "error": error_text,
                "output_created": attempted_output.exists(),
                "input": _artifact(source, stage),
            })
        else:
            raise AcceptancePreparationError(f"{name} telemetry was not rejected")
        _require(not attempted_output.exists(), f"{name} input created run state")

    evidence_time = generated_at_utc.replace("Z", "+00:00")
    unavailable_evidence = RunEvidence(json.dumps({
        "schema_version": 1,
        "run_id": str(uuid4()),
        "started_at": evidence_time,
        "finished_at": evidence_time,
        "tasks": [
            {"task_id": "ingest", "status": "failed", "value": None,
             "error": "Malformed input", "dependencies": []},
            {"task_id": "check", "status": "blocked", "value": None,
             "error": "Unsuccessful dependencies: ingest",
             "dependencies": ["ingest"]},
            {"task_id": "detail", "status": "blocked", "value": None,
             "error": "Unsuccessful dependencies: check",
             "dependencies": ["check"]},
        ],
    }))
    unavailable_report = VerificationReport.from_evidence(
        unavailable_evidence,
        RequirementBindings.from_mapping({"COM-LINK-001": "check"}),
        detail_task_id="detail",
    )
    unavailable_document = unavailable_report.to_dict()
    _require(unavailable_document["requirement"]["verdict"] == "not_evaluated",
             "Missing evidence invented a requirement verdict")
    _require(unavailable_document["detail"]["status"] == "unavailable",
             "Missing engineering detail was not explicitly unavailable")
    missing_json = review_controls / "missing-evidence-report.json"
    missing_html = review_controls / "missing-evidence-report.html"
    missing_json.write_text(unavailable_report.to_json() + "\n", encoding="utf-8")
    missing_html.write_text(unavailable_report.to_html(), encoding="utf-8")

    before_resume = _portable_identities(runs / "passing")
    resumed = run_link_verification(
        FIXTURES / "link_margin_passed.csv", runs / "passing",
        threshold_db="3.0", resume_run_id=passed.run_id,
    )
    after_resume = _portable_identities(runs / "passing")
    _require(resumed == passed, "Completed resume changed the public result")
    _require(after_resume == before_resume,
             "Completed resume changed portable evidence")

    bundle_a = handoffs / "synthetic-failure-a.zip"
    bundle_b = handoffs / "synthetic-failure-b.zip"
    bundle_manifest = create_handoff_bundle(runs / "synthetic-failure", bundle_a)
    repeated_manifest = create_handoff_bundle(runs / "synthetic-failure", bundle_b)
    _require(bundle_a.read_bytes() == bundle_b.read_bytes(),
             "Repeated handoff export changed bundle bytes")
    _require(inspect_handoff_bundle(bundle_a) == bundle_manifest,
             "Exported handoff did not reopen identically")
    _require(inspect_handoff_bundle(bundle_b) == repeated_manifest == bundle_manifest,
             "Repeated handoff manifest changed")
    _require(bundle_manifest["run_id"] == synthetic.run_id,
             "Handoff run identity changed")
    _require(bundle_manifest["requirement_id"] == "COM-LINK-001",
             "Handoff requirement identity changed")
    _require(bundle_manifest["verdict"] == "fail", "Handoff verdict changed")

    app = DashboardApp(CompletedRunWorkspace.open(runs))
    index = _request(app, "/api/v1/runs")
    _require(index["status"] == "200 OK", "Dashboard index was unavailable")
    index_document = json.loads(index["body"].decode("utf-8"))
    _require(index_document["run_count"] == 3,
             "Dashboard did not admit the three prepared runs")
    download = _request(app, f"/api/v1/runs/{synthetic.run_id}/handoff")
    _require(download["status"] == "200 OK", "Dashboard handoff was unavailable")
    expected_headers = {
        "Content-Type": "application/zip",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Disposition": (
            f'attachment; filename="chimera-{synthetic.run_id}-handoff.zip"'
        ),
    }
    for name, expected in expected_headers.items():
        _require(download["headers"].get(name) == expected,
                 f"Dashboard handoff header changed: {name}")
    _require(download["body"] == bundle_a.read_bytes(),
             "Dashboard handoff differs from file export")
    dashboard_bundle = handoffs / "dashboard-synthetic-failure.zip"
    dashboard_bundle.write_bytes(download["body"])
    _require(inspect_handoff_bundle(dashboard_bundle) == bundle_manifest,
             "Dashboard handoff did not reopen identically")

    controls = [
        {"control_id": "P345-1", "status": "passed",
         "summary": "Synthetic reference produced durable COM-LINK-001 PASS"},
        {"control_id": "P345-2", "status": "passed",
         "summary": "Natural sample 2 measured 2.0 dB, below the 3.0 dB threshold"},
        {"control_id": "P345-3", "status": "passed",
         "summary": "Synthetic fault retained provenance and matched the natural failure"},
        {"control_id": "P345-4", "status": "passed",
         "summary": "Three malformed telemetry shapes created no run state"},
        {"control_id": "P345-5", "status": "passed",
         "summary": "Missing evidence remained unavailable and not evaluated"},
        {"control_id": "P345-6", "status": "passed",
         "summary": "Completed resume preserved every portable artifact byte"},
        {"control_id": "P345-7", "status": "passed",
         "summary": "Repeated failed-run handoffs were byte-identical and reopened"},
        {"control_id": "P345-8", "status": "passed",
         "summary": "Dashboard download headers, bytes and reopened handoff agreed"},
    ]
    run_results = []
    for label, result in (
        ("passing", passed), ("natural-failure", natural),
        ("synthetic-failure", synthetic),
    ):
        run_results.append({
            "label": label,
            "run_id": result.run_id,
            "verdict": result.verdict,
            "report_sha256": result.report_sha256,
            "artifacts": _all_run_artifacts(runs / label, stage),
        })
    worksheet_path = stage / "operator-observations.md"
    worksheet_path.write_text(_worksheet(candidate_commit), encoding="utf-8")
    record = {
        "schema_version": 1,
        "record_type": "chimera.operator-acceptance-preparation",
        "candidate_commit_sha": candidate_commit,
        "candidate_checks": {
            "before_controls": "matched_clean_head",
            "before_publication": "matched_clean_head",
        },
        "generated_at_utc": generated_at_utc,
        "source_scope": "synthetic reference fixtures; no measured radio data",
        "source_identity_limit": (
            "Git SHA and content hashes are identities, not signatures, trusted build "
            "attestation, execution authorship or measurement authenticity"
        ),
        "engineering_status": "passed",
        "acceptance_status": "pending_human_observation",
        "controls": controls,
        "natural_reference": {
            "sample_index": 2,
            "link_margin_db": "2.0",
            "threshold_db": "3.0",
        },
        "synthetic_provenance": provenance,
        "malformed_inputs": malformed_results,
        "missing_evidence": {
            "requirement_verdict": "not_evaluated",
            "detail_status": "unavailable",
            "artifacts": [
                _artifact(missing_json, stage), _artifact(missing_html, stage),
            ],
        },
        "completed_resume": {
            "before_sha256": before_resume,
            "after_sha256": after_resume,
            "portable_artifacts_unchanged": before_resume == after_resume,
        },
        "runs": run_results,
        "handoff_manifest": bundle_manifest,
        "handoffs": [
            _artifact(bundle_a, stage), _artifact(bundle_b, stage),
            _artifact(dashboard_bundle, stage),
        ],
        "dashboard_download": {
            "matches_file_export": download["body"] == bundle_a.read_bytes(),
            "headers": expected_headers,
        },
        "human_observations": {
            "status": "not_performed",
            "keyboard_operator_journey": "not_performed",
            "desktop_browser_diversity": "not_performed",
            "physical_device": "not_performed",
            "screen_reader_wcag": "not_performed",
            "leo_validation": "not_performed",
            "phase_disposition": "pending",
        },
        "observation_worksheet": _artifact(worksheet_path, stage),
    }
    record_bytes = _canonical(record)
    record_path = stage / "acceptance-preparation.json"
    record_path.write_bytes(record_bytes)
    reopened_record = json.loads(
        record_path.read_text(encoding="utf-8")
    )
    _require(_canonical(reopened_record) == record_bytes,
             "Acceptance record did not reopen canonically")
    return record


def _publish_staging(stage: Path, target: Path) -> None:
    if target.is_symlink() or target.exists():
        raise AcceptancePreparationError(
            "Acceptance output already exists or is a symbolic link"
        )
    try:
        target.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise AcceptancePreparationError(
            "Acceptance output appeared during publication"
        ) from exc
    except OSError as exc:
        raise AcceptancePreparationError("Cannot publish acceptance output") from exc
    marker = target / ".PUBLISHING"
    try:
        with marker.open("x", encoding="utf-8") as stream:
            stream.write(
                "Publication is incomplete; do not use this directory as evidence.\n"
            )
    except OSError as exc:
        try:
            target.rmdir()
        except OSError:
            raise AcceptancePreparationError(
                "Acceptance publication initialization failed; reserved output remains"
            ) from exc
        raise AcceptancePreparationError(
            "Cannot initialize acceptance output publication"
        ) from exc
    try:
        for item in sorted(stage.iterdir(), key=lambda path: path.name):
            os.rename(item, target / item.name)
        stage.rmdir()
        marker.unlink()
    except OSError as exc:
        raise AcceptancePreparationError(
            "Acceptance output publication is incomplete; .PUBLISHING remains"
        ) from exc


def prepare_acceptance(output: str | Path, *, candidate_commit: str,
                       generated_at_utc: str | None = None) -> dict:
    """Prepare one review workspace from an exact clean commit without overwrite."""
    _validate_candidate_checkout(candidate_commit)
    requested = Path(output)
    if requested.is_symlink() or requested.exists():
        raise AcceptancePreparationError(
            "Acceptance output already exists or is a symbolic link"
        )
    if requested.parent.is_symlink() or not requested.parent.is_dir():
        raise AcceptancePreparationError("Acceptance output parent is unavailable")
    target = requested.resolve(strict=False)
    checkout = ROOT.resolve()
    if target == checkout or checkout in target.parents:
        raise AcceptancePreparationError(
            "Acceptance output must be outside the source checkout"
        )
    if target.is_symlink() or target.exists():
        raise AcceptancePreparationError(
            "Acceptance output already exists or is a symbolic link"
        )
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise AcceptancePreparationError("Acceptance output parent is unavailable")
    if generated_at_utc is None:
        generated_at_utc = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    try:
        parsed_time = datetime.fromisoformat(generated_at_utc)
    except (TypeError, ValueError) as exc:
        raise AcceptancePreparationError(
            "generated_at_utc must be canonical UTC timestamp text"
        ) from exc
    if (parsed_time.tzinfo != timezone.utc
            or parsed_time.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ) != generated_at_utc):
        raise AcceptancePreparationError(
            "generated_at_utc must be canonical UTC timestamp text"
        )

    stage = Path(tempfile.mkdtemp(
        dir=target.parent, prefix=f".{target.name}.staging-"
    ))
    stage.chmod(0o700)
    try:
        record = _build_staging(stage, candidate_commit, generated_at_utc)
        # Bind publication to the same clean source state checked before execution.
        _validate_candidate_checkout(candidate_commit)
        _publish_staging(stage, target)
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return record


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="prepare persistent synthetic P3/P4/P5 operator-review evidence"
    )
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    record = prepare_acceptance(
        args.output, candidate_commit=args.candidate_commit
    )
    for control in record["controls"]:
        print(f"PASS {control['control_id']}: {control['summary']}")
    output = args.output.resolve(strict=False)
    print(f"candidate-commit: {args.candidate_commit}")
    print(f"engineering-record: {output / 'acceptance-preparation.json'}")
    print(f"observation-worksheet: {output / 'operator-observations.md'}")
    print("Human observations and P3/P4/P5 acceptance remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
