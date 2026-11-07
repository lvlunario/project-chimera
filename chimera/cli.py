"""Command-line operator boundary for declarative local workflows."""
import argparse
from pathlib import Path
import sys

from .evidence import EvidenceError, run_with_evidence
from .api import OperatorAPIError, serve_completed_run
from .dashboard import DashboardError, serve_dashboard
from .handoff import HandoffError, create_handoff_bundle, inspect_handoff_bundle
from .operator import (OperatorError, OperatorInputError, OperatorOutputError,
                       run_link_verification)
from .workflow import WorkflowError, load_workflow


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chimera")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="run a declarative JSON workflow")
    run_parser.add_argument("workflow", type=Path)
    run_parser.add_argument("--evidence", type=Path, required=True)
    link_parser = commands.add_parser(
        "verify-link", help="run or resume durable communications verification"
    )
    link_parser.add_argument("source", type=Path)
    link_parser.add_argument("--output", type=Path, required=True)
    link_parser.add_argument("--threshold-db", required=True)
    link_parser.add_argument("--fault-plan", type=Path)
    link_parser.add_argument("--resume-run-id")
    serve_parser = commands.add_parser(
        "serve-link", help="serve one completed link run on IPv4 loopback"
    )
    serve_parser.add_argument("output", type=Path)
    serve_parser.add_argument("--port", type=int, default=8765)
    dashboard_parser = commands.add_parser(
        "serve-dashboard", help="serve validated completed runs on IPv4 loopback"
    )
    dashboard_parser.add_argument("workspace", type=Path)
    dashboard_parser.add_argument("--port", type=int, default=8765)
    export_parser = commands.add_parser(
        "export-link", help="export one validated completed run as a handoff bundle"
    )
    export_parser.add_argument("run", type=Path)
    export_parser.add_argument("--output", type=Path, required=True)
    inspect_parser = commands.add_parser(
        "inspect-link", help="validate and summarize a completed-run handoff bundle"
    )
    inspect_parser.add_argument("bundle", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "inspect-link":
        try:
            manifest = inspect_handoff_bundle(args.bundle)
        except HandoffError as exc:
            print(f"chimera: invalid handoff bundle: {exc}", file=sys.stderr)
            return 3
        print(f"run_id: {manifest['run_id']}")
        print(f"{manifest['requirement_id']}: {manifest['verdict']}")
        print(f"bundle: {args.bundle}")
        return 0
    if args.command == "export-link":
        try:
            manifest = create_handoff_bundle(args.run, args.output)
        except HandoffError as exc:
            print(f"chimera: handoff unavailable: {exc}", file=sys.stderr)
            return 3
        print(f"run_id: {manifest['run_id']}")
        print(f"{manifest['requirement_id']}: {manifest['verdict']}")
        print(f"bundle: {args.output}")
        return 0
    if args.command == "serve-dashboard":
        try:
            serve_dashboard(args.workspace, args.port)
        except DashboardError as exc:
            print(f"chimera: dashboard unavailable: {exc}", file=sys.stderr)
            return 3
        except KeyboardInterrupt:
            return 0
        return 0
    if args.command == "serve-link":
        try:
            serve_completed_run(args.output, args.port)
        except OperatorAPIError as exc:
            print(f"chimera: completed run unavailable: {exc}", file=sys.stderr)
            return 3
        except KeyboardInterrupt:
            return 0
        return 0
    if args.command == "verify-link":
        try:
            result = run_link_verification(
                args.source, args.output, threshold_db=args.threshold_db,
                fault_plan_path=args.fault_plan,
                resume_run_id=args.resume_run_id,
            )
        except OperatorInputError as exc:
            print(f"chimera: invalid link request: {exc}", file=sys.stderr)
            return 2
        except (OperatorOutputError, OperatorError) as exc:
            print(f"chimera: link run unavailable: {exc}", file=sys.stderr)
            return 3
        print(f"run_id: {result.run_id}")
        print(f"COM-LINK-001: {result.verdict}")
        print(f"evidence: {result.evidence_path}")
        print(f"report-json: {result.report_json_path}")
        print(f"report-html: {result.report_html_path}")
        return 0 if result.verdict == "pass" else (1 if result.verdict == "fail" else 2)

    if args.command != "run":  # pragma: no cover - argparse enforces this
        return 2

    if args.evidence.exists():
        print(f"chimera: evidence output already exists: {args.evidence}", file=sys.stderr)
        return 3
    try:
        tasks = load_workflow(args.workflow)
        evidence = run_with_evidence(tasks)
    except (WorkflowError, EvidenceError, ValueError) as exc:
        print(f"chimera: invalid workflow: {exc}", file=sys.stderr)
        return 2

    try:
        with args.evidence.open("x", encoding="utf-8") as stream:
            stream.write(evidence.to_json())
            stream.write("\n")
    except OSError as exc:
        print(f"chimera: cannot write evidence: {exc}", file=sys.stderr)
        return 3

    tasks_document = evidence.to_dict()["tasks"]
    for task in tasks_document:
        print(f"{task['task_id']}: {task['status']}")
    failed = any(task["status"] != "succeeded" for task in tasks_document)
    print(f"evidence: {args.evidence}")
    return 1 if failed else 0


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
