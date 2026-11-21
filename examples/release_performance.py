"""Measure the bounded P7 local-prototype workload from an exact clean commit.

The record is synthetic engineering evidence.  It is not a hardware, production,
capacity, or service-level claim.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from time import perf_counter_ns
from typing import Callable

from chimera.dashboard import CompletedRunWorkspace
from chimera.handoff import create_handoff_bundle, inspect_handoff_bundle
from chimera.operator import run_link_verification


ROOT = Path(__file__).resolve().parents[1]
_COMMIT = re.compile(r"[0-9a-f]{40}")


class PerformanceBaselineError(RuntimeError):
    """A release-performance record could not be produced safely."""


@dataclass(frozen=True)
class Workload:
    sample_count: int = 10_000
    workspace_runs: int = 10
    handoff_iterations: int = 10
    dashboard_iterations: int = 5

    def validate(self) -> None:
        if (type(self.sample_count) is not int
                or not 2 <= self.sample_count <= 10_000):
            raise PerformanceBaselineError("sample_count must be in 2..10000")
        if (type(self.workspace_runs) is not int
                or not 1 <= self.workspace_runs <= 100):
            raise PerformanceBaselineError("workspace_runs must be in 1..100")
        if (type(self.handoff_iterations) is not int
                or not 1 <= self.handoff_iterations <= 20):
            raise PerformanceBaselineError("handoff_iterations must be in 1..20")
        if (type(self.dashboard_iterations) is not int
                or not 1 <= self.dashboard_iterations <= 20):
            raise PerformanceBaselineError("dashboard_iterations must be in 1..20")


DEFAULT_WORKLOAD = Workload()
TARGETS_MS = {
    "operator_run_p95_ms": 3_000.0,
    "handoff_round_trip_p95_ms": 1_000.0,
    "dashboard_snapshot_p95_ms": 3_000.0,
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PerformanceBaselineError(message)


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
        raise PerformanceBaselineError("Git checkout identity is unavailable") from exc


def _validate_candidate_checkout(candidate_commit: str) -> None:
    if type(candidate_commit) is not str or _COMMIT.fullmatch(candidate_commit) is None:
        raise PerformanceBaselineError(
            "candidate commit must be a full lowercase 40-character Git SHA"
        )
    head = _git("rev-parse", "HEAD")
    actual = head.stdout.strip()
    if (head.returncode != 0 or _COMMIT.fullmatch(actual) is None
            or actual != candidate_commit):
        raise PerformanceBaselineError(
            "candidate commit must equal the exact checked-out Git HEAD"
        )
    status = _git("status", "--porcelain", "--untracked-files=normal")
    if status.returncode != 0:
        raise PerformanceBaselineError("Git checkout status is unavailable")
    if status.stdout:
        raise PerformanceBaselineError(
            "performance measurement requires a clean checkout"
        )


def _timestamp_text(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise PerformanceBaselineError(
            "generated_at_utc must be canonical UTC timestamp text"
        ) from exc
    if (parsed.tzinfo != timezone.utc
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise PerformanceBaselineError(
            "generated_at_utc must be canonical UTC timestamp text"
        )
    return value


def _telemetry(sample_count: int) -> bytes:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lines = ["timestamp_utc,link_margin_db"]
    for index in range(sample_count):
        timestamp = (start + timedelta(seconds=index)).isoformat()
        margin = "2.0" if index == sample_count - 1 else "4.0"
        lines.append(f"{timestamp},{margin}")
    content = ("\n".join(lines) + "\n").encode("utf-8")
    _require(len(content) <= 1_048_576, "generated telemetry exceeds product bound")
    return content


def _duration_ms(timer: Callable[[], int], action: Callable[[], object]) -> float:
    before = timer()
    action()
    after = timer()
    _require(type(before) is int and type(after) is int and after >= before,
             "monotonic timer returned an invalid interval")
    return round((after - before) / 1_000_000, 3)


def _percentile(values: list[float], fraction: float) -> float:
    _require(values and 0 < fraction <= 1, "percentile input is invalid")
    ordered = sorted(values)
    position = max(1, math.ceil(fraction * len(ordered))) - 1
    return ordered[position]


def _summary(values: list[float]) -> dict:
    _require(
        bool(values) and all(
            type(value) in (int, float) and math.isfinite(value) and value >= 0
            for value in values
        ),
        "performance samples must be finite nonnegative numbers",
    )
    return {
        "samples_ms": values,
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
        "max_ms": max(values),
    }


def _evaluate(measurements: dict, targets: dict[str, float]) -> tuple[str, dict]:
    metric_sources = {
        "operator_run_p95_ms": ("operator_run", "p95_ms"),
        "handoff_round_trip_p95_ms": ("handoff_round_trip", "p95_ms"),
        "dashboard_snapshot_p95_ms": ("dashboard_snapshot", "p95_ms"),
    }
    _require(set(targets) == set(metric_sources), "performance target set changed")
    results = {}
    for metric, (group, field) in metric_sources.items():
        limit = targets[metric]
        observed = measurements[group][field]
        _require(type(limit) in (int, float) and math.isfinite(limit) and limit > 0,
                 f"invalid performance target: {metric}")
        results[metric] = {
            "observed_ms": observed,
            "target_ms": limit,
            "status": "passed" if observed <= limit else "failed",
        }
    status = "passed" if all(
        item["status"] == "passed" for item in results.values()
    ) else "failed"
    return status, results


def _run_workload(root: Path, workload: Workload,
                  timer: Callable[[], int]) -> dict:
    workload.validate()
    source = root / "synthetic-max-input.csv"
    source.write_bytes(_telemetry(workload.sample_count))
    runs = root / "runs"
    bundles = root / "handoffs"
    runs.mkdir()
    bundles.mkdir()

    operator_samples = []
    results = []
    for index in range(workload.workspace_runs):
        output = runs / f"run-{index + 1:02d}"
        holder: dict[str, object] = {}

        def execute() -> None:
            holder["result"] = run_link_verification(
                source, output, threshold_db="3.0"
            )

        operator_samples.append(_duration_ms(timer, execute))
        result = holder["result"]
        _require(getattr(result, "verdict", None) == "fail",
                 "performance workload did not preserve expected FAIL verdict")
        results.append(result)

    handoff_samples = []
    first_run = runs / "run-01"
    expected_run_id = getattr(results[0], "run_id")
    for index in range(workload.handoff_iterations):
        bundle = bundles / f"handoff-{index + 1:02d}.zip"
        holder: dict[str, object] = {}

        def round_trip() -> None:
            holder["created"] = create_handoff_bundle(first_run, bundle)
            holder["opened"] = inspect_handoff_bundle(bundle)

        handoff_samples.append(_duration_ms(timer, round_trip))
        _require(holder["created"] == holder["opened"],
                 "handoff manifest changed during performance measurement")
        _require(holder["opened"]["run_id"] == expected_run_id,
                 "handoff run identity changed during performance measurement")

    dashboard_samples = []
    for _ in range(workload.dashboard_iterations):
        holder: dict[str, object] = {}

        def open_snapshot() -> None:
            holder["workspace"] = CompletedRunWorkspace.open(runs)

        dashboard_samples.append(_duration_ms(timer, open_snapshot))
        document = holder["workspace"].document()
        _require(document["run_count"] == workload.workspace_runs,
                 "dashboard omitted a measured completed run")
        _require(document["invalid_count"] == 0,
                 "dashboard rejected a measured completed run")

    return {
        "operator_run": _summary(operator_samples),
        "handoff_round_trip": _summary(handoff_samples),
        "dashboard_snapshot": _summary(dashboard_samples),
    }


def _environment() -> dict:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "operating_system": platform.system(),
        "kernel_release": platform.release(),
        "machine": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
    }


def _write_record(target: Path, record: dict) -> None:
    content = _canonical(record)
    try:
        with target.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise PerformanceBaselineError(
            "performance output already exists or is a symbolic link"
        ) from exc
    except OSError as exc:
        try:
            if target.is_file() and not target.is_symlink():
                target.unlink()
        except OSError:
            pass
        raise PerformanceBaselineError("cannot publish performance output") from exc
    try:
        reopened = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise PerformanceBaselineError("performance output did not reopen") from exc
    _require(_canonical(reopened) == content,
             "performance output did not reopen canonically")


def _measure_configured_performance(
    output: str | Path, *, candidate_commit: str,
    workload: Workload, targets: dict[str, float], workload_version: str,
    generated_at_utc: str | None = None,
    timer: Callable[[], int] = perf_counter_ns,
) -> dict:
    """Private configurable runner used by tests and the fixed public wrapper."""
    _validate_candidate_checkout(candidate_commit)
    target = Path(output)
    if target.is_symlink() or target.exists():
        raise PerformanceBaselineError(
            "performance output already exists or is a symbolic link"
        )
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise PerformanceBaselineError("performance output parent is unavailable")
    resolved = target.resolve(strict=False)
    checkout = ROOT.resolve()
    if resolved == checkout or checkout in resolved.parents:
        raise PerformanceBaselineError(
            "performance output must be outside the source checkout"
        )
    generated = _timestamp_text(generated_at_utc)
    workload.validate()
    _require(type(workload_version) is str and workload_version,
             "workload_version must be nonempty text")
    if workload_version == "p7-local-prototype-v1":
        _require(workload == DEFAULT_WORKLOAD and targets == TARGETS_MS,
                 "p7-local-prototype-v1 workload and targets are fixed")
    with tempfile.TemporaryDirectory(prefix="chimera-release-performance-") as directory:
        measurements = _run_workload(Path(directory), workload, timer)
    status, target_results = _evaluate(measurements, dict(targets))
    record = {
        "schema_version": 1,
        "record_type": "chimera.release-performance-baseline",
        "workload_version": workload_version,
        "candidate_commit_sha": candidate_commit,
        "candidate_checks": {
            "before_measurement": "matched_clean_head",
            "before_publication": "matched_clean_head",
        },
        "generated_at_utc": generated,
        "clock": "time.perf_counter_ns monotonic elapsed time",
        "environment": _environment(),
        "workload": {
            "source": "generated synthetic communications CSV",
            "sample_count": workload.sample_count,
            "workspace_runs": workload.workspace_runs,
            "handoff_iterations": workload.handoff_iterations,
            "dashboard_iterations": workload.dashboard_iterations,
            "threshold_db": "3.0",
            "minimum_link_margin_db": "2.0",
            "expected_verdict": "fail",
        },
        "targets_ms": dict(targets),
        "measurements": measurements,
        "target_results": target_results,
        "status": status,
        "scope": (
            "local synthetic prototype workload; not hardware, production capacity, "
            "multi-user load, or a service-level objective"
        ),
    }
    # Prevent source changes from being labeled as measurements of candidate_commit.
    _validate_candidate_checkout(candidate_commit)
    _write_record(resolved, record)
    return record


def measure_performance(
    output: str | Path, *, candidate_commit: str,
    generated_at_utc: str | None = None,
) -> dict:
    """Measure the immutable p7-local-prototype-v1 workload and targets."""
    return _measure_configured_performance(
        output,
        candidate_commit=candidate_commit,
        workload=DEFAULT_WORKLOAD,
        targets=TARGETS_MS,
        workload_version="p7-local-prototype-v1",
        generated_at_utc=generated_at_utc,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="measure the fixed synthetic P7 local-prototype workload"
    )
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        record = measure_performance(
            args.output, candidate_commit=args.candidate_commit
        )
    except PerformanceBaselineError as exc:
        print(f"chimera performance: {exc}", file=sys.stderr)
        return 2
    for metric, result in record["target_results"].items():
        print(
            f"{result['status'].upper()} {metric}: "
            f"{result['observed_ms']:.3f} ms <= {result['target_ms']:.3f} ms"
        )
    print(f"candidate-commit: {args.candidate_commit}")
    print(f"performance-record: {args.output.resolve(strict=False)}")
    print("Synthetic local-prototype performance only; no hardware or production claim")
    return 0 if record["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
