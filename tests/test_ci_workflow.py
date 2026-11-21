import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"

EXPECTED_ACTIONS = {
    "actions/checkout": (
        "fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09",
        "v5.1.0",
    ),
    "actions/setup-python": (
        "ece7cb06caefa5fff74198d8649806c4678c61a1",
        "v6.3.0",
    ),
}

USES_LINE = re.compile(
    r"^\s*uses:\s*([^@\s]+)@([0-9a-f]+)\s+#\s+(v[0-9]+(?:\.[0-9]+){2})\s*$"
)


class CiWorkflowTests(unittest.TestCase):
    def test_official_actions_use_reviewed_node24_release_pins(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        observed = []
        for line in workflow.splitlines():
            if "uses:" not in line:
                continue
            match = USES_LINE.fullmatch(line)
            self.assertIsNotNone(
                match,
                f"every action must use a reviewed 40-character SHA and patch tag: {line}",
            )
            action, commit, version = match.groups()
            self.assertIn(action, EXPECTED_ACTIONS)
            self.assertEqual(40, len(commit))
            self.assertEqual(EXPECTED_ACTIONS[action], (commit, version))
            observed.append(action)

        self.assertEqual(
            ["actions/checkout", "actions/setup-python"] * 2,
            observed,
        )

    def test_checkout_credentials_remain_disabled(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(2, workflow.count("persist-credentials: false"))


if __name__ == "__main__":
    unittest.main()
