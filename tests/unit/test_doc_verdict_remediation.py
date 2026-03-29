"""Tests for Issue #624 — doc-master verdict remediation-aware logic.

Validates that implement.md STEP 12 correctly handles doc-master
re-invocation after STEP 11 remediation.
"""
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestDocVerdictRemediation:
    """Validate implement.md has remediation-aware doc-drift logic."""

    def _read_implement_md(self) -> str:
        return (PROJECT_ROOT / "plugins/autonomous-dev/commands/implement.md").read_text()

    def test_step12_has_remediation_aware_section(self):
        """STEP 12 must contain remediation-aware doc-drift logic."""
        content = self._read_implement_md()
        assert "Remediation-Aware Doc-Drift" in content, (
            "implement.md STEP 12 must contain 'Remediation-Aware Doc-Drift' section"
        )

    def test_step12_discards_stale_background_result(self):
        """When remediation occurred, STEP 12 must discard stale STEP 10 result."""
        content = self._read_implement_md()
        # Check for instruction to discard stale result
        assert re.search(r"(?i)discard.*step\s*10.*background", content), (
            "implement.md must instruct to DISCARD the stale STEP 10 background doc-master result"
        )

    def test_step12_uses_git_diff_for_current_files(self):
        """STEP 12 re-invocation must use git diff for current file list."""
        content = self._read_implement_md()
        assert "git diff --name-only" in content, (
            "implement.md STEP 12 must use 'git diff --name-only' to get current changed files"
        )

    def test_step12_reinvocation_is_blocking(self):
        """STEP 12 re-invocation must be blocking (not run_in_background)."""
        content = self._read_implement_md()
        # Check that the remediation section specifies blocking
        assert re.search(r"(?i)re-invoke.*doc-master.*blocking.*not.*background", content), (
            "implement.md must specify doc-master re-invocation as BLOCKING (not background)"
        )

    def test_step12_logs_reinvocation(self):
        """STEP 12 must log DOC-VERDICT-REINVOKE when re-invoking after remediation."""
        content = self._read_implement_md()
        assert "DOC-VERDICT-REINVOKE" in content, (
            "implement.md must log [DOC-VERDICT-REINVOKE] when re-invoking doc-master after remediation"
        )

    def test_retry_uses_current_file_list(self):
        """The existing retry logic must also use current git diff, not stale file list."""
        content = self._read_implement_md()
        # Find the retry section and verify it mentions current file list
        retry_match = re.search(r"DOC-VERDICT-RETRY.*?current file list", content, re.DOTALL)
        assert retry_match, (
            "implement.md retry logic must reference 'current file list' from git diff"
        )

    def test_non_remediation_path_unchanged(self):
        """When no remediation occurred, the original STEP 10 background flow is used."""
        content = self._read_implement_md()
        assert re.search(r"(?i)did not.*trigger.*remediation.*original.*step\s*10.*background", content), (
            "implement.md must preserve the original STEP 10 background collection flow for non-remediation cases"
        )
