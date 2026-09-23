"""Executable P2 verification controls; engineering evidence, not PM acceptance."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _run_control(module: str, expected: tuple[str, ...]) -> str:
    flags = ["-O"] if sys.flags.optimize else []
    result = subprocess.run(
        [sys.executable, *flags, "-m", module],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{module} exited {result.returncode}: {result.stderr.strip()}"
        )
    missing = [line for line in expected if line not in result.stdout]
    if missing:
        raise RuntimeError(f"{module} omitted expected evidence: {missing}")
    return result.stdout


def main() -> None:
    _run_control("examples.link_csv_demo", (
        "journal/export: completed and reopened without callback replay",
        "COM-LINK-001: fail",
        "failing samples: 1",
        "passing control: pass",
        "malformed control: rejected",
        "callbacks: ingest=1, check=1, report=1",
    ))
    print("PASS P2-1: durable failed communications evidence plus passing/malformed adapter controls")

    _run_control("examples.journal_export_demo", (
        "export: schema-v1 evidence reopened without callbacks",
        "requirement REQ-LINK-MARGIN: fail",
        "callbacks: link-margin-check=1",
    ))
    print("PASS P2-2: completed journal exported and assessed without callback replay")

    _run_control("examples.resume_demo", (
        "first task: preserved succeeded (not repeated)",
        "second task: resumed from pending and succeeded",
        "run: completed after process restart",
    ))
    print("PASS P2-3: proven-pending suffix resumed without repeating terminal work")

    _run_control("examples.journal_demo", (
        "effect marker: performed once",
        "recovered run: needs_attention",
        "effect task: running (outcome unknown; not retried)",
        "callback invocations during recovery: 0",
    ))
    print("PASS P2-4: outcome-unknown task required attention and was not retried")

    print("P2 engineering walkthrough passed; PM verification/validation decision pending")


if __name__ == "__main__":
    main()
