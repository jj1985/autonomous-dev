"""Regression test: Issue #746 — security-auditor must re-run after remediation."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_CMD = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"


class TestSecurityReauditAfterRemediation:
    def setup_method(self):
        self.content = IMPLEMENT_CMD.read_text()

    def test_security_reaudit_after_remediation_mentioned(self):
        """STEP 11 must require security-auditor re-run after remediation."""
        assert re.search(r"security.auditor.*re.?run.*remediation|remediation.*re.?run.*security.auditor",
                        self.content, re.IGNORECASE), \
            "implement.md must mention security-auditor re-run after remediation"

    def test_stale_pass_forbidden(self):
        """Must forbid accepting pre-remediation security-auditor PASS."""
        assert "stale" in self.content.lower() or "pre-remediation" in self.content.lower(), \
            "implement.md must warn about stale/pre-remediation security-auditor verdicts"
