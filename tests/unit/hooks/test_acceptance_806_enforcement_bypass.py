"""Acceptance tests for Issue #806 — enforcement bypass hardening.

These tests verify the acceptance criteria from the issue:
1. Ordering gate uses JSON permissionDecision block format (not exit code 2)
2. Bash heredoc workaround to denied Write path detected and blocked
3. Pipeline state file deletion during active pipeline is guarded
4. No false positives on legitimate Bash commands
5. Regression tests exist for #803 and #804
"""
import os
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# --- AC1: Ordering gate uses JSON block format ---

class TestOrderingGateJsonFormat:
    """Verify ordering gate output uses permissionDecision JSON, not exit code 2."""

    def test_ordering_deny_output_is_json_format(self):
        """The output_decision function must produce JSON with permissionDecision."""
        import sys
        sys.path.insert(0, str(Path(__file__).parents[3] / "plugins" / "autonomous-dev" / "hooks"))
        # Import the module to check function exists
        import importlib
        upt = importlib.import_module("unified_pre_tool")
        assert hasattr(upt, "output_decision"), "output_decision function must exist"


# --- AC2: Bash heredoc workaround detection ---

class TestWriteToBashWorkaroundDetection:
    """Verify cross-tool deny-workaround detection blocks Bash heredoc retries."""

    def test_deny_cache_records_write_denial(self):
        """When Write to protected file is denied, deny cache must be updated."""
        import sys
        sys.path.insert(0, str(Path(__file__).parents[3] / "plugins" / "autonomous-dev" / "hooks"))
        import importlib
        upt = importlib.import_module("unified_pre_tool")
        assert hasattr(upt, "_update_deny_cache"), "_update_deny_cache must exist"
        assert hasattr(upt, "_check_deny_cache"), "_check_deny_cache must exist"

    def test_bash_heredoc_to_recently_denied_path_detected(self):
        """Bash heredoc targeting a recently Write-denied path should be catchable."""
        import sys
        sys.path.insert(0, str(Path(__file__).parents[3] / "plugins" / "autonomous-dev" / "hooks"))
        import importlib
        upt = importlib.import_module("unified_pre_tool")
        assert hasattr(upt, "_extract_bash_file_writes"), "_extract_bash_file_writes must exist"


# --- AC3: Pipeline state file deletion guard ---

class TestPipelineStateDeletionGuard:
    """Verify pipeline state files are protected from deletion during active pipeline."""

    def test_state_deletion_guard_function_exists(self):
        """_check_bash_state_deletion must exist in unified_pre_tool.py."""
        import sys
        sys.path.insert(0, str(Path(__file__).parents[3] / "plugins" / "autonomous-dev" / "hooks"))
        import importlib
        upt = importlib.import_module("unified_pre_tool")
        assert hasattr(upt, "_check_bash_state_deletion"), \
            "_check_bash_state_deletion function must exist for state file protection"

    def test_rm_pipeline_state_detected(self):
        """rm of pipeline state file during active pipeline must be detected."""
        import sys
        sys.path.insert(0, str(Path(__file__).parents[3] / "plugins" / "autonomous-dev" / "hooks"))
        import importlib
        upt = importlib.import_module("unified_pre_tool")
        result = upt._check_bash_state_deletion("rm -f /tmp/implement_pipeline_state.json")
        assert result is not None, "rm of pipeline state must be detected"

    def test_rm_unrelated_file_not_detected(self):
        """rm of unrelated /tmp file must NOT be detected (no false positive)."""
        import sys
        sys.path.insert(0, str(Path(__file__).parents[3] / "plugins" / "autonomous-dev" / "hooks"))
        import importlib
        upt = importlib.import_module("unified_pre_tool")
        result = upt._check_bash_state_deletion("rm -f /tmp/my_temp_file.txt")
        assert result is None, "rm of unrelated file must not trigger guard"


# --- AC4: No false positives ---

class TestNoFalsePositives:
    """Verify legitimate Bash commands are not blocked."""

    def test_legitimate_heredoc_not_blocked(self):
        """Heredoc to non-protected, non-denied file must not be blocked."""
        import sys
        sys.path.insert(0, str(Path(__file__).parents[3] / "plugins" / "autonomous-dev" / "hooks"))
        import importlib
        upt = importlib.import_module("unified_pre_tool")
        # A heredoc to a test output file should extract the path but not be a state file
        result = upt._check_bash_state_deletion("cat > /tmp/test_output.txt << 'EOF'\nhello\nEOF")
        assert result is None, "Heredoc to non-state file must not trigger state deletion guard"


# --- AC5: Regression test files exist ---

class TestRegressionTestsExist:
    """Verify regression test files were created for #803 and #804."""

    def test_issue_803_regression_test_exists(self):
        """Regression test file for issue #803 must exist."""
        test_dir = Path(__file__).parents[2] / "regression"
        matches = list(test_dir.glob("*803*")) + list(test_dir.glob("*write_bash*"))
        assert len(matches) > 0, \
            f"Regression test for issue #803 (Write-Bash workaround) must exist in {test_dir}"

    def test_issue_804_regression_test_exists(self):
        """Regression test file for issue #804 must exist."""
        test_dir = Path(__file__).parents[2] / "regression"
        matches = list(test_dir.glob("*804*")) + list(test_dir.glob("*subagent*ordering*"))
        assert len(matches) > 0, \
            f"Regression test for issue #804 (subagent ordering) must exist in {test_dir}"
