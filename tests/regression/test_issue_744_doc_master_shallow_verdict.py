"""Regression test: Issue #744 — doc-master shallow verdict detection."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_CMD = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"


class TestDocMasterShallowVerdict:
    def setup_method(self):
        self.content = IMPLEMENT_CMD.read_text()

    def test_shallow_verdict_detection_mentioned(self):
        """implement.md must mention shallow verdict detection."""
        assert "DOC-VERDICT-SHALLOW" in self.content or "shallow" in self.content.lower()

    def test_minimum_word_count_specified(self):
        """implement.md must specify minimum word count for doc-master output."""
        assert re.search(r"(fewer than|minimum|less than)\s*\d+\s*words", self.content, re.IGNORECASE)
