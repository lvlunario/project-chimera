#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/chimera-clean-install.XXXXXXXX")
trap 'rm -rf "$WORK"' EXIT

python - <<'PY'
import re
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Clean-install verification requires Python 3.11+")
try:
    import setuptools
except ImportError as exc:
    raise SystemExit("Offline wheel build requires local setuptools>=77") from exc
match = re.match(r"(\d+)", setuptools.__version__)
if match is None or int(match.group(1)) < 77:
    raise SystemExit(
        f"Offline wheel build requires local setuptools>=77; found {setuptools.__version__}"
    )
print(f"build-backend: setuptools {setuptools.__version__}")
PY

mkdir -p "$WORK/source" "$WORK/wheel" "$WORK/outside"
cp "$ROOT/pyproject.toml" "$ROOT/README.md" "$ROOT/LICENSE" "$WORK/source/"
cp -R "$ROOT/chimera" "$WORK/source/"
find "$WORK/source" -type d -name __pycache__ -prune -exec rm -rf {} +

python -m pip wheel \
  --disable-pip-version-check \
  --no-deps \
  --no-build-isolation \
  --wheel-dir "$WORK/wheel" \
  "$WORK/source"

WHEELS=("$WORK"/wheel/*.whl)
if [[ ${#WHEELS[@]} -ne 1 ]]; then
  echo "Expected one wheel, found ${#WHEELS[@]}" >&2
  exit 1
fi

python -m venv "$WORK/venv"
"$WORK/venv/bin/python" -m pip install \
  --disable-pip-version-check \
  --no-index \
  --no-deps \
  "${WHEELS[0]}"

cd "$WORK/outside"
CHIMERA_SOURCE_ROOT="$ROOT" "$WORK/venv/bin/python" - <<'PY'
from importlib.metadata import distribution, version
from pathlib import Path
import os

import chimera
from chimera import RequirementBindings, RunEvidence, Task, assess_requirements, run_with_evidence

source_root = Path(os.environ["CHIMERA_SOURCE_ROOT"]).resolve()
module_path = Path(chimera.__file__).resolve()
if module_path.is_relative_to(source_root):
    raise SystemExit(f"Source checkout leaked into clean import: {module_path}")
if version("project-chimera") != "0.1.0.dev0":
    raise SystemExit("Installed distribution version mismatch")
metadata = distribution("project-chimera").metadata
if metadata["Requires-Python"] != ">=3.11":
    raise SystemExit("Installed Python requirement mismatch")
if list(distribution("project-chimera").requires or []):
    raise SystemExit("Unexpected runtime dependency")

evidence = run_with_evidence([Task("installed-api", lambda: "available")])
reopened = RunEvidence.from_json(evidence.to_json())
if reopened.to_dict()["tasks"][0]["value"] != "available":
    raise SystemExit("Installed public API round trip failed")
print(f"installed-version: {version('project-chimera')}")
print(f"installed-module: {module_path}")
print("installed-api: evidence round trip passed")
checks = run_with_evidence([Task("boolean-check", lambda: False)])
bindings = RequirementBindings.from_mapping({"R1": "boolean-check"})
reopened_bindings = RequirementBindings.from_json(bindings.to_json())
assessment = assess_requirements(RunEvidence.from_json(checks.to_json()), reopened_bindings)
if assessment.outcomes[0].verdict != "fail" or assessment.all_passed:
    raise SystemExit("Installed requirement verdict classification failed")
if assessment.bindings_sha256 != bindings.sha256:
    raise SystemExit("Installed binding identity mismatch")
print("installed-verdicts: failed requirement and binding identity preserved after reload")
from chimera import EvidenceStore
import tempfile
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory, "installed.sqlite")
    with EvidenceStore(path) as store:
        store.save(checks, bindings)
    with EvidenceStore(path) as store:
        restored = assess_requirements(*store.load(assessment.run_id, bindings.sha256))
    if restored != assessment:
        raise SystemExit("Installed storage reopen changed assessment")
print("installed-storage: immutable run/binding reopen passed")
from chimera import DatabaseOwnership, OwnershipBusy
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory, "ownership.sqlite")
    with EvidenceStore(path):
        pass
    with DatabaseOwnership(path) as owner:
        owner.check()
        try:
            with DatabaseOwnership(path):
                raise SystemExit("Installed ownership admitted a second owner")
        except OwnershipBusy:
            pass
    with DatabaseOwnership(path) as owner:
        owner.check()
print("installed-ownership: exclusion and release passed (Linux)")
from chimera import (JournalCommitUncertain, JournalPlan, JournalStorageUnavailable,
                     JournalTask, export_journal_evidence, inspect_interrupted,
                     resume_journaled, run_journaled)
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory, "journal.sqlite")
    result = run_journaled(
        path,
        [JournalTask("check", lambda: False, "installed:check:v1")],
    )
    if result.state != "completed" or result.tasks[0].value is not False:
        raise SystemExit("Installed journal did not preserve boolean result")
    plan = JournalPlan.from_tasks(
        [JournalTask("check", lambda: (_ for _ in ()).throw(
            SystemExit("inspection executed callback")), "installed:check:v1")]
    )
    if inspect_interrupted(path, result.run_id, plan) != result:
        raise SystemExit("Installed completed-journal inspection changed the result")
    if resume_journaled(path, result.run_id, [
            JournalTask("check", lambda: (_ for _ in ()).throw(
                SystemExit("completed resume executed callback")), "installed:check:v1")
    ]) != result:
        raise SystemExit("Installed completed resume changed the result")
    exported = export_journal_evidence(path, result.run_id, plan)
    if exported.to_dict()["tasks"][0]["value"] is not False:
        raise SystemExit("Installed journal export changed the committed result")
    export_bindings = RequirementBindings.from_mapping({"R-INSTALLED": "check"})
    export_path = Path(directory, "export.sqlite")
    with EvidenceStore(export_path) as store:
        store.save(exported, export_bindings)
    with EvidenceStore(export_path) as store:
        export_assessment = assess_requirements(
            *store.load(result.run_id, export_bindings.sha256)
        )
    if export_assessment.outcomes[0].verdict != "fail":
        raise SystemExit("Installed journal export/storage verdict changed")
print("installed-journal: durable result, callback-free inspection/resume passed")
print("installed-export: journal evidence/storage/verdict handoff passed")
if not issubclass(JournalCommitUncertain, RuntimeError):
    raise SystemExit("Installed uncertain-commit exception is unavailable")
if not issubclass(JournalStorageUnavailable, RuntimeError):
    raise SystemExit("Installed storage-unavailable exception is unavailable")
print("installed-reconciliation: public fail-closed exceptions available")
from chimera import (LinkMarginReport, evaluate_link_margin, identify_link_csv,
                     link_margin_passes, load_link_csv)
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory, "link.csv")
    path.write_text(
        "timestamp_utc,link_margin_db\n"
        "2026-09-21T00:00:00Z,4.0\n"
        "2026-09-21T00:00:01Z,2.0\n",
        encoding="utf-8",
    )
    identity = identify_link_csv(path)
    telemetry = load_link_csv(path, expected_sha256=identity.sha256)
    if link_margin_passes(telemetry, 3.0) is not False:
        raise SystemExit("Installed telemetry threshold verdict changed")
    if telemetry.manifest()["input_sha256"] != identity.sha256:
        raise SystemExit("Installed telemetry manifest lost input identity")
    report = evaluate_link_margin(telemetry, 3.0)
    reopened_report = LinkMarginReport.from_json(report.to_json())
    if reopened_report != report or reopened_report.to_dict()["failure_count"] != 1:
        raise SystemExit("Installed link-margin report round trip failed")
    if reopened_report.to_dict()["failing_samples"][0]["link_margin_db"] != "2.0":
        raise SystemExit("Installed link-margin report lost failing sample")
print("installed-telemetry: strict CSV identity and failed threshold passed")
print("installed-link-report: canonical failing-sample round trip passed")
from chimera import FaultPlan, fault_manifest, inject_link_csv, parse_link_csv
source = b"timestamp_utc,link_margin_db\n2026-09-22T00:00:00Z,4.0\n"
fault = FaultPlan.from_json(
    '{"schema_version":1,"model":"sample-replacement-v1",'
    '"replacements":[{"sample_index":1,"link_margin_db":"2.0"}]}'
)
derived = inject_link_csv(source, fault)
manifest = fault_manifest(source, fault)
if derived != inject_link_csv(source, FaultPlan.from_json(fault.to_json())):
    raise SystemExit("Installed fault repeatability failed")
if evaluate_link_margin(parse_link_csv(derived), 3).passed:
    raise SystemExit("Installed injected fault did not fail the requirement")
if manifest["derived"]["input_sha256"] != parse_link_csv(derived).input_sha256:
    raise SystemExit("Installed fault provenance lost derived identity")
if manifest["fault_plan_sha256"] != fault.sha256 or manifest["synthetic"] is not True:
    raise SystemExit("Installed fault provenance lost plan or synthetic label")
print("installed-faults: deterministic replacement and provenance passed")
PY

DEMO_OUTPUT=$("$WORK/venv/bin/chimera-demo")
printf '%s\n' "$DEMO_OUTPUT"
grep -q '^link-check: failed' <<<"$DEMO_OUTPUT"
grep -q '^report: blocked' <<<"$DEMO_OUTPUT"

set +e
CLI_OUTPUT=$("$WORK/venv/bin/chimera" run "$ROOT/examples/workflow.json" --evidence "$WORK/outside/cli-run.json")
CLI_STATUS=$?
set -e
printf '%s\n' "$CLI_OUTPUT"
if [[ $CLI_STATUS -ne 1 ]]; then
  echo "Expected synthetic CLI workflow to exit 1; found $CLI_STATUS" >&2
  exit 1
fi
grep -q '^link-check: failed' <<<"$CLI_OUTPUT"
grep -q '^report: blocked' <<<"$CLI_OUTPUT"
"$WORK/venv/bin/python" - "$WORK/outside/cli-run.json" <<'PY'
from pathlib import Path
import sys

from chimera import RunEvidence

evidence = RunEvidence.from_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
if len(evidence.to_dict()["tasks"]) != 4:
    raise SystemExit("Installed CLI evidence task count mismatch")
print("installed-cli: workflow and evidence passed")
PY
printf '%s\n' "clean-install: passed (temporary environment removed on exit)"
