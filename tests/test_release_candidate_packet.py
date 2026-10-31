"""Protect the exact-candidate M4 evidence-packet boundary."""
import ast
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from examples import operator_acceptance_prep, release_candidate_packet


class ReleaseCandidatePacketTests(unittest.TestCase):
    candidate = "a" * 40
    generated = "2026-10-30T10:00:00Z"
    source_generated = "2026-10-30T09:59:00Z"

    def _acceptance_workspace(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        workspace = root / "acceptance"
        with patch.object(
                operator_acceptance_prep, "_validate_candidate_checkout"):
            operator_acceptance_prep.prepare_acceptance(
                workspace,
                candidate_commit=self.candidate,
                generated_at_utc=self.source_generated,
            )
        return workspace

    def _records(self, root: Path) -> tuple[Path, Path, Path]:
        candidate_files = {
            relative: (release_candidate_packet.ROOT / relative).read_bytes()
            for relative in release_candidate_packet.CANDIDATE_FILES
        }
        performance = {
            "schema_version": 1,
            "record_type": "chimera.release-performance-baseline",
            "workload_version": "p7-local-prototype-v1",
            "candidate_commit_sha": self.candidate,
            "candidate_checks": {
                "before_measurement": "matched_clean_head",
                "before_publication": "matched_clean_head",
            },
            "generated_at_utc": self.source_generated,
            "clock": "time.perf_counter_ns monotonic elapsed time",
            "environment": {
                "python_implementation": "CPython",
                "python_version": "3.12.0",
                "operating_system": "Linux",
                "kernel_release": "test",
                "machine": "x86_64",
                "logical_cpu_count": 2,
            },
            "workload": {
                "source": "generated synthetic communications CSV",
                "sample_count": 10_000,
                "workspace_runs": 10,
                "handoff_iterations": 10,
                "dashboard_iterations": 5,
                "threshold_db": "3.0",
                "minimum_link_margin_db": "2.0",
                "expected_verdict": "fail",
            },
            "targets_ms": {
                name: target for name, (_, target) in
                release_candidate_packet.PERFORMANCE_METRICS.items()
            },
            "measurements": {
                group: {
                    "samples_ms": [1.0] * (
                        5 if group == "dashboard_snapshot" else 10
                    ),
                    "p50_ms": 1.0,
                    "p95_ms": 1.0,
                    "max_ms": 1.0,
                }
                for group, _ in release_candidate_packet.PERFORMANCE_METRICS.values()
            },
            "target_results": {
                name: {
                    "observed_ms": 1.0,
                    "target_ms": target,
                    "status": "passed",
                }
                for name, (_, target) in
                release_candidate_packet.PERFORMANCE_METRICS.items()
            },
            "status": "passed",
            "scope": release_candidate_packet.PERFORMANCE_SCOPE,
        }
        threat_model = candidate_files["docs/threat-model-v1.json"]
        threat_document = json.loads(threat_model.decode("utf-8"))
        threat_evidence_paths = sorted({
            path
            for item in threat_document["threats"]
            for control in item["controls"]
            for path in control["evidence_paths"]
        })
        threat_control_ids = {
            control["id"]
            for item in threat_document["threats"]
            for control in item["controls"]
        }
        disposition_counts = {
            name: 0 for name in release_candidate_packet.THREAT_DISPOSITIONS
        }
        for item in threat_document["threats"]:
            disposition = item["engineering_disposition"]
            disposition_counts[disposition] += 1
        threat = {
            "schema_version": 1,
            "record_type": "chimera.release-threat-model-assessment",
            "model_id": "p7-local-prototype-threat-model-v1",
            "candidate_commit_sha": self.candidate,
            "candidate_checks": {
                "before_assessment": "matched_clean_head",
                "before_publication": "matched_clean_head",
            },
            "generated_at_utc": self.source_generated,
            "model": {
                "path": "docs/threat-model-v1.json",
                "byte_count": len(threat_model),
                "sha256": sha256(threat_model).hexdigest(),
                "asset_count": len(threat_document["assets"]),
                "actor_count": len(threat_document["actors"]),
                "trust_boundary_count": len(threat_document["trust_boundaries"]),
                "threat_count": len(threat_document["threats"]),
                "control_count": len(threat_control_ids),
                "evidence_file_count": len(threat_evidence_paths),
                "disposition_counts": disposition_counts,
            },
            "evidence_files": [
                {
                    "path": relative,
                    "byte_count": len((release_candidate_packet.ROOT / relative).read_bytes()),
                    "sha256": sha256(
                        (release_candidate_packet.ROOT / relative).read_bytes()
                    ).hexdigest(),
                }
                for relative in threat_evidence_paths
            ],
            "checks": [
                {"id": f"THREAT-{number:03d}", "status": "passed",
                 "description": "passed"}
                for number in range(1, 6)
            ],
            "must_fix_before_m4": [],
            "status": "model_complete",
            "release_decision": "pending_m4_review",
            "human_acceptance": "not_granted",
            "scope": release_candidate_packet.THREAT_SCOPE,
        }
        readiness_manifest = candidate_files["docs/release-readiness-v1.json"]
        readiness_document = json.loads(readiness_manifest.decode("utf-8"))
        readiness_evidence_paths = {
            path
            for group in readiness_document["requirement_groups"]
            for path in group["evidence_paths"]
        }
        readiness_evidence_paths.update(
            path
            for defect in readiness_document["defect_snapshot"]["open_defects"]
            for path in defect["evidence_paths"]
        )
        readiness_evidence_paths.update(
            guide["path"] for guide in readiness_document["guide_checks"]
        )
        declared_requirements = release_candidate_packet._REQUIREMENT_ROW.findall(
            candidate_files["docs/REQUIREMENTS.md"].decode("utf-8")
        )
        guide_summaries = [
            {
                "guide_id": guide["guide_id"],
                "heading_count": len(guide["required_headings"]),
                "path": guide["path"],
            }
            for guide in readiness_document["guide_checks"]
        ]
        snapshot = readiness_document["defect_snapshot"]
        readiness = {
            "schema_version": 1,
            "record_type": "chimera.release-readiness-assessment",
            "candidate_commit_sha": self.candidate,
            "candidate_checks": {
                "before_assessment": "matched_clean_head",
                "before_publication": "matched_clean_head",
            },
            "generated_at_utc": self.source_generated,
            "checks": [
                {"id": f"READINESS-{number:03d}", "status": "passed",
                 "description": "passed"}
                for number in range(1, 6)
            ],
            "defects": {
                "open_count": len(snapshot["open_defects"]),
                "open_release_blockers": [
                    item["issue_number"] for item in snapshot["open_defects"]
                    if item["release_blocker"]
                ],
                "snapshot_at_utc": snapshot["observed_at_utc"],
            },
            "evidence_files": [
                {
                    "path": relative,
                    "byte_count": len((release_candidate_packet.ROOT / relative).read_bytes()),
                    "sha256": sha256(
                        (release_candidate_packet.ROOT / relative).read_bytes()
                    ).hexdigest(),
                }
                for relative in sorted(readiness_evidence_paths)
            ],
            "guides": {
                "guide_count": len(guide_summaries),
                "required_heading_count": sum(
                    item["heading_count"] for item in guide_summaries
                ),
                "summaries": guide_summaries,
            },
            "human_acceptance": "not_granted",
            "m4_decision": "pending",
            "m5_decision": "pending",
            "manifest": {
                "byte_count": len(readiness_manifest),
                "id": "p7-local-prototype-release-readiness-v1",
                "path": "docs/release-readiness-v1.json",
                "sha256": sha256(readiness_manifest).hexdigest(),
            },
            "pending_human_evidence": list(
                release_candidate_packet.PENDING_HUMAN_EVIDENCE
            ),
            "requirements": {
                "covered_count": len(declared_requirements),
                "declared_count": len(declared_requirements),
                "group_count": len(readiness_document["requirement_groups"]),
            },
            "scope": release_candidate_packet.READINESS_SCOPE,
            "status": "review_inputs_complete",
        }
        paths = (
            root / "performance.json", root / "threat.json", root / "readiness.json"
        )
        paths[0].write_bytes(release_candidate_packet._compact(performance))
        paths[1].write_bytes(release_candidate_packet._pretty(threat))
        paths[2].write_bytes(release_candidate_packet._pretty(readiness))
        return paths

    def _assemble(self, root: Path, name: str = "packet.zip") -> tuple[Path, dict]:
        workspace = self._acceptance_workspace(root)
        performance, threat, readiness = self._records(root)
        output = root / name
        with patch.object(
                release_candidate_packet, "_validate_candidate_checkout") as validate:
            manifest = release_candidate_packet.assemble_packet(
                output,
                candidate_commit=self.candidate,
                acceptance_workspace=workspace,
                performance_record=performance,
                threat_record=threat,
                readiness_record=readiness,
                generated_at_utc=self.generated,
            )
        self.assertEqual(2, validate.call_count)
        return output, manifest

    @staticmethod
    def _repack(path: Path, manifest: dict, members: dict[str, bytes]) -> None:
        coherent = deepcopy(manifest)
        coherent["files"] = [
            release_candidate_packet._identity(name, members[name])
            for name in sorted(members)
        ]
        for source in coherent["source_records"].values():
            if source["path"] in members:
                content = members[source["path"]]
                source["byte_count"] = len(content)
                source["sha256"] = sha256(content).hexdigest()
        path.write_bytes(release_candidate_packet._zip_bytes(coherent, members))

    def test_builds_reopens_repeats_and_extracts_complete_pending_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, manifest = self._assemble(root, "first.zip")
            self.assertEqual("packet_complete_for_m4_review", manifest["status"])
            self.assertEqual([], manifest["release_blockers"])
            self.assertEqual("pending", manifest["m4_decision"])
            self.assertEqual("not_granted", manifest["human_acceptance"])
            self.assertEqual(manifest, release_candidate_packet.inspect_packet(first))

            second = root / "second.zip"
            with patch.object(
                    release_candidate_packet, "_validate_candidate_checkout"):
                second_manifest = release_candidate_packet.assemble_packet(
                    second,
                    candidate_commit=self.candidate,
                    acceptance_workspace=root / "acceptance",
                    performance_record=root / "performance.json",
                    threat_record=root / "threat.json",
                    readiness_record=root / "readiness.json",
                    generated_at_utc=self.generated,
                )
            self.assertEqual(manifest, second_manifest)
            self.assertEqual(first.read_bytes(), second.read_bytes())

            extracted = root / "extracted"
            self.assertEqual(
                manifest,
                release_candidate_packet.extract_packet(first, extracted),
            )
            self.assertFalse((extracted / ".PUBLISHING").exists())
            self.assertEqual(
                release_candidate_packet._pretty(manifest),
                (extracted / "manifest.json").read_bytes(),
            )
            script = (extracted / "M4-ACCEPTANCE-SCRIPT.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("**NOT PERFORMED.**", script)
            self.assertIn(self.candidate, script)
            self.assertNotIn("- [x]", script.lower())

    def test_coherent_failed_performance_is_retained_as_packet_blocker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._acceptance_workspace(root)
            performance, threat, readiness = self._records(root)
            document = json.loads(performance.read_text(encoding="utf-8"))
            document["measurements"]["operator_run"]["samples_ms"][-1] = 4_000.0
            document["measurements"]["operator_run"]["p95_ms"] = 4_000.0
            document["measurements"]["operator_run"]["max_ms"] = 4_000.0
            document["target_results"]["operator_run_p95_ms"]["observed_ms"] = 4_000.0
            document["target_results"]["operator_run_p95_ms"]["status"] = "failed"
            document["status"] = "failed"
            performance.write_bytes(release_candidate_packet._compact(document))
            output = root / "blocked.zip"
            with patch.object(
                    release_candidate_packet, "_validate_candidate_checkout"):
                manifest = release_candidate_packet.assemble_packet(
                    output,
                    candidate_commit=self.candidate,
                    acceptance_workspace=workspace,
                    performance_record=performance,
                    threat_record=threat,
                    readiness_record=readiness,
                    generated_at_utc=self.generated,
                )
            self.assertEqual("blocked_by_release_controls", manifest["status"])
            self.assertEqual(
                ["performance:operator_run_p95_ms"],
                manifest["release_blockers"],
            )
            self.assertEqual("blocked", manifest["checks"][2]["status"])
            self.assertEqual(manifest, release_candidate_packet.inspect_packet(output))

    def test_rejects_candidate_and_acceptance_claim_mismatches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._acceptance_workspace(root)
            performance, threat, readiness = self._records(root)
            cases = []

            changed_candidate = json.loads(performance.read_text(encoding="utf-8"))
            changed_candidate["candidate_commit_sha"] = "b" * 40
            cases.append((performance, changed_candidate, "candidate"))

            accepted = json.loads(readiness.read_text(encoding="utf-8"))
            accepted["human_acceptance"] = "granted"
            cases.append((readiness, accepted, "must remain pending"))

            inconsistent = json.loads(performance.read_text(encoding="utf-8"))
            inconsistent["status"] = "failed"
            cases.append((performance, inconsistent, "aggregate status"))

            for index, (path, mutation, message) in enumerate(cases):
                with self.subTest(message=message):
                    original = path.read_bytes()
                    style = "compact" if path == performance else "pretty"
                    path.write_bytes(
                        release_candidate_packet._compact(mutation)
                        if style == "compact"
                        else release_candidate_packet._pretty(mutation)
                    )
                    output = root / f"rejected-{index}.zip"
                    with patch.object(
                            release_candidate_packet,
                            "_validate_candidate_checkout"):
                        with self.assertRaisesRegex(
                                release_candidate_packet.ReleaseCandidatePacketError,
                                message):
                            release_candidate_packet.assemble_packet(
                                output,
                                candidate_commit=self.candidate,
                                acceptance_workspace=workspace,
                                performance_record=performance,
                                threat_record=threat,
                                readiness_record=readiness,
                                generated_at_utc=self.generated,
                            )
                    self.assertFalse(output.exists())
                    path.write_bytes(original)

    def test_rejects_changed_unexpected_and_symbolic_acceptance_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._acceptance_workspace(root)
            files = release_candidate_packet._workspace_file_bytes(workspace)
            record = json.loads(files["acceptance-preparation.json"].decode("utf-8"))
            record["runs"][0]["artifacts"][0]["sha256"] = "0" * 64
            (workspace / "acceptance-preparation.json").write_bytes(
                release_candidate_packet._compact(record)
            )
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "sha256"):
                release_candidate_packet._validate_acceptance_workspace(
                    release_candidate_packet._workspace_file_bytes(workspace),
                    self.candidate,
                )

            workspace = root / "acceptance-extra"
            original = self._acceptance_workspace(root / "extra-root")
            original.rename(workspace)
            (workspace / "unexpected.txt").write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "unexpected"):
                release_candidate_packet._validate_acceptance_workspace(
                    release_candidate_packet._workspace_file_bytes(workspace),
                    self.candidate,
                )

            linked = workspace / "linked.txt"
            linked.symlink_to(workspace / "operator-observations.md")
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "symbolic link"):
                release_candidate_packet._workspace_file_bytes(workspace)

    def test_archive_tampering_extra_members_and_changed_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet, _ = self._assemble(root)
            manifest, members = release_candidate_packet._read_packet(packet)

            extra = dict(members)
            extra["extra.txt"] = b"unexpected"
            extra_packet = root / "extra.zip"
            extra_packet.write_bytes(release_candidate_packet._zip_bytes(manifest, extra))
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "identity count|unindexed"):
                release_candidate_packet.inspect_packet(extra_packet)

            changed = dict(members)
            changed["M4-ACCEPTANCE-SCRIPT.md"] += b"approved\n"
            changed_packet = root / "changed.zip"
            changed_packet.write_bytes(
                release_candidate_packet._zip_bytes(manifest, changed)
            )
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "byte_count|sha256"):
                release_candidate_packet.inspect_packet(changed_packet)

            traversal = root / "traversal.zip"
            destination = io.BytesIO()
            with zipfile.ZipFile(destination, "w") as archive:
                info = zipfile.ZipInfo("../manifest.json", release_candidate_packet.FIXED_ZIP_TIME)
                info.create_system = 3
                info.external_attr = release_candidate_packet._REGULAR_MODE << 16
                archive.writestr(info, b"{}")
            traversal.write_bytes(destination.getvalue())
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "safe relative"):
                release_candidate_packet.inspect_packet(traversal)

    def test_rejects_fail_open_source_semantics_and_scope_overclaims(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._acceptance_workspace(root)
            performance, threat, readiness = self._records(root)

            source_cases = [
                (
                    performance,
                    lambda value: value["workload"].__setitem__("sample_count", 1),
                    "workload changed",
                    "compact",
                ),
                (
                    performance,
                    lambda value: (
                        value["measurements"]["operator_run"]["samples_ms"].__setitem__(
                            -1, 4_000.0
                        ),
                        value["measurements"]["operator_run"].__setitem__(
                            "p95_ms", 4_000.0
                        ),
                        value["measurements"]["operator_run"].__setitem__(
                            "max_ms", 4_000.0
                        ),
                        value["target_results"]["operator_run_p95_ms"].__setitem__(
                            "observed_ms", 4_000.0
                        ),
                    ),
                    "result status is inconsistent",
                    "compact",
                ),
                (
                    threat,
                    lambda value: value.__setitem__("model_id", "wrong-model"),
                    "record type changed",
                    "pretty",
                ),
                (
                    threat,
                    lambda value: value.__setitem__(
                        "candidate_checks", {
                            "before_assessment": "not_checked",
                            "before_publication": "not_checked",
                        }
                    ),
                    "candidate checks are incomplete",
                    "pretty",
                ),
                (
                    threat,
                    lambda value: value["model"]["disposition_counts"].pop(
                        "must_fix_before_m4"
                    ),
                    "summary does not match candidate model",
                    "pretty",
                ),
                (
                    readiness,
                    lambda value: value.__setitem__("checks", []),
                    "check inventory changed",
                    "pretty",
                ),
                (
                    readiness,
                    lambda value: value.__setitem__(
                        "pending_human_evidence", ["overclaimed complete"]
                    ),
                    "pending review inputs changed",
                    "pretty",
                ),
                (
                    readiness,
                    lambda value: value.__setitem__("scope", "release approved"),
                    "scope changed",
                    "pretty",
                ),
            ]
            for index, (path, mutate, message, style) in enumerate(source_cases):
                with self.subTest(source=path.name, message=message):
                    original = path.read_bytes()
                    try:
                        document = json.loads(original.decode("utf-8"))
                        mutate(document)
                        path.write_bytes(
                            release_candidate_packet._compact(document)
                            if style == "compact"
                            else release_candidate_packet._pretty(document)
                        )
                        with patch.object(
                                release_candidate_packet,
                                "_validate_candidate_checkout"):
                            with self.assertRaisesRegex(
                                    release_candidate_packet.ReleaseCandidatePacketError,
                                    message):
                                release_candidate_packet.assemble_packet(
                                    root / f"source-rejected-{index}.zip",
                                    candidate_commit=self.candidate,
                                    acceptance_workspace=workspace,
                                    performance_record=performance,
                                    threat_record=threat,
                                    readiness_record=readiness,
                                    generated_at_utc=self.generated,
                                )
                    finally:
                        path.write_bytes(original)

            operator_cases = [
                (lambda value: value["synthetic_provenance"].__setitem__(
                    "synthetic", False), "provenance changed"),
                (lambda value: value["completed_resume"].__setitem__(
                    "portable_artifacts_unchanged", False), "did not preserve"),
                (lambda value: value["completed_resume"]["before_sha256"].pop(
                    "request.json"), "did not preserve"),
                (lambda value: value["handoff_manifest"].__setitem__(
                    "verdict", "pass"), "handoff manifest changed"),
                (lambda value: value["dashboard_download"].__setitem__(
                    "matches_file_export", False), "dashboard export control changed"),
                (lambda value: value["dashboard_download"]["headers"].pop(
                    "Content-Disposition"), "dashboard export control changed"),
                (lambda value: value["malformed_inputs"][1].__setitem__(
                    "case", "malformed-value"), "input inventory changed"),
            ]
            record_path = workspace / "acceptance-preparation.json"
            for mutate, message in operator_cases:
                with self.subTest(operator=message):
                    original = record_path.read_bytes()
                    document = json.loads(original.decode("utf-8"))
                    mutate(document)
                    record_path.write_bytes(
                        release_candidate_packet._compact(document)
                    )
                    with self.assertRaisesRegex(
                            release_candidate_packet.ReleaseCandidatePacketError,
                            message):
                        release_candidate_packet._validate_acceptance_workspace(
                            release_candidate_packet._workspace_file_bytes(workspace),
                            self.candidate,
                        )
                    record_path.write_bytes(original)

    def test_rejects_unreopenable_operator_artifacts_even_when_record_is_rehashed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            workspace = self._acceptance_workspace(root / "run-case")
            record_path = workspace / "acceptance-preparation.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            report_path = "runs/passing/report.json"
            changed_report = b"{}\n"
            (workspace / report_path).write_bytes(changed_report)
            artifact = next(
                item for run in record["runs"] if run["label"] == "passing"
                for item in run["artifacts"] if item["path"] == report_path
            )
            artifact["bytes"] = len(changed_report)
            artifact["sha256"] = sha256(changed_report).hexdigest()
            record_path.write_bytes(release_candidate_packet._compact(record))
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "does not reopen as a completed run"):
                release_candidate_packet._validate_acceptance_workspace(
                    release_candidate_packet._workspace_file_bytes(workspace),
                    self.candidate,
                )

            workspace = self._acceptance_workspace(root / "handoff-case")
            record_path = workspace / "acceptance-preparation.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            changed_handoff = b"not-a-zip\n"
            for artifact in record["handoffs"]:
                (workspace / artifact["path"]).write_bytes(changed_handoff)
                artifact["bytes"] = len(changed_handoff)
                artifact["sha256"] = sha256(changed_handoff).hexdigest()
            record_path.write_bytes(release_candidate_packet._compact(record))
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "handoff .* does not reopen"):
                release_candidate_packet._validate_acceptance_workspace(
                    release_candidate_packet._workspace_file_bytes(workspace),
                    self.candidate,
                )

            workspace = self._acceptance_workspace(root / "malformed-case")
            record_path = workspace / "acceptance-preparation.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            valid_csv = (
                release_candidate_packet.ROOT
                / "examples/fixtures/link_margin_passed.csv"
            ).read_bytes()
            input_path = "inputs/malformed-value.csv"
            (workspace / input_path).write_bytes(valid_csv)
            malformed = next(
                item for item in record["malformed_inputs"]
                if item["case"] == "malformed-value"
            )
            malformed["input"]["bytes"] = len(valid_csv)
            malformed["input"]["sha256"] = sha256(valid_csv).hexdigest()
            record_path.write_bytes(release_candidate_packet._compact(record))
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "accepted by the product parser"):
                release_candidate_packet._validate_acceptance_workspace(
                    release_candidate_packet._workspace_file_bytes(workspace),
                    self.candidate,
                )

    def test_rejects_coherently_indexed_extra_operator_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._acceptance_workspace(root)
            record_path = workspace / "acceptance-preparation.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            content = b"unreviewed content\n"
            relative = "runs/passing/unreviewed-secret.txt"
            (workspace / relative).write_bytes(content)
            passing = next(
                run for run in record["runs"] if run["label"] == "passing"
            )
            passing["artifacts"].append({
                "path": relative,
                "bytes": len(content),
                "sha256": sha256(content).hexdigest(),
            })
            record_path.write_bytes(release_candidate_packet._compact(record))

            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "artifact inventory changed"):
                release_candidate_packet._validate_acceptance_workspace(
                    release_candidate_packet._workspace_file_bytes(workspace),
                    self.candidate,
                )

            renamed = self._acceptance_workspace(root / "renamed")
            record_path = renamed / "acceptance-preparation.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            original = renamed / "inputs/malformed-value.csv"
            replacement = renamed / "notes/unreviewed-invalid.txt"
            replacement.parent.mkdir()
            original.rename(replacement)
            malformed = next(
                item for item in record["malformed_inputs"]
                if item["case"] == "malformed-value"
            )
            malformed["input"]["path"] = "notes/unreviewed-invalid.txt"
            record_path.write_bytes(release_candidate_packet._compact(record))

            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "artifact path changed"):
                release_candidate_packet._validate_acceptance_workspace(
                    release_candidate_packet._workspace_file_bytes(renamed),
                    self.candidate,
                )

            contradictory = self._acceptance_workspace(root / "contradictory")
            record_path = contradictory / "acceptance-preparation.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            worksheet_path = contradictory / "operator-observations.md"
            worksheet = worksheet_path.read_bytes() + (
                b"\nReview performed by Leo. M4 decision: approved. "
                b"Human acceptance: granted.\n"
            )
            worksheet_path.write_bytes(worksheet)
            artifact = record["observation_worksheet"]
            artifact["bytes"] = len(worksheet)
            artifact["sha256"] = sha256(worksheet).hexdigest()
            record_path.write_bytes(release_candidate_packet._compact(record))

            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "canonical blank candidate form"):
                release_candidate_packet._validate_acceptance_workspace(
                    release_candidate_packet._workspace_file_bytes(contradictory),
                    self.candidate,
                )

    def test_portable_inspection_rejects_reindexed_extras_collisions_and_future_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet, _ = self._assemble(root)
            manifest, members = release_candidate_packet._read_packet(packet)

            extra_members = dict(members)
            extra_members["notes/unreviewed.txt"] = b"not a v1 packet member\n"
            extra = root / "coherent-extra.zip"
            self._repack(extra, manifest, extra_members)
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "member inventory changed"):
                release_candidate_packet.inspect_packet(extra)

            collision_members = dict(members)
            collision_members["notes"] = b"file\n"
            collision_members["notes/sub.txt"] = b"child\n"
            collision = root / "prefix-collision.zip"
            self._repack(collision, manifest, collision_members)
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "file/path-prefix collision"):
                release_candidate_packet.inspect_packet(collision)

            future_members = dict(members)
            performance_path = release_candidate_packet.ASSESSMENT_NAMES["performance"]
            performance = json.loads(future_members[performance_path].decode("utf-8"))
            performance["generated_at_utc"] = "2026-10-30T10:00:01Z"
            future_members[performance_path] = release_candidate_packet._compact(
                performance
            )
            future = root / "future-source.zip"
            self._repack(future, manifest, future_members)
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "generated after the packet"):
                release_candidate_packet.inspect_packet(future)

    def test_refuses_existing_symlinked_inside_checkout_and_changed_candidate_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._acceptance_workspace(root)
            performance, threat, readiness = self._records(root)
            existing = root / "existing.zip"
            existing.write_bytes(b"user data")
            linked = root / "linked.zip"
            linked.symlink_to(root / "missing")
            for output in (existing, linked):
                before = output.lstat()
                with patch.object(
                        release_candidate_packet,
                        "_validate_candidate_checkout"):
                    with self.assertRaisesRegex(
                            release_candidate_packet.ReleaseCandidatePacketError,
                            "already exists"):
                        release_candidate_packet.assemble_packet(
                            output,
                            candidate_commit=self.candidate,
                            acceptance_workspace=workspace,
                            performance_record=performance,
                            threat_record=threat,
                            readiness_record=readiness,
                            generated_at_utc=self.generated,
                        )
                self.assertEqual(before, output.lstat())
            self.assertEqual(b"user data", existing.read_bytes())

            inside = release_candidate_packet.ROOT / "packet-test-output.zip"
            with patch.object(
                    release_candidate_packet, "_validate_candidate_checkout"):
                with self.assertRaisesRegex(
                        release_candidate_packet.ReleaseCandidatePacketError,
                        "outside the source checkout"):
                    release_candidate_packet.assemble_packet(
                        inside,
                        candidate_commit=self.candidate,
                        acceptance_workspace=workspace,
                        performance_record=performance,
                        threat_record=threat,
                        readiness_record=readiness,
                        generated_at_utc=self.generated,
                    )
            self.assertFalse(inside.exists())

            changed = release_candidate_packet.ReleaseCandidatePacketError(
                "release-candidate packet requires a clean checkout"
            )
            output = root / "changed.zip"
            with patch.object(
                    release_candidate_packet, "_validate_candidate_checkout",
                    side_effect=[None, changed]):
                with self.assertRaisesRegex(
                        release_candidate_packet.ReleaseCandidatePacketError,
                        "clean checkout"):
                    release_candidate_packet.assemble_packet(
                        output,
                        candidate_commit=self.candidate,
                        acceptance_workspace=workspace,
                        performance_record=performance,
                        threat_record=threat,
                        readiness_record=readiness,
                        generated_at_utc=self.generated,
                    )
            self.assertFalse(output.exists())

    def test_candidate_validation_and_canonical_json_fail_closed(self):
        for candidate in ("", "abc", "A" * 40, "g" * 40):
            with self.subTest(candidate=candidate):
                with patch.object(release_candidate_packet, "_git") as git:
                    with self.assertRaisesRegex(
                            release_candidate_packet.ReleaseCandidatePacketError,
                            "full lowercase"):
                        release_candidate_packet._validate_candidate_checkout(candidate)
                    git.assert_not_called()
        head = subprocess.CompletedProcess(
            ["git"], 0, stdout=self.candidate + "\n", stderr=""
        )
        dirty = subprocess.CompletedProcess(
            ["git"], 0, stdout="?? result.zip\n", stderr=""
        )
        with patch.object(
                release_candidate_packet, "_git", side_effect=[head, dirty]):
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "clean checkout"):
                release_candidate_packet._validate_candidate_checkout(self.candidate)

        for content, message in (
            (b'{"a":1,"a":2}\n', "duplicate"),
            (b'{"a": 1}\n', "canonical"),
            (b'{"a":NaN}\n', "non-finite"),
            (b'{"a":"\xff"}\n', "strict UTF-8"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(
                        release_candidate_packet.ReleaseCandidatePacketError,
                        message):
                    release_candidate_packet._load_json_bytes(
                        content, "test record", style="compact"
                    )

    def test_extraction_refuses_existing_output_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet, _ = self._assemble(root)
            existing = root / "existing"
            existing.mkdir()
            marker = existing / "user.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(
                    release_candidate_packet.ReleaseCandidatePacketError,
                    "already exists"):
                release_candidate_packet.extract_packet(packet, existing)
            self.assertEqual("keep", marker.read_text(encoding="utf-8"))

    def test_control_does_not_depend_on_removable_asserts(self):
        source = Path(release_candidate_packet.__file__).read_text(encoding="utf-8")
        self.assertFalse(
            any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(source))),
            "release-candidate packet controls must survive python -O",
        )


if __name__ == "__main__":
    unittest.main()
