"""Regression test: Issue #745 — coordinator must not apply remediation fixes directly."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_CMD = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"


class TestNoCoordinatorRemediation:
    def setup_method(self):
        self.content = IMPLEMENT_CMD.read_text()

    def test_forbids_direct_coordinator_fixes(self):
        """Coordinator must not apply remediation fixes directly."""
        assert re.search(r"(?i)applying remediation.*directly|direct.*remediation.*fix", self.content), \
            "implement.md must forbid coordinator applying remediation fixes directly"

    def test_forbids_context_pressure_justification(self):
        """Must not cite context pressure as justification for skipping implementer."""
        assert "context pressure" in self.content.lower() or "context compression" in self.content.lower(), \
            "implement.md must mention context pressure/compression as invalid justification"
