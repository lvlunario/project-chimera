"""Protect the runnable PM walkthrough against regression."""
from pathlib import Path
import subprocess
import sys
import unittest


class ApprovalDemoTests(unittest.TestCase):
    def test_walkthrough_normal_and_optimized(self):
        for flags in ([], ["-O"]):
            with self.subTest(flags=flags):
                result = subprocess.run([sys.executable, *flags, "-m", "examples.approval_demo"],
                                        cwd=Path(__file__).resolve().parents[1],
                                        capture_output=True, text=True, timeout=15, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.count("PASS:"), 6)
                self.assertIn("PM acceptance pending", result.stdout)
