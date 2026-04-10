"""Regression test: Issue #741 — doc-master must not fold prior-commit CHANGELOG drift."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_MASTER = REPO_ROOT / "plugins" / "autonomous-dev" / "agents" / "doc-master.md"


class TestDocMasterChangelogScopeBoundary:
    """Verify doc-master has CHANGELOG scope boundary enforcement."""

    def setup_method(self):
        self.content = DOC_MASTER.read_text()

    def test_changelog_scope_boundary_section_exists(self):
        """doc-master.md must contain CHANGELOG Scope Boundary section."""
        assert "CHANGELOG Scope Boundary" in self.content

    def test_forbidden_silent_folding(self):
        """doc-master must forbid silently folding prior-commit drift."""
        assert "silently folding" in self.content.lower()

    def test_prior_commit_drift_must_be_reported(self):
        """doc-master must require reporting prior-commit drift as a finding."""
        assert "DOC-DRIFT-FOUND (prior commit)" in self.content

    def test_scope_check_heuristic_present(self):
        """doc-master must include git diff scope check heuristic."""
        assert "git diff --name-only" in self.content
