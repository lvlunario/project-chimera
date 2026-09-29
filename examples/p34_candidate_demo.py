"""Executable P3/P4 candidate controls; engineering evidence, not acceptance."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from chimera import RequirementBindings, RunEvidence, VerificationReport
from chimera.dashboard import CompletedRunWorkspace, DashboardApp
from chimera.handoff import create_handoff_bundle, inspect_handoff_bundle
from chimera.operator import OperatorInputError, run_link_verification


FIXTURES = Path(__file__).resolve().parent / "fixtures"
PORTABLE_ARTIFACTS = (
    "request.json", "evidence.json", "bindings.json", "report.json", "report.html",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _request(app: DashboardApp, path: str) -> dict:
    response: dict = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    response["body"] = b"".join(app({
        "REQUEST_METHOD": "GET", "PATH_INFO": path,
    }, start_response))
    return response


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = root / "workspace"
        workspace.mkdir()

        passed = run_link_verification(
            FIXTURES / "link_margin_passed.csv", workspace / "passing",
            threshold_db="3.0",
        )
        _require(passed.verdict == "pass", "passing control did not pass")
        print("PASS P34-1: valid telemetry produced durable COM-LINK-001 PASS evidence")

        natural = run_link_verification(
            FIXTURES / "link_margin_failed.csv", workspace / "natural-failure",
            threshold_db="3.0",
        )
        natural_report = json.loads(natural.report_json_path.read_text(encoding="utf-8"))
        natural_link = natural_report["detail"]["link_margin"]
        _require(natural.verdict == "fail", "natural failing control did not fail")
        _require(natural_link["threshold_db"] == "3.0", "threshold identity changed")
        _require(natural_link["minimum_link_margin_db"] == "2.0",
                 "independently expected 2.0 dB minimum changed")
        _require(natural_link["failing_samples"] == [{
            "sample_index": 2, "timestamp_utc": "2026-09-21T00:00:01+00:00",
            "link_margin_db": "2.0",
        }], "natural failing sample differs from the reference calculation")
        print("PASS P34-2: reference failure matched sample 2 at 2.0 dB below 3.0 dB")

        failed = run_link_verification(
            FIXTURES / "link_margin_passed.csv", workspace / "synthetic-failure",
            threshold_db="3.0", fault_plan_path=FIXTURES / "link_fault_plan.json",
        )
        repeated = run_link_verification(
            FIXTURES / "link_margin_passed.csv", workspace / "synthetic-repeat",
            threshold_db="3.0", fault_plan_path=FIXTURES / "link_fault_plan.json",
        )
        _require(failed.verdict == "fail", "synthetic fault control did not fail")
        failed_report = json.loads(failed.report_json_path.read_text(encoding="utf-8"))
        repeated_report = json.loads(repeated.report_json_path.read_text(encoding="utf-8"))
        for field in ("requirement", "detail", "provenance"):
            _require(failed_report[field] == repeated_report[field],
                     f"repeated fault changed report {field}")
        _require(failed_report["requirement"] == {
            "requirement_id": "COM-LINK-001", "task_id": "check",
            "verdict": "fail", "reason": "Check returned False",
        }, "failed requirement trace changed")
        _require(failed_report["provenance"]["synthetic"] is True,
                 "synthetic label is absent from the failed report")
        _require(failed_report["provenance"]["procedure"]
                 == "chimera.synthetic.sample-replacement-v1",
                 "fault procedure version changed")
        _require(failed_report["detail"]["link_margin"] == natural_link,
                 "synthetic engineering outcome differs from reference failure")
        _require("2.0" in failed.report_html_path.read_text(encoding="utf-8"),
                 "HTML omitted the failing value")
        print("PASS P34-3: repeated fault preserved procedure, provenance and failed outcome")

        invalid_inputs = {
            "malformed-value": (FIXTURES / "link_margin_malformed.csv").read_bytes(),
            "missing-column": b"timestamp_utc\n2026-09-21T00:00:00+00:00\n",
            "invalid-unit": (b"timestamp_utc,link_margin_mw\n"
                             b"2026-09-21T00:00:00+00:00,4.0\n"),
        }
        for name, content in invalid_inputs.items():
            invalid_source = root / f"{name}.csv"
            invalid_source.write_bytes(content)
            invalid_output = workspace / name
            try:
                run_link_verification(
                    invalid_source, invalid_output, threshold_db="3.0",
                )
            except OperatorInputError:
                pass
            else:
                raise RuntimeError(f"{name} telemetry was not rejected")
            _require(not invalid_output.exists(), f"{name} input created output state")
        print("PASS P34-4: malformed value, missing column and invalid unit created no run")

        now = datetime.now(timezone.utc).isoformat()
        unavailable_evidence = RunEvidence(json.dumps({
            "schema_version": 1, "run_id": str(uuid4()),
            "started_at": now, "finished_at": now, "tasks": [
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
        unavailable = VerificationReport.from_evidence(
            unavailable_evidence,
            RequirementBindings.from_mapping({"COM-LINK-001": "check"}),
            detail_task_id="detail",
        ).to_dict()
        _require(unavailable["requirement"]["verdict"] == "not_evaluated",
                 "missing evidence invented a verdict")
        _require(unavailable["detail"]["status"] == "unavailable",
                 "missing detail was not explicit")
        print("PASS P34-5: missing evidence remained unavailable and not evaluated")

        before = {
            name: (workspace / "passing" / name).read_bytes()
            for name in PORTABLE_ARTIFACTS
        }
        resumed = run_link_verification(
            FIXTURES / "link_margin_passed.csv", workspace / "passing",
            threshold_db="3.0", resume_run_id=passed.run_id,
        )
        after = {
            name: (workspace / "passing" / name).read_bytes()
            for name in PORTABLE_ARTIFACTS
        }
        _require(resumed == passed, "completed-run resume changed the public result")
        _require(after == before, "completed-run resume changed portable evidence")
        print("PASS P34-6: completed-run resume preserved the sealed portable evidence")

        bundle = root / "failed-handoff.zip"
        manifest = create_handoff_bundle(workspace / "synthetic-failure", bundle)
        inspected = inspect_handoff_bundle(bundle)
        _require(inspected == manifest, "exported handoff did not inspect identically")
        _require(inspected["run_id"] == failed.run_id, "handoff run identity changed")
        _require(inspected["requirement_id"] == "COM-LINK-001",
                 "handoff requirement identity changed")
        _require(inspected["verdict"] == "fail", "handoff verdict changed")
        print("PASS P34-7: failed requirement handoff reopened with exact identity and verdict")

        app = DashboardApp(CompletedRunWorkspace.open(workspace))
        index = _request(app, "/api/v1/runs")
        _require(index["status"] == "200 OK", "dashboard index was unavailable")
        download = _request(app, f"/api/v1/runs/{failed.run_id}/handoff")
        _require(download["status"] == "200 OK", "dashboard handoff was unavailable")
        _require(download["body"] == bundle.read_bytes(),
                 "dashboard handoff differs from file export")
        downloaded = root / "downloaded-handoff.zip"
        downloaded.write_bytes(download["body"])
        _require(inspect_handoff_bundle(downloaded) == manifest,
                 "downloaded handoff did not reopen identically")
        print("PASS P34-8: dashboard downloaded the exact independently inspectable handoff")

    print("P3/P4 engineering candidate controls passed; Leo walkthrough and acceptance remain open")


if __name__ == "__main__":
    main()
