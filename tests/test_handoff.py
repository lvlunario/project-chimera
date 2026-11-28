import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_STORED, ZipFile

from chimera.handoff import (ARTIFACT_NAMES, HandoffError,
                             create_handoff_bundle, handoff_bundle_bytes,
                             inspect_handoff_bundle)
from chimera.api import CompletedLinkRun
from chimera.operator import run_link_verification


FIXTURES = Path(__file__).parents[1] / "examples" / "fixtures"


class HandoffTests(unittest.TestCase):
    def _run(self, root: Path, name="run") -> Path:
        output = root / name
        run_link_verification(
            FIXTURES / "link_margin_passed.csv", output,
            threshold_db="3.0",
        )
        return output

    def test_bundle_is_deterministic_and_self_verifying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root)
            first, second = root / "first.zip", root / "second.zip"
            expected = create_handoff_bundle(run, first)
            create_handoff_bundle(run, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(expected, inspect_handoff_bundle(first))
            self.assertEqual(first.read_bytes(), handoff_bundle_bytes(
                CompletedLinkRun.open(run)
            ))
            self.assertEqual("pass", expected["verdict"])
            with ZipFile(first) as archive:
                self.assertEqual(
                    ["manifest.json", *ARTIFACT_NAMES], archive.namelist()
                )
                self.assertTrue(all(item.compress_type == ZIP_STORED
                                    for item in archive.infolist()))

    def test_manifest_hashes_exact_bundle_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root)
            bundle = root / "handoff.zip"
            manifest = create_handoff_bundle(run, bundle)
            with ZipFile(bundle) as archive:
                saved = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest, saved)
                for entry in saved["artifacts"]:
                    self.assertEqual(entry["bytes"], len(archive.read(entry["path"])))

    def test_refuses_existing_output_and_invalid_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root)
            output = root / "handoff.zip"
            output.write_bytes(b"owned")
            with self.assertRaisesRegex(HandoffError, "already exists"):
                create_handoff_bundle(run, output)
            (run / "report.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(HandoffError, "Completed run is invalid"):
                create_handoff_bundle(run, root / "new.zip")

    def test_inspector_rejects_changed_and_extra_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root)
            original = root / "handoff.zip"
            create_handoff_bundle(run, original)
            for case, mutation in (
                ("changed", ("report.json", b"{}")),
                ("extra", ("unexpected.txt", b"no")),
            ):
                target = root / f"{case}.zip"
                with ZipFile(original) as source, ZipFile(target, "w") as changed:
                    for item in source.infolist():
                        data = source.read(item.filename)
                        if mutation[0] == item.filename:
                            data = mutation[1]
                        changed.writestr(item, data)
                    if mutation[0] == "unexpected.txt":
                        changed.writestr("unexpected.txt", mutation[1])
                with self.subTest(case=case), self.assertRaises(HandoffError):
                    inspect_handoff_bundle(target)

    def test_inspector_rejects_boolean_schema_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root)
            original, changed = root / "handoff.zip", root / "changed.zip"
            create_handoff_bundle(run, original)
            with ZipFile(original) as source, ZipFile(changed, "w") as target:
                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename == "manifest.json":
                        manifest = json.loads(data)
                        manifest["schema_version"] = True
                        data = (json.dumps(
                            manifest, sort_keys=True, separators=(",", ":")
                        ) + "\n").encode()
                    target.writestr(item, data)
            with self.assertRaisesRegex(HandoffError, "schema_version"):
                inspect_handoff_bundle(changed)

    def test_failed_write_leaves_no_final_or_temporary_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root)
            output = root / "handoff.zip"

            class FailingWriter:
                def __init__(self, stream):
                    self.stream = stream

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.stream.close()

                def write(self, content):
                    self.stream.write(content[:17])
                    raise OSError("injected write failure")

                def flush(self):
                    self.stream.flush()

                def fileno(self):
                    return self.stream.fileno()

            real_fdopen = __import__("os").fdopen

            def fail_fdopen(descriptor, mode):
                return FailingWriter(real_fdopen(descriptor, mode))

            with patch("chimera.handoff.os.fdopen", side_effect=fail_fdopen):
                with self.assertRaisesRegex(HandoffError, "Cannot publish"):
                    create_handoff_bundle(run, output)
            self.assertFalse(output.exists())
            self.assertEqual([], list(root.glob(".handoff.zip.*.tmp")))
            create_handoff_bundle(run, output)
            self.assertEqual("pass", inspect_handoff_bundle(output)["verdict"])

    def test_byte_renderer_requires_validated_completed_view(self):
        with self.assertRaisesRegex(TypeError, "CompletedLinkRun"):
            handoff_bundle_bytes(object())

    def test_cli_export_and_inspect(self):
        from chimera.cli import main

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root)
            bundle = root / "handoff.zip"
            self.assertEqual(
                0, main(["export-link", str(run), "--output", str(bundle)])
            )
            self.assertEqual(0, main(["inspect-link", str(bundle)]))


if __name__ == "__main__":
    unittest.main()
