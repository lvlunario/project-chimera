"""Protect the exact-candidate P7 release-readiness inventory control."""
import ast
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from examples import release_readiness


class ReleaseReadinessTests(unittest.TestCase):
    candidate = "a" * 40

    @classmethod
    def setUpClass(cls):
        cls.document, cls.manifest_content = release_readiness._load_canonical_json(
            release_readiness.MANIFEST_PATH, 262_144
        )
        cls.tracked = release_readiness._tracked_repository_paths()
        cls.tracked.update({
            "docs/release-readiness-v1.json",
            "examples/release_candidate_packet.py",
            "examples/release_readiness.py",
            "tests/test_release_candidate_packet.py",
            "tests/test_release_readiness.py",
        })
        cls.requirements = release_readiness._declared_requirement_ids()

    def _validate(self, document=None):
        return release_readiness._validate_manifest(
            self.document if document is None else document,
            tracked_paths=self.tracked,
            requirement_ids=self.requirements,
        )

    def test_checked_in_manifest_covers_current_review_inputs(self):
        summary = self._validate()
        self.assertEqual(122, summary["requirement_count"])
        self.assertEqual(21, summary["requirement_group_count"])
        self.assertEqual(2, summary["defect_count"])
        self.assertEqual([], summary["open_release_blockers"])
        self.assertEqual(6, summary["guide_count"])
        self.assertEqual(49, summary["guide_heading_count"])
        self.assertGreaterEqual(len(summary["evidence_files"]), 35)
        self.assertTrue(all(
            item["byte_count"] > 0 and len(item["sha256"]) == 64
            for item in summary["evidence_files"]
        ))
        evidence_paths = {item["path"] for item in summary["evidence_files"]}
        self.assertIn("docs/REQUIREMENTS.md", evidence_paths)
        self.assertIn("docs/release-readiness-v1.json", evidence_paths)
        self.assertEqual(
            list(release_readiness._PENDING_HUMAN_EVIDENCE),
            summary["pending_human_evidence"],
        )

    def test_publishes_canonical_candidate_bound_review_index(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release-readiness.json"
            with (
                patch.object(release_readiness, "_validate_candidate_checkout")
                    as validate_candidate,
                patch.object(
                    release_readiness,
                    "_tracked_repository_paths",
                    return_value=self.tracked,
                ),
            ):
                record = release_readiness.assess_release_readiness(
                    output,
                    candidate_commit=self.candidate,
                    generated_at_utc="2026-10-29T11:00:00Z",
                )
            self.assertEqual(2, validate_candidate.call_count)
            self.assertEqual("review_inputs_complete", record["status"])
            self.assertEqual(self.candidate, record["candidate_commit_sha"])
            self.assertEqual("pending", record["m4_decision"])
            self.assertEqual("pending", record["m5_decision"])
            self.assertEqual("not_granted", record["human_acceptance"])
            self.assertEqual(122, record["requirements"]["declared_count"])
            self.assertEqual(122, record["requirements"]["covered_count"])
            self.assertEqual(2, record["defects"]["open_count"])
            self.assertEqual([], record["defects"]["open_release_blockers"])
            self.assertEqual(
                release_readiness.hashlib.sha256(
                    self.manifest_content
                ).hexdigest(),
                record["manifest"]["sha256"],
            )
            self.assertEqual(record, json.loads(output.read_text(encoding="utf-8")))
            self.assertEqual(release_readiness._canonical(record), output.read_bytes())

            original = output.read_bytes()
            with patch.object(release_readiness, "_validate_candidate_checkout"):
                with self.assertRaisesRegex(
                        release_readiness.ReleaseReadinessError, "already exists"):
                    release_readiness.assess_release_readiness(
                        output, candidate_commit=self.candidate
                    )
            self.assertEqual(original, output.read_bytes())

    def test_parser_rejects_duplicate_noncanonical_and_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = {
                "duplicate.json": b'{"a":1,"a":2}\n',
                "noncanonical.json": b'{"a": 1}\n',
                "invalid-utf8.json": b'{"a":"\xff"}\n',
                "nonfinite.json": b'{"a":NaN}\n',
                "lone-surrogate.json": b'{"a":"\\ud800"}\n',
                "nested.json": (b'{"a":' * 1_000) + b'0' + (b'}' * 1_000) + b'\n',
            }
            for name, content in cases.items():
                with self.subTest(name=name):
                    path = root / name
                    path.write_bytes(content)
                    with self.assertRaises(release_readiness.ReleaseReadinessError):
                        release_readiness._load_canonical_json(
                            path, 100_000 if name == "nested.json" else 1_024
                        )

    def test_rejects_missing_duplicate_and_unknown_requirement_coverage(self):
        missing = deepcopy(self.document)
        missing["requirement_groups"][14]["requirement_ids"].pop()
        duplicate = deepcopy(self.document)
        duplicate["requirement_groups"][14]["requirement_ids"].append("READINESS-004")
        unknown = deepcopy(self.document)
        unknown["requirement_groups"][14]["requirement_ids"].append("READINESS-999")
        for name, document in (
            ("missing", missing), ("duplicate", duplicate), ("unknown", unknown),
        ):
            with self.subTest(name=name):
                with self.assertRaises(release_readiness.ReleaseReadinessError):
                    self._validate(document)

    def test_rejects_untracked_traversing_and_nonregular_evidence(self):
        cases = []
        untracked = deepcopy(self.document)
        untracked["requirement_groups"][0]["evidence_paths"][0] = "missing.txt"
        cases.append(("untracked", untracked, self.tracked))
        traversing = deepcopy(self.document)
        traversing["requirement_groups"][0]["evidence_paths"][0] = "../README.md"
        cases.append(("traversal", traversing, self.tracked | {"../README.md"}))
        directory = deepcopy(self.document)
        directory["requirement_groups"][0]["evidence_paths"][0] = "docs"
        cases.append(("directory", directory, self.tracked | {"docs"}))
        for name, document, tracked in cases:
            with self.subTest(name=name):
                with self.assertRaises(release_readiness.ReleaseReadinessError):
                    release_readiness._validate_manifest(
                        document,
                        tracked_paths=tracked,
                        requirement_ids=self.requirements,
                    )

    def test_rejects_missing_and_out_of_order_guide_headings(self):
        missing = deepcopy(self.document)
        missing["guide_checks"][0]["required_headings"][1] = "## Missing heading"
        out_of_order = deepcopy(self.document)
        headings = out_of_order["guide_checks"][0]["required_headings"]
        headings[1], headings[2] = headings[2], headings[1]
        for name, document in (("missing", missing), ("order", out_of_order)):
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                        release_readiness.ReleaseReadinessError, "missing required heading"):
                    self._validate(document)

    def test_rejects_stale_or_inconsistent_defect_disposition(self):
        closed = deepcopy(self.document)
        closed["defect_snapshot"]["open_defects"][0]["github_state"] = "closed"
        inconsistent = deepcopy(self.document)
        inconsistent["defect_snapshot"]["open_defects"][0]["release_blocker"] = True
        mismatch = deepcopy(self.document)
        mismatch["defect_snapshot"]["open_defects"][0][
            "engineering_disposition"
        ] = "unresolved"
        mismatch["defect_snapshot"]["open_defects"][0]["release_blocker"] = True
        for name, document in (
            ("closed", closed), ("inconsistent", inconsistent), ("mismatch", mismatch),
        ):
            with self.subTest(name=name):
                with self.assertRaises(release_readiness.ReleaseReadinessError):
                    self._validate(document)

    def test_rejects_weakened_defect_and_guide_inventories(self):
        no_defects = deepcopy(self.document)
        no_defects["defect_snapshot"]["open_defects"] = []
        one_guide = deepcopy(self.document)
        one_guide["guide_checks"] = one_guide["guide_checks"][:1]
        for name, document in (("defects", no_defects), ("guides", one_guide)):
            with self.subTest(name=name):
                with self.assertRaises(release_readiness.ReleaseReadinessError):
                    self._validate(document)

    def test_rejects_defect_snapshot_later_than_assessment(self):
        document = deepcopy(self.document)
        document["defect_snapshot"]["observed_at_utc"] = "9999-12-31T23:59:59Z"
        summary = self._validate(document)
        with self.assertRaisesRegex(
                release_readiness.ReleaseReadinessError, "cannot be later"):
            release_readiness._build_assessment(
                candidate_commit=self.candidate,
                generated_at_utc="2026-10-29T11:00:00Z",
                manifest_content=self.manifest_content,
                summary=summary,
            )

    def test_unresolved_defect_is_retained_and_returns_blocked(self):
        document = deepcopy(self.document)
        defect = document["defect_snapshot"]["open_defects"][0]
        defect["engineering_disposition"] = "unresolved"
        defect["release_blocker"] = True
        document["release_review"]["open_release_blockers"] = [4]
        summary = self._validate(document)
        record = release_readiness._build_assessment(
            candidate_commit=self.candidate,
            generated_at_utc="2026-10-29T11:00:00Z",
            manifest_content=self.manifest_content,
            summary=summary,
        )
        self.assertEqual("release_blockers_present", record["status"])
        self.assertEqual([4], record["defects"]["open_release_blockers"])
        check = {item["id"]: item for item in record["checks"]}
        self.assertEqual("blocked", check["READINESS-002"]["status"])
        output = io.StringIO()
        with (
            patch.object(
                release_readiness, "assess_release_readiness", return_value=record
            ),
            redirect_stdout(output),
        ):
            result = release_readiness.main([
                "--candidate-commit", self.candidate,
                "--output", "/tmp/release-readiness.json",
            ])
        self.assertEqual(1, result)
        self.assertIn("BLOCKED READINESS-002:", output.getvalue())

    def test_candidate_validation_rejects_wrong_dirty_and_invalid_commits(self):
        clean_head = subprocess.CompletedProcess([], 0, stdout=self.candidate + "\n")
        clean_status = subprocess.CompletedProcess([], 0, stdout="")
        with patch.object(
            release_readiness, "_git", side_effect=[clean_head, clean_status]
        ):
            release_readiness._validate_candidate_checkout(self.candidate)
        for name, commit, results in (
            ("invalid", "ABC", []),
            ("wrong", self.candidate, [subprocess.CompletedProcess([], 0, stdout="b" * 40)]),
            ("dirty", self.candidate, [clean_head, subprocess.CompletedProcess([], 0, stdout=" M README.md\n")]),
        ):
            with self.subTest(name=name):
                with patch.object(release_readiness, "_git", side_effect=results):
                    with self.assertRaises(release_readiness.ReleaseReadinessError):
                        release_readiness._validate_candidate_checkout(commit)

    def test_output_publication_failure_leaves_no_partial_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "failed.json"
            with patch.object(release_readiness.os, "link", side_effect=OSError("no")):
                with self.assertRaisesRegex(
                        release_readiness.ReleaseReadinessError, "cannot publish"):
                    release_readiness._write_record(target, {"ok": True})
            self.assertFalse(target.exists())
            self.assertEqual([], list(root.glob(".failed.json.*.tmp")))

    def test_control_survives_optimized_python(self):
        source = Path(release_readiness.__file__).read_text(encoding="utf-8")
        self.assertFalse(
            any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(source))),
            "release-readiness controls must not depend on removable assert statements",
        )

    def test_cli_uses_pass_label_without_claiming_acceptance(self):
        record = release_readiness._build_assessment(
            candidate_commit=self.candidate,
            generated_at_utc="2026-10-29T11:00:00Z",
            manifest_content=self.manifest_content,
            summary=self._validate(),
        )
        output = io.StringIO()
        with (
            patch.object(
                release_readiness, "assess_release_readiness", return_value=record
            ),
            redirect_stdout(output),
        ):
            result = release_readiness.main([
                "--candidate-commit", self.candidate,
                "--output", "/tmp/release-readiness.json",
            ])
        self.assertEqual(0, result)
        rendered = output.getvalue()
        self.assertIn("PASS READINESS-001:", rendered)
        self.assertIn("M4/M5 decisions and human acceptance remain pending", rendered)
        self.assertNotIn("release approved", rendered.lower())


if __name__ == "__main__":
    unittest.main()
