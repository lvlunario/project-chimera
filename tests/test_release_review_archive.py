"""Protect the portable exact-candidate review-rehearsal archive."""
import ast
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from examples import (
    operator_acceptance_prep,
    release_candidate_packet,
    release_performance,
    release_readiness,
    release_review_archive,
    release_review_rehearsal,
    release_threat_model,
)


class ReleaseReviewArchiveTests(unittest.TestCase):
    candidate = "a" * 40
    generated = "2026-11-14T10:15:00Z"

    def _validators(self, *, blocked=False):
        tracked = release_readiness._tracked_repository_paths()
        tracked.update({
            "examples/release_candidate_nomination.py",
            "examples/release_review_archive.py",
            "examples/release_review_rehearsal.py",
            "tests/test_release_candidate_nomination.py",
            "tests/test_release_review_archive.py",
            "tests/test_release_review_rehearsal.py",
        })
        operator_value = 3_001.0 if blocked else 1.0
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
                    "operator_run": release_performance._summary(
                        [operator_value] * 10
                    ),
                    "handoff_round_trip": release_performance._summary(
                        [1.0] * 10
                    ),
                    "dashboard_snapshot": release_performance._summary(
                        [1.0] * 5
                    ),
                },
            ),
        )

    def _prepare(self, output: Path, *, blocked=False):
        with ExitStack() as stack:
            for validator in self._validators(blocked=blocked):
                stack.enter_context(validator)
            return release_review_rehearsal.prepare_review_rehearsal(
                output,
                candidate_commit=self.candidate,
                generated_at_utc=self.generated,
            )

    @staticmethod
    def _tree_bytes(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    @staticmethod
    def _zip_bytes(
        entries: list[tuple[str, bytes]],
        *,
        compressed_name: str | None = None,
    ) -> bytes:
        destination = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(
                destination, "w", compression=zipfile.ZIP_STORED
            ) as archive:
                for name, content in entries:
                    info = zipfile.ZipInfo(
                        name, release_review_archive.FIXED_ZIP_TIME
                    )
                    info.create_system = 3
                    info.compress_type = (
                        zipfile.ZIP_DEFLATED
                        if name == compressed_name
                        else zipfile.ZIP_STORED
                    )
                    info.external_attr = (
                        release_review_archive.REGULAR_MODE << 16
                    )
                    archive.writestr(info, content)
        return destination.getvalue()

    @staticmethod
    def _encrypted(content: bytes) -> bytes:
        changed = bytearray(content)
        positions = (
            (b"PK\x03\x04", 6),
            (b"PK\x01\x02", 8),
        )
        for signature, offset in positions:
            start = 0
            found = False
            while True:
                position = changed.find(signature, start)
                if position < 0:
                    break
                flags = int.from_bytes(
                    changed[position + offset:position + offset + 2], "little"
                )
                changed[position + offset:position + offset + 2] = (
                    flags | 0x1
                ).to_bytes(2, "little")
                start = position + 4
                found = True
            if not found:
                raise AssertionError("test ZIP signature is unavailable")
        return bytes(changed)

    @staticmethod
    def _invalid_utf8_name(content: bytes) -> bytes:
        changed = bytearray(content)
        for signature, flags_offset, name_offset in (
            (b"PK\x03\x04", 6, 30),
            (b"PK\x01\x02", 8, 46),
        ):
            position = changed.find(signature)
            if position < 0:
                raise AssertionError("test ZIP signature is unavailable")
            flags = int.from_bytes(
                changed[
                    position + flags_offset:position + flags_offset + 2
                ],
                "little",
            )
            changed[
                position + flags_offset:position + flags_offset + 2
            ] = (flags | 0x800).to_bytes(2, "little")
            changed[position + name_offset] = 0xff
        return bytes(changed)

    def test_round_trip_is_deterministic_bounded_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review = root / "review"
            receipt = self._prepare(review)
            before = self._tree_bytes(review)
            first = root / "first.zip"
            second = root / "second.zip"

            summary = release_review_archive.create_review_archive(
                review, first
            )
            repeated = release_review_archive.create_review_archive(
                review, second
            )
            first_bytes = first.read_bytes()
            self.assertEqual(first_bytes, second.read_bytes())
            self.assertEqual(summary, repeated)
            self.assertEqual(
                summary,
                release_review_archive.inspect_review_archive(first),
            )
            self.assertEqual(before, self._tree_bytes(review))
            self.assertEqual(first_bytes, first.read_bytes())
            self.assertEqual(self.candidate, summary["candidate_commit_sha"])
            self.assertEqual(
                "packet_complete_for_m4_review", summary["status"]
            )
            self.assertEqual("pending", summary["m4_decision"])
            self.assertEqual("pending", summary["m5_decision"])
            self.assertEqual("not_granted", summary["human_acceptance"])

            with zipfile.ZipFile(first, "r") as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                expected = sorted([
                    release_review_rehearsal.RECEIPT_NAME,
                    *[item["path"] for item in receipt["artifacts"]],
                ])
                self.assertEqual(expected, names)
                self.assertEqual(b"", archive.comment)
                for info in infos:
                    self.assertEqual(
                        release_review_archive.FIXED_ZIP_TIME,
                        info.date_time,
                    )
                    self.assertEqual(zipfile.ZIP_STORED, info.compress_type)
                    self.assertEqual(info.file_size, info.compress_size)
                    self.assertEqual(0, info.flag_bits)
                    self.assertEqual(3, info.create_system)
                    self.assertEqual(
                        release_review_archive.REGULAR_MODE,
                        info.external_attr >> 16,
                    )
                    self.assertEqual(b"", info.extra)
                    self.assertEqual(b"", info.comment)

            output = io.StringIO()
            with redirect_stdout(output):
                result = release_review_archive.main([
                    "inspect", str(first),
                ])
            self.assertEqual(0, result)
            self.assertIn(
                "P3/P4/P5, M4/M5 and human acceptance remain pending",
                output.getvalue(),
            )

    def test_coherent_blocked_rehearsal_remains_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review = root / "review"
            receipt = self._prepare(review, blocked=True)
            self.assertEqual(
                ["performance:operator_run_p95_ms"],
                receipt["release_blockers"],
            )
            archive = root / "blocked.zip"
            summary = release_review_archive.create_review_archive(
                review, archive
            )
            self.assertEqual(
                "blocked_by_release_controls", summary["status"]
            )
            self.assertEqual(
                ["performance:operator_run_p95_ms"],
                summary["release_blockers"],
            )
            output = io.StringIO()
            with redirect_stdout(output):
                result = release_review_archive.main([
                    "inspect", str(archive),
                ])
            self.assertEqual(1, result)
            self.assertIn("blocked_by_release_controls", output.getvalue())
            self.assertIn("remain pending", output.getvalue())

    def test_archive_tampering_and_unsafe_members_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review = root / "review"
            self._prepare(review)
            archive = root / "valid.zip"
            release_review_archive.create_review_archive(review, archive)
            with zipfile.ZipFile(archive, "r") as source:
                entries = [
                    (info.filename, source.read(info))
                    for info in source.infolist()
                ]
            by_name = dict(entries)
            changed = deepcopy(entries)
            performance = "sources/release-performance.json"
            changed = [
                (name, content + b" " if name == performance else content)
                for name, content in changed
            ]
            cases = {
                "missing.zip": self._zip_bytes(entries[:-1]),
                "extra.zip": self._zip_bytes(
                    sorted([*entries, ("unexpected.txt", b"unexpected\n")])
                ),
                "changed.zip": self._zip_bytes(changed),
                "duplicate.zip": self._zip_bytes(
                    sorted([*entries, entries[0]])
                ),
                "compressed.zip": self._zip_bytes(
                    entries, compressed_name=performance
                ),
                "traversal.zip": self._zip_bytes(
                    sorted([*entries, ("../escape", b"escape\n")])
                ),
                "absolute.zip": self._zip_bytes(
                    sorted([*entries, ("/absolute", b"absolute\n")])
                ),
                "backslash.zip": self._zip_bytes(
                    sorted([*entries, ("bad\\name", b"bad\n")])
                ),
                "prefix.zip": self._zip_bytes(
                    sorted([*entries, ("sources", b"collision\n")])
                ),
                "deep.zip": self._zip_bytes(sorted([
                    *entries,
                    ("/".join(["deep"] * 17), b"deep\n"),
                ])),
                "encrypted.zip": self._encrypted(archive.read_bytes()),
                "invalid-utf8.zip": self._invalid_utf8_name(
                    archive.read_bytes()
                ),
                "trailing.zip": archive.read_bytes() + b"trailing bytes",
            }
            self.assertIn(performance, by_name)
            for name, content in cases.items():
                with self.subTest(name=name):
                    path = root / name
                    path.write_bytes(content)
                    with self.assertRaises(
                        (
                            release_review_archive.ReviewArchiveError,
                            release_review_rehearsal.ReviewRehearsalError,
                            release_candidate_packet.ReleaseCandidatePacketError,
                        )
                    ):
                        release_review_archive.inspect_review_archive(path)

    def test_output_boundaries_and_partial_publication_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review = root / "review"
            self._prepare(review)

            existing = root / "existing.zip"
            existing.write_bytes(b"keep")
            with self.assertRaisesRegex(
                release_review_archive.ReviewArchiveError, "already exists"
            ):
                release_review_archive.create_review_archive(review, existing)
            self.assertEqual(b"keep", existing.read_bytes())

            existing_directory = root / "existing-directory"
            existing_directory.mkdir()
            with self.assertRaisesRegex(
                release_review_archive.ReviewArchiveError, "already exists"
            ):
                release_review_archive.create_review_archive(
                    review, existing_directory
                )

            symlink = root / "symlink.zip"
            symlink.symlink_to(existing)
            with self.assertRaisesRegex(
                release_review_archive.ReviewArchiveError, "symbolic link"
            ):
                release_review_archive.create_review_archive(review, symlink)

            real_parent = root / "real-parent"
            real_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(
                release_review_archive.ReviewArchiveError,
                "parent is unavailable",
            ):
                release_review_archive.create_review_archive(
                    review, linked_parent / "archive.zip"
                )

            walked_parent = root / "walked-parent"
            walked_parent.mkdir()
            renamed_parent = root / "walked-parent-renamed"
            alternate_parent = root / "alternate-parent"
            alternate_parent.mkdir()
            original_open = release_review_archive.os.open
            swapped_parent = False

            def swap_parent_before_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal swapped_parent
                if path == walked_parent.name and not swapped_parent:
                    swapped_parent = True
                    walked_parent.rename(renamed_parent)
                    walked_parent.symlink_to(
                        alternate_parent, target_is_directory=True
                    )
                if dir_fd is None:
                    return original_open(path, flags, mode)
                return original_open(path, flags, mode, dir_fd=dir_fd)

            with patch.object(
                release_review_archive.os,
                "open",
                side_effect=swap_parent_before_open,
            ):
                with self.assertRaisesRegex(
                    release_review_archive.ReviewArchiveError,
                    "parent is unavailable",
                ):
                    release_review_archive.create_review_archive(
                        review, walked_parent / "archive.zip"
                    )
            self.assertTrue(walked_parent.is_symlink())
            self.assertFalse((renamed_parent / "archive.zip").exists())
            self.assertFalse((alternate_parent / "archive.zip").exists())

            with self.assertRaisesRegex(
                release_review_archive.ReviewArchiveError,
                "outside the checkout and rehearsal",
            ):
                release_review_archive.create_review_archive(
                    review, review / "inside.zip"
                )

            forbidden = release_review_archive.ROOT / "forbidden-review.zip"
            self.assertFalse(forbidden.exists())
            with self.assertRaisesRegex(
                release_review_archive.ReviewArchiveError,
                "outside the checkout and rehearsal",
            ):
                release_review_archive.create_review_archive(
                    review, forbidden
                )
            self.assertFalse(forbidden.exists())

            failed = root / "failed.zip"
            with patch.object(
                release_review_archive.os,
                "link",
                side_effect=OSError("injected publication failure"),
            ):
                with self.assertRaisesRegex(
                    release_review_archive.ReviewArchiveError,
                    "cannot publish",
                ):
                    release_review_archive.create_review_archive(
                        review, failed
                    )
            self.assertFalse(failed.exists())
            self.assertEqual([], list(root.glob(".failed.zip.*.tmp")))

            swapped = root / "swapped.zip"
            original_live_entry_content_matches = (
                release_review_archive._live_entry_content_matches
            )

            def reject_swapped_output(
                parent, parent_identity, name, identity, content
            ):
                if parent == root and name == swapped.name:
                    return False
                return original_live_entry_content_matches(
                    parent, parent_identity, name, identity, content
                )

            with patch.object(
                release_review_archive,
                "_live_entry_content_matches",
                side_effect=reject_swapped_output,
            ):
                with self.assertRaisesRegex(
                    release_review_archive.ReviewArchiveError,
                    "path or content changed during publication",
                ):
                    release_review_archive.create_review_archive(
                        review, swapped
                    )
            self.assertFalse(swapped.exists())

            fifo = root / "fifo.zip"
            original_write_archive = release_review_archive._write_archive

            def replace_with_fifo(parent_descriptor, target_name, content):
                identity = original_write_archive(
                    parent_descriptor, target_name, content
                )
                fifo.unlink()
                os.mkfifo(fifo, mode=0o600)
                return identity

            with patch.object(
                release_review_archive,
                "_write_archive",
                side_effect=replace_with_fifo,
            ):
                with self.assertRaisesRegex(
                    release_review_archive.ReviewArchiveError,
                    "identity changed during publication",
                ):
                    release_review_archive.create_review_archive(
                        review, fifo
                    )
            self.assertTrue(fifo.exists())
            self.assertFalse(fifo.is_file())
            fifo.unlink()

            replaced = root / "replaced.zip"
            original_inspect = release_review_archive._inspect_bytes

            def replace_after_inspection(content):
                summary = original_inspect(content)
                replaced.unlink()
                replaced.write_bytes(b"replacement must be preserved\n")
                return summary

            with patch.object(
                release_review_archive,
                "_inspect_bytes",
                side_effect=replace_after_inspection,
            ):
                with self.assertRaisesRegex(
                    release_review_archive.ReviewArchiveError,
                    "path or content changed during publication",
                ):
                    release_review_archive.create_review_archive(
                        review, replaced
                    )
            self.assertEqual(
                b"replacement must be preserved\n", replaced.read_bytes()
            )

            corrupted = root / "corrupted.zip"

            def corrupt_after_inspection(content):
                summary = original_inspect(content)
                identity = corrupted.stat().st_ino
                corrupted.write_bytes(b"in-place corruption\n")
                self.assertEqual(identity, corrupted.stat().st_ino)
                return summary

            with patch.object(
                release_review_archive,
                "_inspect_bytes",
                side_effect=corrupt_after_inspection,
            ):
                with self.assertRaisesRegex(
                    release_review_archive.ReviewArchiveError,
                    "path or content changed during publication",
                ):
                    release_review_archive.create_review_archive(
                        review, corrupted
                    )
            self.assertFalse(corrupted.exists())

    def test_bounds_cli_errors_and_optimized_control_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review = root / "review"
            self._prepare(review)
            archive = root / "valid.zip"
            release_review_archive.create_review_archive(review, archive)
            with patch.object(
                release_review_archive, "MAX_ARCHIVE_BYTES", 1
            ):
                with self.assertRaisesRegex(
                    release_review_archive.ReviewArchiveError, "size"
                ):
                    release_review_archive.inspect_review_archive(archive)
            with patch.object(
                release_review_archive, "MAX_ARCHIVE_MEMBERS", 1
            ):
                with self.assertRaisesRegex(
                    release_review_archive.ReviewArchiveError, "member count"
                ):
                    release_review_archive.inspect_review_archive(archive)

            target = root / "target.zip"
            target.write_bytes(archive.read_bytes())
            input_parent = root / "input-parent"
            input_parent.mkdir()
            raced = input_parent / "raced.zip"
            raced.write_bytes(b"replace me")
            input_parent_renamed = root / "input-parent-renamed"
            alternate_input = root / "alternate-input"
            alternate_input.mkdir()
            (alternate_input / raced.name).write_bytes(target.read_bytes())
            original_open = release_review_archive.os.open
            swapped_input = False

            def swap_input_parent(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal swapped_input
                if path == input_parent.name and not swapped_input:
                    swapped_input = True
                    input_parent.rename(input_parent_renamed)
                    input_parent.symlink_to(
                        alternate_input, target_is_directory=True
                    )
                if dir_fd is None:
                    return original_open(path, flags, mode)
                return original_open(path, flags, mode, dir_fd=dir_fd)

            with patch.object(
                release_review_archive.os,
                "open",
                side_effect=swap_input_parent,
            ):
                with self.assertRaisesRegex(
                    release_review_archive.ReviewArchiveError,
                    "parent is unavailable",
                ):
                    release_review_archive.inspect_review_archive(raced)
            self.assertTrue(input_parent.is_symlink())
            self.assertEqual(
                b"replace me",
                (input_parent_renamed / raced.name).read_bytes(),
            )

            invalid = root / "invalid.zip"
            invalid.write_bytes(
                self._invalid_utf8_name(archive.read_bytes())
            )
            output = io.StringIO()
            with redirect_stderr(output):
                result = release_review_archive.main([
                    "inspect", str(invalid),
                ])
            self.assertEqual(2, result)
            self.assertIn("chimera review archive:", output.getvalue())
            self.assertNotIn("Traceback", output.getvalue())

            surrogate = root / "surrogate.zip"
            surrogate.write_bytes(self._zip_bytes([(
                release_review_rehearsal.RECEIPT_NAME,
                b'{"artifacts":[],"x":"\\ud800"}\n',
            )]))
            output = io.StringIO()
            with redirect_stderr(output):
                result = release_review_archive.main([
                    "inspect", str(surrogate),
                ])
            self.assertEqual(2, result)
            self.assertIn("canonical UTF-8 JSON", output.getvalue())
            self.assertNotIn("Traceback", output.getvalue())

            oversized_integer = root / "oversized-integer.zip"
            oversized_integer.write_bytes(self._zip_bytes([(
                release_review_rehearsal.RECEIPT_NAME,
                b'{"artifacts":[],"n":' + b"1" * 5_000 + b"}\n",
            )]))
            output = io.StringIO()
            with redirect_stderr(output):
                result = release_review_archive.main([
                    "inspect", str(oversized_integer),
                ])
            self.assertEqual(2, result)
            self.assertIn("canonical UTF-8 JSON", output.getvalue())
            self.assertNotIn("Traceback", output.getvalue())

        source = Path(
            release_review_archive.__file__
        ).read_text(encoding="utf-8")
        self.assertFalse(
            any(
                isinstance(node, ast.Assert)
                for node in ast.walk(ast.parse(source))
            ),
            "review archive controls must survive optimized Python",
        )
        workflow = (
            release_review_archive.ROOT / ".github/workflows/test.yml"
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
