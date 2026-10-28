"""Protect the exact-candidate P7 threat-model control."""
import ast
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from examples import release_threat_model


class ReleaseThreatModelTests(unittest.TestCase):
    candidate = "a" * 40

    @classmethod
    def setUpClass(cls):
        cls.document, cls.model_content = release_threat_model._load_canonical_json(
            release_threat_model.MODEL_PATH, 262_144
        )
        tracked = release_threat_model._tracked_repository_paths()
        tracked.add(release_threat_model.MODEL_REPOSITORY_PATH)
        tracked.add("tests/test_release_threat_model.py")
        cls.tracked = tracked
        cls.requirements = release_threat_model._declared_requirement_ids()

    def _validate(self, document=None):
        return release_threat_model._validate_model(
            self.document if document is None else document,
            tracked_paths=self.tracked,
            requirement_ids=self.requirements,
        )

    def test_checked_in_model_is_canonical_complete_and_traceable(self):
        summary = self._validate()
        self.assertEqual(7, summary["asset_count"])
        self.assertEqual(5, summary["actor_count"])
        self.assertEqual(6, summary["trust_boundary_count"])
        self.assertEqual(10, summary["threat_count"])
        self.assertEqual(17, summary["control_count"])
        self.assertGreaterEqual(len(summary["evidence_files"]), 20)
        self.assertEqual([], summary["must_fix_before_m4"])
        self.assertEqual(10, summary["disposition_counts"]["tracked_for_m4"])
        self.assertTrue(all(
            len(item["sha256"]) == 64 and item["byte_count"] > 0
            for item in summary["evidence_files"]
        ))
        risks = {item["id"]: item for item in self.document["threats"]}
        self.assertEqual(
            [f"ASSET-{index:03d}" for index in range(1, 7)],
            risks["RISK-008"]["asset_ids"],
        )
        assets = {item["id"]: item for item in self.document["assets"]}
        for asset_id in ("ASSET-001", "ASSET-002", "ASSET-003", "ASSET-004",
                         "ASSET-005", "ASSET-006"):
            self.assertIn("confidentiality", assets[asset_id]["security_properties"])

    def test_publishes_canonical_candidate_bound_reference_assessment(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "threat-assessment.json"
            with (
                patch.object(release_threat_model, "_validate_candidate_checkout")
                    as validate_candidate,
                patch.object(
                    release_threat_model,
                    "_tracked_repository_paths",
                    return_value=self.tracked,
                ),
            ):
                record = release_threat_model.assess_threat_model(
                    output,
                    candidate_commit=self.candidate,
                    generated_at_utc="2026-10-28T10:00:00Z",
                )
            self.assertEqual(2, validate_candidate.call_count)
            self.assertEqual("model_complete", record["status"])
            self.assertEqual(self.candidate, record["candidate_commit_sha"])
            self.assertEqual("pending_m4_review", record["release_decision"])
            self.assertEqual("not_granted", record["human_acceptance"])
            self.assertEqual([], record["must_fix_before_m4"])
            self.assertEqual(
                release_threat_model.hashlib.sha256(self.model_content).hexdigest(),
                record["model"]["sha256"],
            )
            self.assertIn("not a penetration test", record["scope"])
            self.assertEqual(record, json.loads(output.read_text(encoding="utf-8")))
            self.assertEqual(release_threat_model._canonical(record), output.read_bytes())

            original = output.read_bytes()
            with patch.object(release_threat_model, "_validate_candidate_checkout"):
                with self.assertRaisesRegex(
                        release_threat_model.ThreatModelError, "already exists"):
                    release_threat_model.assess_threat_model(
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
                    with self.assertRaises(release_threat_model.ThreatModelError):
                        release_threat_model._load_canonical_json(
                            path, 100_000 if name == "nested.json" else 1024
                        )

    def test_model_rejects_schema_reference_trace_and_disposition_gaps(self):
        mutations = []

        boolean_version = deepcopy(self.document)
        boolean_version["schema_version"] = True
        mutations.append((boolean_version, "schema version"))

        unknown_field = deepcopy(self.document)
        unknown_field["unexpected"] = "value"
        mutations.append((unknown_field, "fields changed"))

        unknown_asset = deepcopy(self.document)
        unknown_asset["threats"][0]["asset_ids"] = ["ASSET-999"]
        mutations.append((unknown_asset, "unknown asset"))

        no_residual = deepcopy(self.document)
        no_residual["threats"][0]["residual_risk"] = ""
        mutations.append((no_residual, "nonempty trimmed"))

        bad_requirement = deepcopy(self.document)
        bad_requirement["threats"][0]["controls"][0]["requirement_ids"] = [
            "MISSING-999"
        ]
        mutations.append((bad_requirement, "undeclared requirement"))

        traversal = deepcopy(self.document)
        traversal["threats"][0]["controls"][0]["evidence_paths"] = [
            "../outside.py"
        ]
        mutations.append((traversal, "traverse"))

        mismatch = deepcopy(self.document)
        mismatch["threats"][0]["engineering_disposition"] = "must_fix_before_m4"
        mutations.append((mismatch, "blocker list"))

        missing_likelihood = deepcopy(self.document)
        del missing_likelihood["threats"][0]["likelihood"]
        mutations.append((missing_likelihood, "fields changed"))

        changed_scope = deepcopy(self.document)
        changed_scope["scope"]["assumptions"][0] = "An unrelated assumption"
        mutations.append((changed_scope, "scope.assumptions changed"))

        nontext_enum = deepcopy(self.document)
        nontext_enum["actors"][0]["trust"] = []
        mutations.append((nontext_enum, "must be text"))

        nontext_category = deepcopy(self.document)
        nontext_category["threats"][0]["category"] = []
        mutations.append((nontext_category, "must be text"))

        nontext_disposition = deepcopy(self.document)
        nontext_disposition["threats"][0]["engineering_disposition"] = []
        mutations.append((nontext_disposition, "must be text"))

        for document, message in mutations:
            with self.subTest(message=message):
                with self.assertRaisesRegex(
                        release_threat_model.ThreatModelError, message):
                    self._validate(document)

    def test_evidence_paths_reject_escape_url_untracked_directory_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regular = root / "regular.txt"
            regular.write_text("evidence", encoding="utf-8")
            folder = root / "folder"
            folder.mkdir()
            link = root / "link.txt"
            link.symlink_to(regular)
            tracked = {"regular.txt", "folder", "link.txt"}
            with patch.object(release_threat_model, "ROOT", root):
                path, identity = release_threat_model._evidence_file(
                    "regular.txt", "evidence", tracked
                )
                self.assertEqual("regular.txt", path)
                self.assertEqual(8, identity["byte_count"])
                for value, message in (
                    ("/absolute.txt", "traverse"),
                    ("../outside.txt", "traverse"),
                    ("folder\\file.txt", "POSIX"),
                    ("https://example.test/file", "POSIX"),
                    ("untracked.txt", "not tracked"),
                    ("folder", "regular file"),
                    ("link.txt", "regular file"),
                ):
                    with self.subTest(value=value):
                        with self.assertRaisesRegex(
                                release_threat_model.ThreatModelError, message):
                            release_threat_model._evidence_file(
                                value, "evidence", tracked
                            )

    def test_m4_blocker_produces_retained_blocked_assessment(self):
        document = deepcopy(self.document)
        document["threats"][0]["engineering_disposition"] = "must_fix_before_m4"
        document["release_review"]["must_fix_before_m4"] = ["RISK-001"]
        summary = self._validate(document)
        record = release_threat_model._build_assessment(
            candidate_commit=self.candidate,
            generated_at_utc="2026-10-28T10:00:00Z",
            model_content=release_threat_model._canonical(document),
            summary=summary,
        )
        self.assertEqual("blocked_by_open_release_threat", record["status"])
        self.assertEqual(["RISK-001"], record["must_fix_before_m4"])
        self.assertEqual("blocked", record["checks"][-1]["status"])

    def test_candidate_validation_fails_closed(self):
        for candidate in ("", "abc", "A" * 40, "g" * 40):
            with self.subTest(candidate=candidate):
                with patch.object(release_threat_model, "_git") as git:
                    with self.assertRaisesRegex(
                            release_threat_model.ThreatModelError, "full lowercase"):
                        release_threat_model._validate_candidate_checkout(candidate)
                    git.assert_not_called()

        head = subprocess.CompletedProcess(
            ["git"], 0, stdout=self.candidate + "\n", stderr=""
        )
        dirty = subprocess.CompletedProcess(
            ["git"], 0, stdout="?? result.json\n", stderr=""
        )
        with patch.object(
                release_threat_model, "_git", side_effect=[head, dirty]):
            with self.assertRaisesRegex(
                    release_threat_model.ThreatModelError, "clean checkout"):
                release_threat_model._validate_candidate_checkout(self.candidate)

        wrong = subprocess.CompletedProcess(
            ["git"], 0, stdout="b" * 40 + "\n", stderr=""
        )
        with patch.object(release_threat_model, "_git", return_value=wrong):
            with self.assertRaisesRegex(
                    release_threat_model.ThreatModelError, "exact checked-out"):
                release_threat_model._validate_candidate_checkout(self.candidate)

    def test_output_boundary_rejects_symlinks_checkout_and_publication_race(self):
        checkout_output = release_threat_model.ROOT / "threat-assessment.json"
        with patch.object(release_threat_model, "_validate_candidate_checkout"):
            with self.assertRaisesRegex(
                    release_threat_model.ThreatModelError, "outside"):
                release_threat_model.assess_threat_model(
                    checkout_output, candidate_commit=self.candidate
                )
        self.assertFalse(checkout_output.exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_parent = root / "real"
            real_parent.mkdir()
            linked_parent = root / "linked"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with patch.object(release_threat_model, "_validate_candidate_checkout"):
                with self.assertRaisesRegex(
                        release_threat_model.ThreatModelError, "parent"):
                    release_threat_model.assess_threat_model(
                        linked_parent / "result.json", candidate_commit=self.candidate
                    )

            target = root / "raced.json"
            record = {"schema_version": 1}

            def race(_source, destination):
                Path(destination).write_bytes(b"raced")
                raise FileExistsError

            with patch.object(os, "link", side_effect=race):
                with self.assertRaisesRegex(
                        release_threat_model.ThreatModelError, "already exists"):
                    release_threat_model._write_record(target, record)
            self.assertEqual(b"raced", target.read_bytes())
            self.assertEqual([], list(root.glob(".raced.json.*.tmp")))

            failed_target = root / "write-failed.json"
            with patch.object(os, "fsync", side_effect=OSError("injected")):
                with self.assertRaisesRegex(
                        release_threat_model.ThreatModelError, "cannot publish"):
                    release_threat_model._write_record(failed_target, record)
            self.assertFalse(failed_target.exists())
            self.assertEqual([], list(root.glob(".write-failed.json.*.tmp")))

    def test_control_survives_optimized_python(self):
        source = Path(release_threat_model.__file__).read_text(encoding="utf-8")
        self.assertFalse(
            any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(source))),
            "threat-model controls must not depend on removable assert statements",
        )


if __name__ == "__main__":
    unittest.main()
