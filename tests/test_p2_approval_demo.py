"""Protect the runnable P2 PM walkthrough against documentation drift."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from examples.p2_approval_demo import _run_control


class P2ApprovalDemoTests(unittest.TestCase):
    def test_approval_controls_do_not_depend_on_removable_asserts(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("link_csv_demo.py", "journal_export_demo.py",
                     "resume_demo.py", "journal_demo.py"):
            with self.subTest(name=name):
                source = (root / "examples" / name).read_text(encoding="utf-8")
                self.assertFalse(
                    any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(source))),
                    f"{name} approval checks must survive python -O",
                )

    def test_walkthrough_normal_and_optimized(self):
        root = Path(__file__).resolve().parents[1]
        for flags in ([], ["-O"]):
            with self.subTest(flags=flags):
                result = subprocess.run(
                    [sys.executable, *flags, "-m", "examples.p2_approval_demo"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(4, result.stdout.count("PASS P2-"))
                self.assertIn("PM verification/validation decision pending", result.stdout)

    def test_control_refuses_success_without_expected_evidence(self):
        completed = subprocess.CompletedProcess(
            args=["synthetic"], returncode=0, stdout="different output\n", stderr=""
        )
        with patch("examples.p2_approval_demo.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "omitted expected evidence"):
                _run_control("synthetic.module", ("required line",))

    def test_control_propagates_child_failure(self):
        completed = subprocess.CompletedProcess(
            args=["synthetic"], returncode=2, stdout="", stderr="synthetic error\n"
        )
        with patch("examples.p2_approval_demo.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "exited 2: synthetic error"):
                _run_control("synthetic.module", ())


if __name__ == "__main__":
    unittest.main()
