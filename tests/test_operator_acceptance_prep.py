"""Protect the persistent P3/P4/P5 operator-review preparation boundary."""
import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from chimera.dashboard import CompletedRunWorkspace
from chimera.handoff import inspect_handoff_bundle
from examples import operator_acceptance_prep


class OperatorAcceptancePreparationTests(unittest.TestCase):
    candidate = "a" * 40

    def _prepare(self, output: Path):
        with patch.object(
                operator_acceptance_prep, "_validate_candidate_checkout"):
            return operator_acceptance_prep.prepare_acceptance(
                output, candidate_commit=self.candidate,
                generated_at_utc="2026-10-24T10:00:00Z",
            )

    @staticmethod
    def _tree_bytes(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()
        }

    def test_prepares_truthful_non_overwriting_review_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "acceptance"
            record = self._prepare(output)

            self.assertEqual(self.candidate, record["candidate_commit_sha"])
            self.assertEqual("passed", record["engineering_status"])
            self.assertEqual(
                "pending_human_observation", record["acceptance_status"]
            )
            self.assertEqual(8, len(record["controls"]))
            self.assertEqual(
                [f"P345-{number}" for number in range(1, 9)],
                [item["control_id"] for item in record["controls"]],
            )
            self.assertEqual(
                {"passed"}, {item["status"] for item in record["controls"]}
            )
            self.assertEqual("not_performed", record["human_observations"]["status"])
            self.assertEqual(
                {"OperatorInputError"},
                {item["exception"] for item in record["malformed_inputs"]},
            )
            self.assertEqual(
                {False}, {item["output_created"] for item in record["malformed_inputs"]}
            )
            self.assertTrue(all(
                item["error"] and len(item["error"]) <= 512
                for item in record["malformed_inputs"]
            ))
            self.assertEqual(
                "not_evaluated",
                record["missing_evidence"]["requirement_verdict"],
            )
            self.assertEqual(
                "unavailable", record["missing_evidence"]["detail_status"]
            )
            self.assertTrue(
                record["completed_resume"]["portable_artifacts_unchanged"]
            )
            self.assertEqual(
                record["completed_resume"]["before_sha256"],
                record["completed_resume"]["after_sha256"],
            )

            saved = (output / "acceptance-preparation.json").read_bytes()
            self.assertEqual(record, json.loads(saved.decode("utf-8")))
            self.assertEqual(
                saved,
                (json.dumps(
                    record, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False,
                ) + "\n").encode("utf-8"),
            )
            for run in record["runs"]:
                for artifact in run["artifacts"]:
                    self.assertFalse(Path(artifact["path"]).is_absolute())
                    content = (output / artifact["path"]).read_bytes()
                    self.assertEqual(len(content), artifact["bytes"])
                    self.assertEqual(sha256(content).hexdigest(), artifact["sha256"])
            for artifact in record["handoffs"]:
                self.assertFalse(Path(artifact["path"]).is_absolute())
                content = (output / artifact["path"]).read_bytes()
                self.assertEqual(len(content), artifact["bytes"])
                self.assertEqual(sha256(content).hexdigest(), artifact["sha256"])
            for malformed in record["malformed_inputs"]:
                artifact = malformed["input"]
                content = (output / artifact["path"]).read_bytes()
                self.assertEqual(len(content), artifact["bytes"])
                self.assertEqual(sha256(content).hexdigest(), artifact["sha256"])
            for artifact in record["missing_evidence"]["artifacts"]:
                content = (output / artifact["path"]).read_bytes()
                self.assertEqual(len(content), artifact["bytes"])
                self.assertEqual(sha256(content).hexdigest(), artifact["sha256"])
            worksheet_artifact = record["observation_worksheet"]
            worksheet_bytes = (output / worksheet_artifact["path"]).read_bytes()
            self.assertEqual(len(worksheet_bytes), worksheet_artifact["bytes"])
            self.assertEqual(
                sha256(worksheet_bytes).hexdigest(), worksheet_artifact["sha256"]
            )

            workspace = CompletedRunWorkspace.open(output / "runs").document()
            self.assertEqual(3, workspace["run_count"])
            self.assertEqual(0, workspace["invalid_count"])
            self.assertEqual(
                ["fail", "fail", "pass"],
                sorted(item["verdict"] for item in workspace["runs"]),
            )
            file_manifest = inspect_handoff_bundle(
                output / "handoffs" / "synthetic-failure-a.zip"
            )
            repeated_manifest = inspect_handoff_bundle(
                output / "handoffs" / "synthetic-failure-b.zip"
            )
            dashboard_manifest = inspect_handoff_bundle(
                output / "handoffs" / "dashboard-synthetic-failure.zip"
            )
            self.assertEqual(file_manifest, repeated_manifest)
            self.assertEqual(file_manifest, dashboard_manifest)
            self.assertEqual(
                (output / "handoffs" / "synthetic-failure-a.zip").read_bytes(),
                (output / "handoffs" / "synthetic-failure-b.zip").read_bytes(),
            )

            worksheet = (output / "operator-observations.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(self.candidate, worksheet)
            self.assertIn("**NOT PERFORMED.**", worksheet)
            self.assertIn("- [ ]", worksheet)
            self.assertNotIn("- [x]", worksheet.lower())
            self.assertIn("P5 verification/validation: pending", worksheet)

            before = self._tree_bytes(output)
            with self.assertRaisesRegex(
                    operator_acceptance_prep.AcceptancePreparationError,
                    "already exists"):
                self._prepare(output)
            self.assertEqual(before, self._tree_bytes(output))

    def test_candidate_checkout_validation_fails_closed_before_output(self):
        invalid = ("", "abc", "A" * 40, " " + "a" * 40, "g" * 40)
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with patch.object(operator_acceptance_prep, "_git") as git:
                    with self.assertRaisesRegex(
                            operator_acceptance_prep.AcceptancePreparationError,
                            "full lowercase"):
                        operator_acceptance_prep._validate_candidate_checkout(candidate)
                    git.assert_not_called()

        wrong_head = subprocess.CompletedProcess(
            ["git"], 0, stdout="b" * 40 + "\n", stderr=""
        )
        with patch.object(
                operator_acceptance_prep, "_git", return_value=wrong_head):
            with self.assertRaisesRegex(
                    operator_acceptance_prep.AcceptancePreparationError,
                    "exact checked-out"):
                operator_acceptance_prep._validate_candidate_checkout(self.candidate)

        head = subprocess.CompletedProcess(
            ["git"], 0, stdout=self.candidate + "\n", stderr=""
        )
        dirty = subprocess.CompletedProcess(
            ["git"], 0, stdout="?? chimera/untracked.py\n", stderr=""
        )
        with patch.object(
                operator_acceptance_prep, "_git", side_effect=[head, dirty]):
            with self.assertRaisesRegex(
                    operator_acceptance_prep.AcceptancePreparationError,
                    "clean checkout"):
                operator_acceptance_prep._validate_candidate_checkout(self.candidate)

        unavailable = subprocess.CompletedProcess(
            ["git"], 128, stdout="", stderr="not a repository"
        )
        with patch.object(
                operator_acceptance_prep, "_git", return_value=unavailable):
            with self.assertRaisesRegex(
                    operator_acceptance_prep.AcceptancePreparationError,
                    "exact checked-out"):
                operator_acceptance_prep._validate_candidate_checkout(self.candidate)

    def test_refuses_existing_targets_and_concurrent_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, make in (
                ("directory", lambda path: path.mkdir()),
                ("file", lambda path: path.write_text("user\n", encoding="utf-8")),
                ("symlink", lambda path: path.symlink_to(root / "missing")),
            ):
                target = root / name
                make(target)
                before = self._tree_bytes(root)
                with self.assertRaisesRegex(
                        operator_acceptance_prep.AcceptancePreparationError,
                        "already exists"):
                    self._prepare(target)
                self.assertEqual(before, self._tree_bytes(root))

            raced = root / "raced"
            original_mkdir = Path.mkdir

            def concurrent_empty_directory(path, *args, **kwargs):
                if path == raced:
                    original_mkdir(path, *args, **kwargs)
                    raise FileExistsError("concurrent empty directory")
                return original_mkdir(path, *args, **kwargs)

            with patch.object(Path, "mkdir", new=concurrent_empty_directory):
                with self.assertRaisesRegex(
                        operator_acceptance_prep.AcceptancePreparationError,
                        "appeared during publication"):
                    self._prepare(raced)
            self.assertTrue(raced.is_dir())
            self.assertEqual([], list(raced.iterdir()))

    def test_late_control_failure_publishes_no_final_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "acceptance"
            with patch.object(
                    operator_acceptance_prep, "_validate_candidate_checkout"), patch.object(
                    operator_acceptance_prep, "run_link_verification",
                    side_effect=RuntimeError("synthetic late control failure")):
                with self.assertRaisesRegex(RuntimeError, "synthetic late"):
                    operator_acceptance_prep.prepare_acceptance(
                        output, candidate_commit=self.candidate
                    )
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.iterdir()))

    def test_checkout_change_before_publication_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "acceptance"
            changed = operator_acceptance_prep.AcceptancePreparationError(
                "acceptance preparation requires a clean checkout"
            )
            with patch.object(
                    operator_acceptance_prep, "_validate_candidate_checkout",
                    side_effect=[None, changed]):
                with self.assertRaisesRegex(
                        operator_acceptance_prep.AcceptancePreparationError,
                        "clean checkout"):
                    operator_acceptance_prep.prepare_acceptance(
                        output, candidate_commit=self.candidate,
                        generated_at_utc="2026-10-24T10:00:00Z",
                    )
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.iterdir()))

    def test_publication_failures_never_look_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "marker-failure"
            original_open = Path.open

            def fail_marker(path, mode="r", *args, **kwargs):
                if path.name == ".PUBLISHING" and "x" in mode:
                    raise PermissionError("synthetic marker failure")
                return original_open(path, mode, *args, **kwargs)

            with patch.object(Path, "open", new=fail_marker):
                with self.assertRaisesRegex(
                        operator_acceptance_prep.AcceptancePreparationError,
                        "initialize acceptance output"):
                    self._prepare(output)
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.iterdir()))

            incomplete = root / "move-failure"
            original_rename = os.rename

            def fail_first_publication_move(source, destination):
                if Path(destination).parent == incomplete:
                    raise OSError("synthetic move failure")
                return original_rename(source, destination)

            with patch.object(os, "rename", new=fail_first_publication_move):
                with self.assertRaisesRegex(
                        operator_acceptance_prep.AcceptancePreparationError,
                        "publication is incomplete"):
                    self._prepare(incomplete)
            marker = incomplete / ".PUBLISHING"
            self.assertTrue(marker.is_file())
            self.assertIn("do not use", marker.read_text(encoding="utf-8"))
            self.assertFalse((incomplete / "acceptance-preparation.json").exists())

    def test_control_does_not_depend_on_removable_asserts(self):
        path = Path(operator_acceptance_prep.__file__)
        source = path.read_text(encoding="utf-8")
        self.assertFalse(
            any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(source))),
            "acceptance preparation controls must survive python -O",
        )


if __name__ == "__main__":
    unittest.main()
