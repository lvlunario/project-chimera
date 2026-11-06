"""Protect the one-command exact-candidate review rehearsal boundary."""
import ast
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from examples import (
    operator_acceptance_prep,
    release_candidate_packet,
    release_performance,
    release_readiness,
    release_review_rehearsal,
    release_threat_model,
)


class ReleaseReviewRehearsalTests(unittest.TestCase):
    candidate = "a" * 40
    generated = "2026-11-06T10:58:00Z"

    def _validators(self):
        tracked = release_readiness._tracked_repository_paths()
        tracked.update({
            "examples/release_review_rehearsal.py",
            "tests/test_release_review_rehearsal.py",
        })
        return (
            patch.object(
                operator_acceptance_prep, "_validate_candidate_checkout"
            ),
            patch.object(
                release_performance, "_validate_candidate_checkout"
            ),
            patch.object(
                release_threat_model, "_validate_candidate_checkout"
            ),
            patch.object(
                release_readiness, "_validate_candidate_checkout"
            ),
            patch.object(
                release_candidate_packet, "_validate_candidate_checkout"
            ),
            patch.object(
                release_readiness,
                "_tracked_repository_paths",
                return_value=tracked,
            ),
        )

    @staticmethod
    def _tree_bytes(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def test_prepares_fail_closed_candidate_bound_review_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "review"
            validators = self._validators()
            with (
                validators[0],
                validators[1],
                validators[2],
                validators[3],
                validators[4],
                validators[5],
            ):
                receipt = release_review_rehearsal.prepare_review_rehearsal(
                    output,
                    candidate_commit=self.candidate,
                    generated_at_utc=self.generated,
                )

            self.assertEqual(self.candidate, receipt["candidate_commit_sha"])
            self.assertEqual(self.generated, receipt["generated_at_utc"])
            self.assertEqual(
                "packet_complete_for_m4_review", receipt["status"]
            )
            self.assertEqual([], receipt["release_blockers"])
            self.assertEqual("pending", receipt["m4_decision"])
            self.assertEqual("pending", receipt["m5_decision"])
            self.assertEqual("not_granted", receipt["human_acceptance"])
            self.assertEqual(
                {
                    "operator_acceptance": "passed",
                    "performance": "passed",
                    "release_readiness": "review_inputs_complete",
                    "threat_model": "model_complete",
                },
                receipt["component_statuses"],
            )
            self.assertFalse((output / ".PUBLISHING").exists())

            saved = (output / release_review_rehearsal.RECEIPT_NAME).read_bytes()
            self.assertEqual(receipt, json.loads(saved.decode("utf-8")))
            self.assertEqual(
                release_review_rehearsal._canonical(receipt), saved
            )
            self.assertEqual(
                receipt,
                release_review_rehearsal.inspect_review_rehearsal(output),
            )
            self.assertEqual(
                receipt["packet_status"],
                release_candidate_packet.inspect_packet(
                    output / release_review_rehearsal.PACKET_NAME
                )["status"],
            )
            expected = {
                "chimera-m4-evidence.zip",
                "sources/operator-acceptance/acceptance-preparation.json",
                "sources/operator-acceptance/operator-observations.md",
                "sources/release-performance.json",
                "sources/release-readiness.json",
                "sources/release-threat-model.json",
            }
            artifact_paths = {item["path"] for item in receipt["artifacts"]}
            self.assertTrue(
                expected.issubset(artifact_paths),
                expected - artifact_paths,
            )
            for artifact in receipt["artifacts"]:
                path = output / artifact["path"]
                content = path.read_bytes()
                self.assertEqual(len(content), artifact["byte_count"])
                self.assertEqual(
                    sha256(content).hexdigest(), artifact["sha256"]
                )
                self.assertFalse(Path(artifact["path"]).is_absolute())
                self.assertNotIn("..", Path(artifact["path"]).parts)

            worksheet = (
                output / "sources/operator-acceptance/operator-observations.md"
            ).read_text(encoding="utf-8")
            self.assertIn(self.candidate, worksheet)
            self.assertIn("**NOT PERFORMED.**", worksheet)
            self.assertNotIn("- [x]", worksheet.lower())

            extra = output / "extra.txt"
            extra.write_text("not indexed\n", encoding="utf-8")
            with self.assertRaisesRegex(
                    release_review_rehearsal.ReviewRehearsalError,
                    "inventory disagrees"):
                release_review_rehearsal.inspect_review_rehearsal(output)
            extra.unlink()

            marker = output / ".PUBLISHING"
            marker.write_text("incomplete\n", encoding="utf-8")
            with self.assertRaisesRegex(
                    release_review_rehearsal.ReviewRehearsalError,
                    "publication is incomplete"):
                release_review_rehearsal.inspect_review_rehearsal(output)
            marker.unlink()

            performance = output / "sources/release-performance.json"
            performance_original = performance.read_bytes()
            performance.write_bytes(performance_original + b" ")
            with self.assertRaisesRegex(
                    release_review_rehearsal.ReviewRehearsalError,
                    "inventory disagrees"):
                release_review_rehearsal.inspect_review_rehearsal(output)
            performance.write_bytes(performance_original)

            tampered = performance_original + b" "
            performance.write_bytes(tampered)
            reindexed = deepcopy(receipt)
            for artifact in reindexed["artifacts"]:
                if artifact["path"] == "sources/release-performance.json":
                    artifact["byte_count"] = len(tampered)
                    artifact["sha256"] = sha256(tampered).hexdigest()
            (output / release_review_rehearsal.RECEIPT_NAME).write_bytes(
                release_review_rehearsal._canonical(reindexed)
            )
            with self.assertRaisesRegex(
                    release_review_rehearsal.ReviewRehearsalError,
                    "packet source content disagrees"):
                release_review_rehearsal.inspect_review_rehearsal(output)
            performance.write_bytes(performance_original)
            (output / release_review_rehearsal.RECEIPT_NAME).write_bytes(saved)

            changed = deepcopy(receipt)
            changed["m4_decision"] = "approved"
            (output / release_review_rehearsal.RECEIPT_NAME).write_bytes(
                release_review_rehearsal._canonical(changed)
            )
            with self.assertRaisesRegex(
                    release_review_rehearsal.ReviewRehearsalError,
                    "cannot record acceptance"):
                release_review_rehearsal.inspect_review_rehearsal(output)
            (output / release_review_rehearsal.RECEIPT_NAME).write_bytes(saved)

            changed = deepcopy(receipt)
            changed["schema_version"] = True
            (output / release_review_rehearsal.RECEIPT_NAME).write_bytes(
                release_review_rehearsal._canonical(changed)
            )
            with self.assertRaisesRegex(
                    release_review_rehearsal.ReviewRehearsalError,
                    "receipt contract changed"):
                release_review_rehearsal.inspect_review_rehearsal(output)
            (output / release_review_rehearsal.RECEIPT_NAME).write_bytes(saved)

            changed = deepcopy(receipt)
            changed["artifacts"][0]["byte_count"] = float(
                changed["artifacts"][0]["byte_count"]
            )
            (output / release_review_rehearsal.RECEIPT_NAME).write_bytes(
                release_review_rehearsal._canonical(changed)
            )
            with self.assertRaisesRegex(
                    release_review_rehearsal.ReviewRehearsalError,
                    "artifact inventory disagrees"):
                release_review_rehearsal.inspect_review_rehearsal(output)
            (output / release_review_rehearsal.RECEIPT_NAME).write_bytes(saved)

            before = self._tree_bytes(output)
            with patch.object(
                    operator_acceptance_prep, "_validate_candidate_checkout"):
                with self.assertRaisesRegex(
                        release_review_rehearsal.ReviewRehearsalError,
                        "already exists"):
                    release_review_rehearsal.prepare_review_rehearsal(
                        output,
                        candidate_commit=self.candidate,
                        generated_at_utc=self.generated,
                    )
            self.assertEqual(before, self._tree_bytes(output))

    def test_component_failure_leaves_no_final_or_staging_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "review"
            with (
                patch.object(
                    operator_acceptance_prep, "_validate_candidate_checkout"
                ),
                patch.object(
                    operator_acceptance_prep,
                    "prepare_acceptance",
                    side_effect=operator_acceptance_prep.AcceptancePreparationError(
                        "injected failure"
                    ),
                ),
            ):
                with self.assertRaisesRegex(
                        operator_acceptance_prep.AcceptancePreparationError,
                        "injected failure"):
                    release_review_rehearsal.prepare_review_rehearsal(
                        output,
                        candidate_commit=self.candidate,
                        generated_at_utc=self.generated,
                    )
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.glob(".review.staging-*")))

    def test_interrupted_publication_retains_incomplete_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "review"
            validators = self._validators()
            original_rename = release_review_rehearsal.os.rename
            original_publish = release_review_rehearsal._publish_staging
            moves = []

            def interrupted_rename(source, target):
                if moves:
                    raise OSError("injected publication interruption")
                moves.append((source, target))
                original_rename(source, target)

            def interrupted_publish(stage, target, *, candidate_commit):
                with patch.object(
                        release_review_rehearsal.os,
                        "rename",
                        side_effect=interrupted_rename):
                    return original_publish(
                        stage, target, candidate_commit=candidate_commit
                    )

            with (
                validators[0],
                validators[1],
                validators[2],
                validators[3],
                validators[4],
                validators[5],
                patch.object(
                    release_review_rehearsal,
                    "_publish_staging",
                    side_effect=interrupted_publish,
                ),
            ):
                with self.assertRaisesRegex(
                        release_review_rehearsal.ReviewRehearsalError,
                        "publication is incomplete"):
                    release_review_rehearsal.prepare_review_rehearsal(
                        output,
                        candidate_commit=self.candidate,
                        generated_at_utc=self.generated,
                    )
            self.assertTrue((output / ".PUBLISHING").is_file())
            self.assertEqual([], list(root.glob(".review.staging-*")))
            with self.assertRaisesRegex(
                    release_review_rehearsal.ReviewRehearsalError,
                    "publication is incomplete"):
                release_review_rehearsal.inspect_review_rehearsal(output)

    def test_rejects_unsafe_existing_and_invalid_timestamp_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "existing"
            existing.mkdir()
            link = root / "link"
            link.symlink_to(existing, target_is_directory=True)
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(root, target_is_directory=True)
            with patch.object(
                    operator_acceptance_prep, "_validate_candidate_checkout"):
                for path in (existing, link):
                    with self.subTest(path=path):
                        with self.assertRaisesRegex(
                                release_review_rehearsal.ReviewRehearsalError,
                                "already exists"):
                            release_review_rehearsal.prepare_review_rehearsal(
                                path,
                                candidate_commit=self.candidate,
                                generated_at_utc=self.generated,
                            )
                with self.assertRaisesRegex(
                        release_review_rehearsal.ReviewRehearsalError,
                        "canonical UTC"):
                    release_review_rehearsal.prepare_review_rehearsal(
                        root / "bad-time",
                        candidate_commit=self.candidate,
                        generated_at_utc="2026-11-06T10:58:00+00:00",
                    )
                with self.assertRaisesRegex(
                        release_review_rehearsal.ReviewRehearsalError,
                        "parent is unavailable"):
                    release_review_rehearsal.prepare_review_rehearsal(
                        linked_parent / "review",
                        candidate_commit=self.candidate,
                        generated_at_utc=self.generated,
                    )
                with self.assertRaisesRegex(
                        release_review_rehearsal.ReviewRehearsalError,
                        "parent is unavailable"):
                    release_review_rehearsal.prepare_review_rehearsal(
                        root / "missing" / "review",
                        candidate_commit=self.candidate,
                        generated_at_utc=self.generated,
                    )

            with self.assertRaisesRegex(
                    operator_acceptance_prep.AcceptancePreparationError,
                    "full lowercase"):
                release_review_rehearsal.prepare_review_rehearsal(
                    root / "invalid-candidate",
                    candidate_commit="abc",
                    generated_at_utc=self.generated,
                )

        with patch.object(
                operator_acceptance_prep, "_validate_candidate_checkout"):
            with self.assertRaisesRegex(
                    release_review_rehearsal.ReviewRehearsalError,
                    "outside the source checkout"):
                release_review_rehearsal.prepare_review_rehearsal(
                    release_review_rehearsal.ROOT / "forbidden-review",
                    candidate_commit=self.candidate,
                    generated_at_utc=self.generated,
                )

    def test_late_candidate_change_publishes_no_final_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "review"
            late = operator_acceptance_prep.AcceptancePreparationError(
                "late candidate change"
            )
            validators = self._validators()
            with (
                patch.object(
                    operator_acceptance_prep,
                    "_validate_candidate_checkout",
                    side_effect=[None, None, None, late],
                ),
                validators[1],
                validators[2],
                validators[3],
                validators[4],
                validators[5],
            ):
                with self.assertRaisesRegex(
                        operator_acceptance_prep.AcceptancePreparationError,
                        "late candidate change"):
                    release_review_rehearsal.prepare_review_rehearsal(
                        output,
                        candidate_commit=self.candidate,
                        generated_at_utc=self.generated,
                    )
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.glob(".review.staging-*")))

    def test_receipt_parser_rejects_duplicate_and_nonfinite_fields(self):
        for content in (
            b'{"a":1,"a":2}\n',
            b'{"a":NaN}\n',
            b'{"a":"\xff"}\n',
        ):
            with self.subTest(content=content):
                with self.assertRaises(
                        release_review_rehearsal.ReviewRehearsalError):
                    release_review_rehearsal._decode_json(
                        content, "test receipt"
                    )

    def test_cli_preserves_blocked_status_and_pending_decisions(self):
        base = {
            "candidate_commit_sha": self.candidate,
            "component_statuses": {
                "operator_acceptance": "passed",
                "performance": "target_missed",
                "release_readiness": "review_inputs_complete",
                "threat_model": "model_complete",
            },
            "human_acceptance": "not_granted",
            "m4_decision": "pending",
            "m5_decision": "pending",
            "packet_status": "blocked_by_release_controls",
            "status": "blocked_by_release_controls",
        }
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            review = Path(directory) / "review"
            review.mkdir()
            (review / release_review_rehearsal.RECEIPT_NAME).write_bytes(b"{}\n")
            (review / release_review_rehearsal.PACKET_NAME).write_bytes(b"packet")
            with (
                patch.object(
                    release_review_rehearsal,
                    "prepare_review_rehearsal",
                    return_value=base,
                ),
                redirect_stdout(output),
            ):
                result = release_review_rehearsal.main([
                    "--candidate-commit", self.candidate,
                    "--output", str(review),
                ])
        self.assertEqual(1, result)
        self.assertIn("packet: blocked_by_release_controls", output.getvalue())
        self.assertIn("human acceptance remain pending", output.getvalue())

    def test_cli_reports_control_error_without_success_claim(self):
        output = io.StringIO()
        with (
            patch.object(
                release_review_rehearsal,
                "prepare_review_rehearsal",
                side_effect=release_review_rehearsal.ReviewRehearsalError(
                    "bad candidate"
                ),
            ),
            redirect_stderr(output),
        ):
            result = release_review_rehearsal.main([
                "--candidate-commit", self.candidate,
                "--output", "/tmp/chimera-review-test",
            ])
        self.assertEqual(2, result)
        self.assertIn("bad candidate", output.getvalue())
        self.assertNotIn("complete", output.getvalue().lower())

    def test_cli_maps_operational_io_failure_and_cleans_staging(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review = root / "review"
            with (
                patch.object(
                    operator_acceptance_prep,
                    "_validate_candidate_checkout",
                ),
                patch.object(
                    release_review_rehearsal.Path,
                    "chmod",
                    side_effect=OSError("injected staging permission failure"),
                ),
                redirect_stderr(output),
            ):
                result = release_review_rehearsal.main([
                    "--candidate-commit", self.candidate,
                    "--output", str(review),
                ])
            self.assertFalse(review.exists())
            self.assertEqual([], list(root.glob(".review.staging-*")))
        self.assertEqual(2, result)
        self.assertIn("injected staging permission failure", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_control_does_not_depend_on_removable_asserts(self):
        source = Path(
            release_review_rehearsal.__file__
        ).read_text(encoding="utf-8")
        self.assertFalse(
            any(
                isinstance(node, ast.Assert)
                for node in ast.walk(ast.parse(source))
            ),
            "review rehearsal controls must survive optimized Python",
        )
        workflow = (
            release_review_rehearsal.ROOT / ".github/workflows/test.yml"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "upload-artifact",
            "create-release",
            "deployment",
            "git tag",
            "git push",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()
