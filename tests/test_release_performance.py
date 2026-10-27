"""Protect the versioned P7 local-prototype performance baseline."""
import ast
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from examples import release_performance


class ReleasePerformanceTests(unittest.TestCase):
    candidate = "a" * 40
    small_workload = release_performance.Workload(
        sample_count=8,
        workspace_runs=2,
        handoff_iterations=2,
        dashboard_iterations=2,
    )

    def _measure(self, output: Path):
        with patch.object(
                release_performance, "_validate_candidate_checkout") as validate:
            record = release_performance._measure_configured_performance(
                output,
                candidate_commit=self.candidate,
                generated_at_utc="2026-10-27T10:00:00Z",
                workload=self.small_workload,
                targets={
                    "operator_run_p95_ms": 60_000.0,
                    "handoff_round_trip_p95_ms": 60_000.0,
                    "dashboard_snapshot_p95_ms": 60_000.0,
                },
                workload_version="test-only-v1",
            )
        self.assertEqual(2, validate.call_count)
        return record

    def test_publishes_versioned_record_for_public_product_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "performance.json"
            record = self._measure(output)

            self.assertEqual(1, record["schema_version"])
            self.assertEqual(
                "chimera.release-performance-baseline", record["record_type"]
            )
            self.assertEqual("test-only-v1", record["workload_version"])
            self.assertEqual(self.candidate, record["candidate_commit_sha"])
            self.assertEqual("passed", record["status"])
            self.assertEqual("fail", record["workload"]["expected_verdict"])
            self.assertEqual(8, record["workload"]["sample_count"])
            self.assertEqual(2, record["workload"]["workspace_runs"])
            self.assertEqual(
                {"operator_run", "handoff_round_trip", "dashboard_snapshot"},
                set(record["measurements"]),
            )
            self.assertEqual(
                2, len(record["measurements"]["operator_run"]["samples_ms"])
            )
            self.assertEqual(
                2,
                len(record["measurements"]["handoff_round_trip"]["samples_ms"]),
            )
            self.assertEqual(
                2,
                len(record["measurements"]["dashboard_snapshot"]["samples_ms"]),
            )
            self.assertTrue(all(
                item["status"] == "passed"
                for item in record["target_results"].values()
            ))
            self.assertIn("not hardware", record["scope"])

            saved = output.read_bytes()
            self.assertEqual(record, json.loads(saved.decode("utf-8")))
            self.assertEqual(
                saved,
                (json.dumps(
                    record, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False,
                ) + "\n").encode("utf-8"),
            )

            before = saved
            with self.assertRaisesRegex(
                    release_performance.PerformanceBaselineError, "already exists"):
                self._measure(output)
            self.assertEqual(before, output.read_bytes())

    def test_target_evaluation_is_explicit_and_conservative(self):
        measurements = {
            "operator_run": {"p95_ms": 3000.001},
            "handoff_round_trip": {"p95_ms": 1000.0},
            "dashboard_snapshot": {"p95_ms": 2999.999},
        }
        status, results = release_performance._evaluate(
            measurements, release_performance.TARGETS_MS
        )
        self.assertEqual("failed", status)
        self.assertEqual("failed", results["operator_run_p95_ms"]["status"])
        self.assertEqual("passed", results["handoff_round_trip_p95_ms"]["status"])
        self.assertEqual("passed", results["dashboard_snapshot_p95_ms"]["status"])

        self.assertEqual(
            {"samples_ms": [1.0, 2.0, 3.0, 4.0, 100.0],
             "p50_ms": 3.0, "p95_ms": 100.0, "max_ms": 100.0},
            release_performance._summary([1.0, 2.0, 3.0, 4.0, 100.0]),
        )

    def test_candidate_validation_fails_closed(self):
        for candidate in ("", "abc", "A" * 40, "g" * 40):
            with self.subTest(candidate=candidate):
                with patch.object(release_performance, "_git") as git:
                    with self.assertRaisesRegex(
                            release_performance.PerformanceBaselineError,
                            "full lowercase"):
                        release_performance._validate_candidate_checkout(candidate)
                    git.assert_not_called()

        head = subprocess.CompletedProcess(
            ["git"], 0, stdout=self.candidate + "\n", stderr=""
        )
        dirty = subprocess.CompletedProcess(
            ["git"], 0, stdout="?? local-result.json\n", stderr=""
        )
        with patch.object(
                release_performance, "_git", side_effect=[head, dirty]):
            with self.assertRaisesRegex(
                    release_performance.PerformanceBaselineError, "clean checkout"):
                release_performance._validate_candidate_checkout(self.candidate)

        wrong_head = subprocess.CompletedProcess(
            ["git"], 0, stdout="b" * 40 + "\n", stderr=""
        )
        with patch.object(
                release_performance, "_git", return_value=wrong_head):
            with self.assertRaisesRegex(
                    release_performance.PerformanceBaselineError,
                    "exact checked-out"):
                release_performance._validate_candidate_checkout(self.candidate)

    def test_fixed_version_cannot_be_relabelled_with_test_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                    release_performance, "_validate_candidate_checkout"):
                with self.assertRaisesRegex(
                        release_performance.PerformanceBaselineError,
                        "workload and targets are fixed"):
                    release_performance._measure_configured_performance(
                        Path(directory) / "result.json",
                        candidate_commit=self.candidate,
                        workload=self.small_workload,
                        targets=release_performance.TARGETS_MS,
                        workload_version="p7-local-prototype-v1",
                    )

    def test_public_runner_pins_the_exact_v1_contract(self):
        with patch.object(
                release_performance, "_measure_configured_performance",
                return_value={"status": "passed"}) as configured:
            result = release_performance.measure_performance(
                "/tmp/result.json", candidate_commit=self.candidate,
                generated_at_utc="2026-10-27T10:00:00Z",
            )
        self.assertEqual({"status": "passed"}, result)
        configured.assert_called_once_with(
            "/tmp/result.json",
            candidate_commit=self.candidate,
            workload=release_performance.DEFAULT_WORKLOAD,
            targets=release_performance.TARGETS_MS,
            workload_version="p7-local-prototype-v1",
            generated_at_utc="2026-10-27T10:00:00Z",
        )

    def test_refuses_directory_symlink_and_symlinked_parent_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing_directory = root / "existing-directory"
            existing_directory.mkdir()
            dangling_symlink = root / "dangling-symlink"
            dangling_symlink.symlink_to(root / "missing")
            real_parent = root / "real-parent"
            real_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)

            with patch.object(
                    release_performance, "_validate_candidate_checkout"):
                for output, message in (
                    (existing_directory, "already exists"),
                    (dangling_symlink, "already exists"),
                    (linked_parent / "result.json", "parent is unavailable"),
                ):
                    with self.subTest(output=output):
                        with self.assertRaisesRegex(
                                release_performance.PerformanceBaselineError,
                                message):
                            release_performance._measure_configured_performance(
                                output,
                                candidate_commit=self.candidate,
                                workload=self.small_workload,
                                targets={
                                    "operator_run_p95_ms": 60_000.0,
                                    "handoff_round_trip_p95_ms": 60_000.0,
                                    "dashboard_snapshot_p95_ms": 60_000.0,
                                },
                                workload_version="test-only-v1",
                            )
            self.assertEqual([], list(real_parent.iterdir()))

    def test_output_must_be_outside_checkout(self):
        output = release_performance.ROOT / "performance.json"
        with patch.object(release_performance, "_validate_candidate_checkout"):
            with self.assertRaisesRegex(
                    release_performance.PerformanceBaselineError,
                    "outside the source checkout"):
                release_performance._measure_configured_performance(
                    output, candidate_commit=self.candidate,
                    workload=self.small_workload,
                    targets={
                        "operator_run_p95_ms": 60_000.0,
                        "handoff_round_trip_p95_ms": 60_000.0,
                        "dashboard_snapshot_p95_ms": 60_000.0,
                    },
                    workload_version="test-only-v1",
                )
        self.assertFalse(output.exists())

    def test_control_does_not_depend_on_removable_asserts(self):
        source = Path(release_performance.__file__).read_text(encoding="utf-8")
        self.assertFalse(
            any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(source))),
            "performance controls must survive python -O",
        )


if __name__ == "__main__":
    unittest.main()
