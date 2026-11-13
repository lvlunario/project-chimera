"""Protect the exact-SHA M4 engineering nomination boundary."""
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
    release_candidate_nomination,
    release_candidate_packet,
    release_performance,
    release_readiness,
    release_review_rehearsal,
    release_threat_model,
)


class ReleaseCandidateNominationTests(unittest.TestCase):
    candidate = "a" * 40
    rehearsal_generated = "2026-11-09T10:31:00Z"
    inspected = "2026-11-09T10:32:00Z"
    nominated = "2026-11-09T10:33:00Z"

    def _validators(self):
        tracked = release_readiness._tracked_repository_paths()
        tracked.update({
            "examples/release_candidate_nomination.py",
            "tests/test_release_candidate_nomination.py",
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
            patch.object(
                release_performance,
                "_run_workload",
                return_value={
                    "operator_run": release_performance._summary([1.0] * 10),
                    "handoff_round_trip": release_performance._summary(
                        [1.0] * 10
                    ),
                    "dashboard_snapshot": release_performance._summary(
                        [1.0] * 5
                    ),
                },
            ),
        )

    def _ci_document(self, candidate=None):
        selected = self.candidate if candidate is None else candidate
        jobs = [
            {"conclusion": "success", "name": name}
            for name in release_candidate_nomination._REQUIRED_JOBS
        ]
        return {
            "branch": release_candidate_nomination.DEVELOPMENT_BRANCH,
            "candidate_commit_sha": selected,
            "inspected_at_utc": self.inspected,
            "record_type": "chimera.github-actions-candidate-evidence",
            "repository": release_candidate_nomination.REPOSITORY,
            "runs": [
                {
                    "conclusion": "success",
                    "event": "push",
                    "jobs": jobs,
                    "run_id": 1001,
                    "run_url": (
                        "https://github.com/lvlunario/project-chimera/"
                        "actions/runs/1001"
                    ),
                    "source_candidate_commit_sha": selected,
                    "tested_commit_sha": selected,
                    "workflow_name": "test",
                },
                {
                    "conclusion": "success",
                    "event": "pull_request",
                    "jobs": deepcopy(jobs),
                    "run_id": 1002,
                    "run_url": (
                        "https://github.com/lvlunario/project-chimera/"
                        "actions/runs/1002"
                    ),
                    "source_candidate_commit_sha": selected,
                    "tested_commit_sha": "b" * 40,
                    "workflow_name": "test",
                },
            ],
            "schema_version": 1,
        }

    @staticmethod
    def _tree_bytes(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def _write_ci(self, path: Path, document=None):
        value = self._ci_document() if document is None else document
        path.write_bytes(release_candidate_nomination._canonical(value))

    def _fake_rehearsal(self, root: Path):
        rehearsal = root / "review"
        (rehearsal / "sources").mkdir(parents=True)
        (rehearsal / release_review_rehearsal.RECEIPT_NAME).write_bytes(
            b'{"receipt":"fixture"}\n'
        )
        (rehearsal / release_review_rehearsal.PACKET_NAME).write_bytes(
            b"packet fixture\n"
        )
        readiness = {
            "defects": {
                "open_count": 3,
                "open_release_blockers": [],
                "snapshot_age_at_assessment_seconds": 60,
                "snapshot_at_utc": "2026-11-09T10:24:30Z",
            }
        }
        (rehearsal / "sources/release-readiness.json").write_bytes(
            release_candidate_nomination._canonical(readiness)
        )
        receipt = {
            "candidate_commit_sha": self.candidate,
            "component_statuses": {
                "operator_acceptance": "passed",
                "performance": "passed",
                "release_readiness": "review_inputs_complete",
                "threat_model": "model_complete",
            },
            "generated_at_utc": self.rehearsal_generated,
            "packet_status": "packet_complete_for_m4_review",
            "release_blockers": [],
            "status": "packet_complete_for_m4_review",
        }
        return rehearsal, receipt

    def test_builds_and_reinspects_exact_candidate_nomination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review = root / "review"
            validators = self._validators()
            with (
                validators[0],
                validators[1],
                validators[2],
                validators[3],
                validators[4],
                validators[5],
                validators[6],
            ):
                release_review_rehearsal.prepare_review_rehearsal(
                    review,
                    candidate_commit=self.candidate,
                    generated_at_utc=self.rehearsal_generated,
                )
            ci_path = root / "ci.json"
            nomination_path = root / "nomination.json"
            self._write_ci(ci_path)
            record = release_candidate_nomination.nominate_candidate(
                nomination_path,
                rehearsal_directory=review,
                ci_evidence=ci_path,
                generated_at_utc=self.nominated,
            )

            self.assertEqual(self.candidate, record["candidate_commit_sha"])
            self.assertEqual(
                "nominated_for_m4_review", record["engineering_state"]
            )
            self.assertEqual("pending", record["m4_decision"])
            self.assertEqual("pending", record["m5_decision"])
            self.assertEqual("not_granted", record["human_acceptance"])
            self.assertEqual(
                {"p3": "pending", "p4": "pending", "p5": "pending"},
                record["phase_dispositions"],
            )
            self.assertEqual([], record["defect_snapshot"]["open_release_blockers"])
            self.assertGreaterEqual(
                record["defect_snapshot"][
                    "snapshot_age_at_nomination_seconds"
                ],
                0,
            )
            self.assertEqual(
                sha256(ci_path.read_bytes()).hexdigest(),
                record["hosted_ci"]["evidence_sha256"],
            )
            self.assertEqual(
                sha256(
                    (review / release_review_rehearsal.RECEIPT_NAME).read_bytes()
                ).hexdigest(),
                record["rehearsal"]["receipt"]["sha256"],
            )
            before = self._tree_bytes(review)
            self.assertEqual(
                record,
                release_candidate_nomination.inspect_candidate_nomination(
                    nomination_path,
                    rehearsal_directory=review,
                ),
            )
            self.assertEqual(before, self._tree_bytes(review))

            saved = nomination_path.read_bytes()
            self.assertEqual(record, json.loads(saved.decode("utf-8")))
            self.assertEqual(
                release_candidate_nomination._canonical(record), saved
            )

    def test_rejects_blocked_rehearsal_and_candidate_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review, receipt = self._fake_rehearsal(root)
            ci_path = root / "ci.json"
            self._write_ci(ci_path)

            blocked = deepcopy(receipt)
            blocked["status"] = "blocked_by_release_controls"
            blocked["packet_status"] = "blocked_by_release_controls"
            blocked["release_blockers"] = [
                "performance:operator_run_p95_ms"
            ]
            with (
                patch.object(
                    release_review_rehearsal,
                    "inspect_review_rehearsal",
                    return_value=blocked,
                ),
                self.assertRaisesRegex(
                    release_candidate_nomination.CandidateNominationError,
                    "blocked review rehearsal",
                ),
            ):
                release_candidate_nomination.nominate_candidate(
                    root / "blocked.json",
                    rehearsal_directory=review,
                    ci_evidence=ci_path,
                    generated_at_utc=self.nominated,
                )

            wrong = self._ci_document(candidate="c" * 40)
            self._write_ci(ci_path, wrong)
            with (
                patch.object(
                    release_review_rehearsal,
                    "inspect_review_rehearsal",
                    return_value=receipt,
                ),
                self.assertRaisesRegex(
                    release_candidate_nomination.CandidateNominationError,
                    "does not match",
                ),
            ):
                release_candidate_nomination.nominate_candidate(
                    root / "wrong.json",
                    rehearsal_directory=review,
                    ci_evidence=ci_path,
                    generated_at_utc=self.nominated,
                )

    def test_rejects_incomplete_or_misbound_hosted_ci(self):
        cases = {}
        failed = self._ci_document()
        failed["runs"][0]["conclusion"] = "failure"
        cases["did not complete"] = failed
        missing_job = self._ci_document()
        missing_job["runs"][1]["jobs"].pop()
        cases["required job inventory"] = missing_job
        wrong_push = self._ci_document()
        wrong_push["runs"][0]["tested_commit_sha"] = "d" * 40
        cases["did not test"] = wrong_push
        wrong_pr_source = self._ci_document()
        wrong_pr_source["runs"][1]["source_candidate_commit_sha"] = "d" * 40
        cases["commit identity"] = wrong_pr_source
        wrong_url = self._ci_document()
        wrong_url["runs"][0]["run_url"] = (
            "https://github.com/lvlunario/project-chimera/actions/runs/9"
        )
        cases["run URL"] = wrong_url
        huge_url = self._ci_document()
        huge_url["runs"][0]["run_url"] = (
            "https://github.com/lvlunario/project-chimera/actions/runs/"
            + ("9" * 5000)
        )
        cases["run URL.*"] = huge_url
        duplicate = self._ci_document()
        duplicate["runs"][1]["run_id"] = 1001
        duplicate["runs"][1]["run_url"] = (
            "https://github.com/lvlunario/project-chimera/actions/runs/1001"
        )
        cases["distinct"] = duplicate
        boolean = self._ci_document()
        boolean["runs"][0]["run_id"] = True
        boolean["runs"][0]["run_url"] = (
            "https://github.com/lvlunario/project-chimera/actions/runs/1"
        )
        cases["run ID"] = boolean

        for message, document in cases.items():
            with self.subTest(message=message):
                content = release_candidate_nomination._canonical(document)
                with self.assertRaisesRegex(
                    release_candidate_nomination.CandidateNominationError,
                    message,
                ):
                    release_candidate_nomination._validate_ci_document(
                        document, content
                    )

    def test_rejects_noncanonical_ci_duplicate_fields_and_bad_chronology(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review, receipt = self._fake_rehearsal(root)
            ci_path = root / "ci.json"
            output = root / "nomination.json"
            ci_path.write_bytes(b'{"schema_version":1, "schema_version":1}\n')
            with (
                patch.object(
                    release_review_rehearsal,
                    "inspect_review_rehearsal",
                    return_value=receipt,
                ),
                self.assertRaisesRegex(
                    release_candidate_nomination.CandidateNominationError,
                    "duplicate field",
                ),
            ):
                release_candidate_nomination.nominate_candidate(
                    output,
                    rehearsal_directory=review,
                    ci_evidence=ci_path,
                    generated_at_utc=self.nominated,
                )

            document = self._ci_document()
            ci_path.write_bytes(
                release_candidate_nomination._canonical(document)[:-1] + b" \n"
            )
            with (
                patch.object(
                    release_review_rehearsal,
                    "inspect_review_rehearsal",
                    return_value=receipt,
                ),
                self.assertRaisesRegex(
                    release_candidate_nomination.CandidateNominationError,
                    "not canonical",
                ),
            ):
                release_candidate_nomination.nominate_candidate(
                    output,
                    rehearsal_directory=review,
                    ci_evidence=ci_path,
                    generated_at_utc=self.nominated,
                )

            self._write_ci(ci_path)
            with (
                patch.object(
                    release_review_rehearsal,
                    "inspect_review_rehearsal",
                    return_value=receipt,
                ),
                self.assertRaisesRegex(
                    release_candidate_nomination.CandidateNominationError,
                    "chronology",
                ),
            ):
                release_candidate_nomination.nominate_candidate(
                    output,
                    rehearsal_directory=review,
                    ci_evidence=ci_path,
                    generated_at_utc="2026-11-09T10:31:30Z",
                )

    def test_inspection_rejects_tampered_authority_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review, receipt = self._fake_rehearsal(root)
            ci_path = root / "ci.json"
            output = root / "nomination.json"
            self._write_ci(ci_path)
            inspector = patch.object(
                release_review_rehearsal,
                "inspect_review_rehearsal",
                return_value=receipt,
            )
            with inspector:
                record = release_candidate_nomination.nominate_candidate(
                    output,
                    rehearsal_directory=review,
                    ci_evidence=ci_path,
                    generated_at_utc=self.nominated,
                )

            cases = []
            approved = deepcopy(record)
            approved["m4_decision"] = "approved"
            cases.append(("cannot record acceptance", approved))
            phase = deepcopy(record)
            phase["phase_dispositions"]["p5"] = "approved"
            cases.append(("cannot disposition", phase))
            age = deepcopy(record)
            age["defect_snapshot"]["snapshot_age_at_nomination_seconds"] += 1
            cases.append(("defect snapshot changed", age))
            boolean_count = deepcopy(record)
            boolean_count["defect_snapshot"]["open_count"] = True
            cases.append(("open defect count is invalid", boolean_count))
            boolean_blocker = deepcopy(record)
            boolean_blocker["defect_snapshot"]["open_release_blockers"] = [True]
            cases.append(("blocker inventory is invalid", boolean_blocker))
            ci = deepcopy(record)
            ci["hosted_ci"]["runs"][0]["jobs"][0]["conclusion"] = "failure"
            cases.append(("identity changed", ci))
            rehearsal_changed = deepcopy(record)
            rehearsal_changed["rehearsal"]["packet"]["sha256"] = "0" * 64
            cases.append(("rehearsal evidence changed", rehearsal_changed))

            for message, changed in cases:
                with self.subTest(message=message):
                    output.write_bytes(
                        release_candidate_nomination._canonical(changed)
                    )
                    with (
                        patch.object(
                            release_review_rehearsal,
                            "inspect_review_rehearsal",
                            return_value=receipt,
                        ),
                        self.assertRaisesRegex(
                            release_candidate_nomination.CandidateNominationError,
                            message,
                        ),
                    ):
                        release_candidate_nomination.inspect_candidate_nomination(
                            output,
                            rehearsal_directory=review,
                        )

    def test_refuses_existing_checkout_rehearsal_and_symlink_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review, receipt = self._fake_rehearsal(root)
            ci_path = root / "ci.json"
            self._write_ci(ci_path)
            existing = root / "existing.json"
            existing.write_text("keep\n", encoding="utf-8")
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(root, target_is_directory=True)
            inspector = patch.object(
                release_review_rehearsal,
                "inspect_review_rehearsal",
                return_value=receipt,
            )
            for path, message in (
                (existing, "already exists"),
                (review / "nomination.json", "outside the checkout and rehearsal"),
                (linked_parent / "nomination.json", "parent is unavailable"),
            ):
                with self.subTest(path=path), inspector:
                    with self.assertRaisesRegex(
                        release_candidate_nomination.CandidateNominationError,
                        message,
                    ):
                        release_candidate_nomination.nominate_candidate(
                            path,
                            rehearsal_directory=review,
                            ci_evidence=ci_path,
                            generated_at_utc=self.nominated,
                        )
            self.assertEqual("keep\n", existing.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review, receipt = self._fake_rehearsal(root)
            ci_path = root / "ci.json"
            self._write_ci(ci_path)
            with (
                patch.object(
                    release_review_rehearsal,
                    "inspect_review_rehearsal",
                    return_value=receipt,
                ),
                self.assertRaisesRegex(
                    release_candidate_nomination.CandidateNominationError,
                    "outside the checkout",
                ),
            ):
                release_candidate_nomination.nominate_candidate(
                    release_candidate_nomination.ROOT / "forbidden-nomination.json",
                    rehearsal_directory=review,
                    ci_evidence=ci_path,
                    generated_at_utc=self.nominated,
                )

    def test_parent_swap_cannot_redirect_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review, receipt = self._fake_rehearsal(root)
            ci_path = root / "ci.json"
            self._write_ci(ci_path)
            safe = root / "safe"
            safe.mkdir()
            original = root / "safe-original"
            redirected = root / "redirected"
            redirected.mkdir()
            output = safe / "nomination.json"
            validate = release_candidate_nomination._validate_nomination
            calls = 0

            def swap_parent(record, **kwargs):
                nonlocal calls
                result = validate(record, **kwargs)
                calls += 1
                if calls == 1:
                    safe.rename(original)
                    safe.symlink_to(redirected, target_is_directory=True)
                return result

            with (
                patch.object(
                    release_review_rehearsal,
                    "inspect_review_rehearsal",
                    return_value=receipt,
                ),
                patch.object(
                    release_candidate_nomination,
                    "_validate_nomination",
                    side_effect=swap_parent,
                ),
                self.assertRaisesRegex(
                    release_candidate_nomination.CandidateNominationError,
                    "parent changed during publication",
                ),
            ):
                release_candidate_nomination.nominate_candidate(
                    output,
                    rehearsal_directory=review,
                    ci_evidence=ci_path,
                    generated_at_utc=self.nominated,
                )

            self.assertFalse((original / output.name).exists())
            self.assertFalse((redirected / output.name).exists())

    def test_cli_inspects_without_writes_and_maps_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review, receipt = self._fake_rehearsal(root)
            ci_path = root / "ci.json"
            output = root / "nomination.json"
            self._write_ci(ci_path)
            with patch.object(
                release_review_rehearsal,
                "inspect_review_rehearsal",
                return_value=receipt,
            ):
                release_candidate_nomination.nominate_candidate(
                    output,
                    rehearsal_directory=review,
                    ci_evidence=ci_path,
                    generated_at_utc=self.nominated,
                )
            before = self._tree_bytes(root)
            stdout = io.StringIO()
            with (
                patch.object(
                    release_review_rehearsal,
                    "inspect_review_rehearsal",
                    return_value=receipt,
                ),
                redirect_stdout(stdout),
            ):
                result = release_candidate_nomination.main([
                    "inspect", str(output), "--rehearsal", str(review)
                ])
            self.assertEqual(0, result)
            self.assertIn("engineering-state: nominated_for_m4_review", stdout.getvalue())
            self.assertIn("human acceptance remain pending", stdout.getvalue())
            self.assertEqual(before, self._tree_bytes(root))

            output.write_text("{}\n", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = release_candidate_nomination.main([
                    "inspect", str(output), "--rehearsal", str(review)
                ])
            self.assertEqual(2, result)
            self.assertIn("fields changed", stderr.getvalue())
            self.assertNotIn("human acceptance remain pending", stderr.getvalue())

            output.write_bytes(
                b'{"schema_version":' + (b"9" * 5000) + b"}\n"
            )
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = release_candidate_nomination.main([
                    "inspect", str(output), "--rehearsal", str(review)
                ])
            self.assertEqual(2, result)
            self.assertIn("invalid JSON", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

            output.write_bytes(
                b'{"schema_version":'
                + (b"[" * 994)
                + b"0"
                + (b"]" * 994)
                + b"}\n"
            )
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = release_candidate_nomination.main([
                    "inspect", str(output), "--rehearsal", str(review)
                ])
            self.assertEqual(2, result)
            self.assertRegex(
                stderr.getvalue(),
                r"candidate nomination is (invalid|not canonical) JSON",
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def _assert_retained_nomination(
        self,
        *,
        name,
        nomination_sha,
        candidate_sha,
        expected_evidence_sha,
        receipt,
        packet,
    ):
        path = (
            release_candidate_nomination.ROOT
            / "docs"
            / name
        )
        record, content = release_candidate_nomination._load_canonical(
            path,
            release_candidate_nomination.MAX_JSON_BYTES,
            "retained candidate nomination",
        )

        self.assertEqual(
            nomination_sha,
            sha256(content).hexdigest(),
            "the retained nomination must be superseded, never edited in place",
        )
        self.assertEqual(candidate_sha, record["candidate_commit_sha"])
        self.assertEqual(
            "nominated_for_m4_review", record["engineering_state"]
        )
        self.assertEqual("pending", record["m4_decision"])
        self.assertEqual("pending", record["m5_decision"])
        self.assertEqual("not_granted", record["human_acceptance"])
        self.assertEqual(
            {"p3": "pending", "p4": "pending", "p5": "pending"},
            record["phase_dispositions"],
        )
        self.assertEqual(
            release_candidate_nomination.CANDIDATE_CHANGE_POLICY,
            record["candidate_change_policy"],
        )
        self.assertEqual(
            release_candidate_nomination.SCOPE, record["scope"]
        )

        hosted, evidence_sha = release_candidate_nomination._embedded_ci(
            record["hosted_ci"]
        )
        self.assertEqual(
            record["candidate_commit_sha"], hosted["candidate_commit_sha"]
        )
        self.assertEqual(
            ["push", "pull_request"],
            [run["event"] for run in hosted["runs"]],
        )
        self.assertEqual(
            expected_evidence_sha,
            evidence_sha,
        )
        self.assertEqual(receipt, record["rehearsal"]["receipt"])
        self.assertEqual(packet, record["rehearsal"]["packet"])
        self.assertEqual([], record["defect_snapshot"]["open_release_blockers"])

    def test_retained_nomination_records_are_pinned_and_authority_free(self):
        self._assert_retained_nomination(
            name="m4-candidate-nomination-v1.json",
            nomination_sha=(
                "061ded7ead70501da0d748ff333936d54dd095bffc157090508c80fbd8183529"
            ),
            candidate_sha="04606a4b87c270fdce37fd3673ec18c74af82a54",
            expected_evidence_sha=(
                "229c878024a4ff7ed463d19ea4b6abfe1c24d86ac322db1718a89b068450b5ba"
            ),
            receipt={
                "byte_count": 6499,
                "sha256": "d09457933ebe257ec31eeeabd068c7310bfca56f0851949b8543411ac1606e43",
            },
            packet={
                "byte_count": 495356,
                "sha256": "a40e9a84a4bd4d8bbc631f61366cdc0a3338075d9514e23f8a08b0a43e2fa774",
            },
        )
        self._assert_retained_nomination(
            name="m4-candidate-nomination-v2.json",
            nomination_sha=(
                "0d4ed3702e09939d5cce996cd1c0e2b4e105fda179274b91265de21252ecf3f4"
            ),
            candidate_sha="594b03c2a7fcd62548d9eea8b3f7a73f8584555d",
            expected_evidence_sha=(
                "cee2248612063efd724b32b7716324be8f270aec81dad63a8baa9e4d9b6aede4"
            ),
            receipt={
                "byte_count": 6499,
                "sha256": "5538da435e66445b27314525ed2f0b306fa6f16ef9ba2adf521a60b0d20db7ff",
            },
            packet={
                "byte_count": 498309,
                "sha256": "c9d8ebf40c249f19ccedd270c7de0ca357a794b3ed5a28553f4832b8bdf745da",
            },
        )

    def test_control_does_not_depend_on_removable_asserts(self):
        source = Path(release_candidate_nomination.__file__).read_text(
            encoding="utf-8"
        )
        self.assertFalse(
            any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(source))),
            "candidate nomination controls must survive optimized Python",
        )


if __name__ == "__main__":
    unittest.main()
