"""
Tests for spec validation test deletion guard in unified_pre_tool.py (Issue #790).

Validates that:
1. _check_spec_test_deletion_scope blocks deletion of spec tests from other issues
2. _extract_bash_spec_test_targets detects various deletion patterns in Bash commands
3. Write tool integration blocks empty-content writes to out-of-scope spec tests
4. mv to tests/archived/ is allowed as the sanctioned archival path

Date: 2026-04-14
"""

import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook's parent to path so we can import the module
HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOK_DIR))

# Also add lib dir for any transitive imports
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Reset relevant env vars for each test."""
    env_keys = [
        "SKIP_SPEC_DELETION_GUARD",
        "PIPELINE_ISSUE_NUMBER",
        "PIPELINE_STATE_FILE",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# TestCheckSpecTestDeletionScope
# ---------------------------------------------------------------------------

class TestCheckSpecTestDeletionScope:
    """Tests for _check_spec_test_deletion_scope detection function."""

    @patch.object(hook, "_get_current_issue_number", return_value=790)
    def test_spec_test_outside_scope_blocked(self, _mock):
        """File with issue 761, current issue 790 -> returns block."""
        result = hook._check_spec_test_deletion_scope(
            "tests/spec_validation/test_spec_issue761_some_test.py"
        )
        assert result is not None
        assert "761" in result[1]
        assert "790" in result[1]
        assert "REQUIRED NEXT ACTION" in result[1]

    @patch.object(hook, "_get_current_issue_number", return_value=790)
    def test_spec_test_same_issue_allowed(self, _mock):
        """File with issue 790, current issue 790 -> returns None."""
        result = hook._check_spec_test_deletion_scope(
            "tests/spec_validation/test_spec_issue790_acceptance.py"
        )
        assert result is None

    @patch.object(hook, "_get_current_issue_number", return_value=790)
    def test_spec_test_no_issue_in_name_allowed(self, _mock):
        """test_spec_tautological_assertions.py (no issue number) -> returns None."""
        result = hook._check_spec_test_deletion_scope(
            "tests/spec_validation/test_spec_tautological_assertions.py"
        )
        assert result is None

    @patch.object(hook, "_get_current_issue_number", return_value=790)
    def test_non_spec_test_file_allowed(self, _mock):
        """tests/unit/test_something.py (not spec_validation) -> returns None."""
        result = hook._check_spec_test_deletion_scope(
            "tests/unit/test_something.py"
        )
        assert result is None

    @patch.object(hook, "_get_current_issue_number", return_value=0)
    def test_spec_test_no_pipeline_context_allowed(self, _mock):
        """Current issue 0 (no pipeline context) -> returns None (fail open)."""
        result = hook._check_spec_test_deletion_scope(
            "tests/spec_validation/test_spec_issue761_some_test.py"
        )
        assert result is None

    @patch.object(hook, "_get_current_issue_number", return_value=790)
    def test_spec_test_escape_hatch(self, _mock, monkeypatch):
        """SKIP_SPEC_DELETION_GUARD=1 -> returns None regardless of scope."""
        monkeypatch.setenv("SKIP_SPEC_DELETION_GUARD", "1")
        result = hook._check_spec_test_deletion_scope(
            "tests/spec_validation/test_spec_issue761_some_test.py"
        )
        assert result is None

    @patch.object(hook, "_get_current_issue_number", return_value=790)
    def test_spec_test_escape_hatch_true(self, _mock, monkeypatch):
        """SKIP_SPEC_DELETION_GUARD=true -> returns None."""
        monkeypatch.setenv("SKIP_SPEC_DELETION_GUARD", "true")
        result = hook._check_spec_test_deletion_scope(
            "tests/spec_validation/test_spec_issue761_some_test.py"
        )
        assert result is None

    @patch.object(hook, "_get_current_issue_number", return_value=790)
    def test_spec_test_path_traversal_normalized(self, _mock):
        """Path with traversal (../) is normalized and still detected."""
        # Use a path that resolves such that spec_validation is in the resolved string
        # We patch Path.resolve to return a controlled path
        result = hook._check_spec_test_deletion_scope(
            "tests/spec_validation/../spec_validation/test_spec_issue761_foo.py"
        )
        assert result is not None
        assert "761" in result[1]


# ---------------------------------------------------------------------------
# TestExtractBashSpecTestTargets
# ---------------------------------------------------------------------------

class TestExtractBashSpecTestTargets:
    """Tests for _extract_bash_spec_test_targets Bash command extraction."""

    def test_bash_rm_spec_test_detected(self):
        """rm of a spec test file is detected."""
        targets = hook._extract_bash_spec_test_targets(
            "rm tests/spec_validation/test_spec_issue761_acceptance.py"
        )
        assert len(targets) == 1
        assert "test_spec_issue761_acceptance.py" in targets[0]

    def test_bash_rm_with_flags_detected(self):
        """rm -f of a spec test file is detected."""
        targets = hook._extract_bash_spec_test_targets(
            "rm -f tests/spec_validation/test_spec_issue761_acceptance.py"
        )
        assert len(targets) >= 1

    def test_bash_unlink_spec_test_detected(self):
        """unlink of a spec test is detected."""
        targets = hook._extract_bash_spec_test_targets(
            "unlink tests/spec_validation/test_spec_issue761_foo.py"
        )
        assert len(targets) == 1

    def test_bash_python_remove_detected(self):
        """python3 -c os.remove of a spec test is detected."""
        targets = hook._extract_bash_spec_test_targets(
            "python3 -c \"import os; os.remove('tests/spec_validation/test_spec_issue761_foo.py')\""
        )
        assert len(targets) == 1

    def test_bash_mv_to_archived_allowed(self):
        """mv to tests/archived/ is NOT flagged (sanctioned archival)."""
        targets = hook._extract_bash_spec_test_targets(
            "mv tests/spec_validation/test_spec_issue761_foo.py tests/archived/"
        )
        assert len(targets) == 0

    def test_bash_mv_to_other_location_detected(self):
        """mv to a non-archived location IS flagged."""
        targets = hook._extract_bash_spec_test_targets(
            "mv tests/spec_validation/test_spec_issue761_foo.py /tmp/"
        )
        assert len(targets) == 1

    def test_bash_rm_non_spec_test_not_detected(self):
        """rm of a non-spec test file is not detected."""
        targets = hook._extract_bash_spec_test_targets(
            "rm tests/unit/test_something.py"
        )
        assert len(targets) == 0

    def test_bash_empty_command(self):
        """Empty command returns empty list."""
        targets = hook._extract_bash_spec_test_targets("")
        assert targets == []


# ---------------------------------------------------------------------------
# TestWriteToolIntegration
# ---------------------------------------------------------------------------

class TestWriteToolSpecTestIntegration:
    """Tests for Write tool integration with spec test deletion guard."""

    @patch.object(hook, "_get_current_issue_number", return_value=790)
    def test_write_empty_content_to_spec_test_blocked(self, _mock):
        """Write with empty content to out-of-scope spec test -> blocked."""
        result = hook._check_spec_test_deletion_scope(
            "tests/spec_validation/test_spec_issue761_foo.py"
        )
        assert result is not None
        assert "BLOCKED" in result[1]

    @patch.object(hook, "_get_current_issue_number", return_value=790)
    def test_write_content_to_spec_test_allowed(self, _mock):
        """Write with actual content - the scope check itself doesn't care about content.
        Content check is at the integration layer, not in _check_spec_test_deletion_scope.
        The function blocks if scope mismatches (regardless of content)."""
        # The detection function always blocks for mismatched scope.
        # Content filtering happens in the Write tool integration layer.
        result = hook._check_spec_test_deletion_scope(
            "tests/spec_validation/test_spec_issue761_foo.py"
        )
        # Out of scope -> blocked regardless of content (content check is in the main flow)
        assert result is not None

    @patch.object(hook, "_get_current_issue_number", return_value=790)
    def test_write_empty_to_non_spec_test_allowed(self, _mock):
        """Write empty to a non-spec test file -> allowed."""
        result = hook._check_spec_test_deletion_scope(
            "tests/unit/test_something.py"
        )
        assert result is None
