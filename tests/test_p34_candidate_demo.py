"""Protect the integrated P3/P4 candidate control against evidence drift."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest


class P34CandidateDemoTests(unittest.TestCase):
    def test_candidate_control_does_not_depend_on_removable_asserts(self):
        path = Path(__file__).parents[1] / "examples" / "p34_candidate_demo.py"
        source = path.read_text(encoding="utf-8")
        self.assertFalse(
            any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(source))),
            "candidate checks must survive python -O",
        )

    def test_candidate_controls_normal_and_optimized(self):
        root = Path(__file__).resolve().parents[1]
        for flags in ([], ["-O"]):
            with self.subTest(flags=flags):
                result = subprocess.run(
                    [sys.executable, *flags, "-m", "examples.p34_candidate_demo"],
                    cwd=root, capture_output=True, text=True, timeout=60, check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(8, result.stdout.count("PASS P34-"))
                self.assertIn(
                    "Leo walkthrough and acceptance remain open", result.stdout
                )


if __name__ == "__main__":
    unittest.main()
