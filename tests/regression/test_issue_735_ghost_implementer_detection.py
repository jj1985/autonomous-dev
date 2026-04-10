"""Regression test: Issue #735 — ghost implementer detection in STEP 8."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_CMD = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"


class TestGhostImplementerDetection:
    def setup_method(self):
        self.content = IMPLEMENT_CMD.read_text()

    def test_ghost_invocation_detection_mentioned(self):
        """implement.md STEP 8 must mention ghost invocation detection."""
        assert "ghost" in self.content.lower() and "invocation" in self.content.lower()

    def test_retry_on_ghost(self):
        """implement.md must require retry on ghost implementer."""
        assert re.search(r"(?i)retry.*ghost|ghost.*retry", self.content)
