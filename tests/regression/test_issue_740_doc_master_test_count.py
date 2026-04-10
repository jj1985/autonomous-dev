"""Regression test: Issue #740 — doc-master must verify test counts from git diff."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_MASTER = REPO_ROOT / "plugins" / "autonomous-dev" / "agents" / "doc-master.md"


class TestDocMasterTestCountVerification:
    def setup_method(self):
        self.content = DOC_MASTER.read_text()

    def test_test_count_verification_section_exists(self):
        assert "Test Count Verification" in self.content

    def test_uses_git_diff_for_counting(self):
        assert "git diff" in self.content
        assert "def test_" in self.content

    def test_forbidden_estimating_counts(self):
        assert "Estimating test counts" in self.content.lower() or \
               "estimating test counts" in self.content.lower()
