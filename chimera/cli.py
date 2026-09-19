"""Command-line operator boundary for declarative local workflows."""
import argparse
from pathlib import Path
import sys

from .evidence import EvidenceError, run_with_evidence
from .workflow import WorkflowError, load_workflow


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chimera")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="run a declarative JSON workflow")
    run_parser.add_argument("workflow", type=Path)
    run_parser.add_argument("--evidence", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
