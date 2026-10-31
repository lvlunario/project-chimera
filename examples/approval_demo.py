"""Reproducible P1 synthetic approval controls; not PM acceptance."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from chimera import RequirementBindings, RunEvidence, assess_requirements
from chimera.cli import main as cli_main


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    with TemporaryDirectory(prefix="chimera-approval-") as directory:
        root = Path(directory)

        def execute(name, tasks, expected):
            workflow = root / f"{name}.workflow.json"
            evidence_path = root / f"{name}.run.json"
            workflow.write_text(json.dumps({"schema_version": 1, "tasks": tasks}),
                                encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = cli_main(["run", str(workflow), "--evidence", str(evidence_path)])
            require(code == expected, f"{name}: expected exit {expected}, got {code}")
            return workflow, evidence_path

        check = {"id": "check", "operation": "emit", "value": True}
        _, passing = execute("passing", [check], 0)
        bindings = RequirementBindings.from_mapping({"CONTROL": "check"})
        restored = RunEvidence.from_json(passing.read_text(encoding="utf-8"))
        require(assess_requirements(restored, bindings).all_passed, "passing verdict")
        print("PASS: execution exit 0; selected requirement pass")

        workflow, failed = execute("execution-error", [
            {"id": "check", "operation": "fail", "message": "synthetic fault"},
            {"id": "handoff", "operation": "emit", "value": "ready",
             "dependencies": ["check"]},
            {"id": "health", "operation": "emit", "value": True},
        ], 1)
        original = failed.read_bytes()
        restored = RunEvidence.from_json(original.decode("utf-8"))
        statuses = {task["task_id"]: task["status"] for task in restored.to_dict()["tasks"]}
        require(statuses == {"check": "failed", "health": "succeeded", "handoff": "blocked"},
                "execution error propagation")
        print("PASS: execution exit 1; failed/blocked/independent evidence preserved")

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            code = cli_main(["run", str(workflow), "--evidence", str(failed)])
        require(code == 3 and failed.read_bytes() == original, "existing output changed")
        print("PASS: existing output exit 3; original bytes unchanged")

        _, invalid = execute("invalid-graph", [dict(check, dependencies=["absent"])], 2)
        require(not invalid.exists(), "invalid graph wrote run evidence")
        print("PASS: invalid graph exit 2; no completed evidence")

        _, finding = execute("requirement-failure", [dict(check, value=False),
            {"id": "handoff", "operation": "emit", "value": "ready",
             "dependencies": ["check"]}], 0)
        binding_path = root / "bindings.json"
        binding_path.write_text(bindings.to_json(), encoding="utf-8")
        reopened_bindings = RequirementBindings.from_json(binding_path.read_text(encoding="utf-8"))
        reopened = RunEvidence.from_json(finding.read_text(encoding="utf-8"))
        before = assess_requirements(reopened, reopened_bindings)
        again = RunEvidence.from_json(reopened.to_json())
        require(assess_requirements(again, reopened_bindings) == before, "replay changed assessment")
        require(before.outcomes[0].verdict == "fail" and not before.all_passed,
                "false check incorrectly passed")
        require(before.bindings_sha256 == bindings.sha256, "binding identity changed")
        require(all(task["status"] == "succeeded" for task in again.to_dict()["tasks"]),
                "finding blocked handoff")
        print("PASS: execution exit 0 but requirement fail; handoff succeeded")
        print("PASS: run and binding reload reproduce assessment without CLI execution")
    print("P1 walkthrough controls passed; temporary artifacts removed; PM acceptance pending")


if __name__ == "__main__":
    main()
