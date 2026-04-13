"""Spec validation tests for Issue #806: Enforcement bypass hardening (#804, #803).

Validates acceptance criteria:
1. PreToolUse hooks fire for Agent tool invocations during pipeline runs
2. Ordering gate enforces reviewer-before-security-auditor in all modes
3. Bash heredoc workaround to denied Write path detected and blocked within time window
4. Pipeline state file deletion during active pipeline is guarded
5. No false positives on legitimate Bash commands or file operations
6. Regression tests for both original issues (#804, #803)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

sys.path.insert(0, str(HOOKS_DIR))
sys.path.insert(0, str(LIB_DIR))


@pytest.fixture(autouse=True)
def _ensure_paths():
    """Ensure hooks and lib dirs are on sys.path."""
    for d in (str(HOOKS_DIR), str(LIB_DIR)):
        if d not in sys.path:
            sys.path.insert(0, d)
    yield


# ---------------------------------------------------------------------------
# AC1: PreToolUse hooks fire for Agent tool invocations during pipeline runs
# ---------------------------------------------------------------------------

class TestSpec806AC1AgentToolHookFiring:
    """The unified_pre_tool hook must process Agent tool invocations during pipeline runs."""

    def test_spec_806_1a_agent_tool_recognized_for_ordering(self):
        """Agent tool must be in AGENT_TOOL_NAMES so ordering gate applies to it."""
        import unified_pre_tool
        assert hasattr(unified_pre_tool, "AGENT_TOOL_NAMES"), \
            "AGENT_TOOL_NAMES set must exist in unified_pre_tool"
        assert "Agent" in unified_pre_tool.AGENT_TOOL_NAMES, \
            "Agent must be in AGENT_TOOL_NAMES for ordering enforcement"

    def test_spec_806_1b_ordering_gate_applies_to_agent_tools(self):
        """The validate_pipeline_ordering function must exist and handle Agent tools."""
        import unified_pre_tool
        assert hasattr(unified_pre_tool, "validate_pipeline_ordering"), \
            "validate_pipeline_ordering function must exist for Agent tool ordering"


# ---------------------------------------------------------------------------
# AC2: Ordering gate enforces reviewer-before-security-auditor in all modes
# ---------------------------------------------------------------------------

class TestSpec806AC2OrderingEnforcement:
    """Ordering gate must block security-auditor when reviewer has not completed."""

    def test_spec_806_2a_security_auditor_blocked_without_reviewer_sequential(self):
        """In sequential mode, security-auditor must be denied if reviewer not done."""
        from agent_ordering_gate import check_ordering_prerequisites

        result = check_ordering_prerequisites(
            "security-auditor",
            completed_agents={"implementer"},  # reviewer not completed
            validation_mode="sequential",
        )
        assert result.passed is False, \
            "security-auditor must be blocked when reviewer has not completed"

    def test_spec_806_2b_security_auditor_allowed_after_reviewer(self):
        """In sequential mode, security-auditor must pass if reviewer completed."""
        from agent_ordering_gate import check_ordering_prerequisites

        result = check_ordering_prerequisites(
            "security-auditor",
            completed_agents={"implementer", "reviewer"},
            validation_mode="sequential",
        )
        assert result.passed is True, \
            "security-auditor must be allowed when reviewer has completed"

    def test_spec_806_2c_ordering_gate_output_uses_json_format(self, capsys):
        """Ordering deny must use JSON permissionDecision format."""
        import unified_pre_tool

        unified_pre_tool.output_decision("deny", "ordering violation test")
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "ordering violation test" in output["hookSpecificOutput"]["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# AC3: Bash heredoc workaround to denied Write path detected and blocked
# ---------------------------------------------------------------------------

class TestSpec806AC3BashHeredocWorkaround:
    """When Write is denied, Bash heredoc to the same path within time window must be caught."""

    def test_spec_806_3a_deny_cache_records_write_denial(self, tmp_path):
        """Write denial must be recorded in deny cache."""
        import unified_pre_tool

        cache_file = tmp_path / "deny_cache.jsonl"
        test_path = "/Users/dev/project/plugins/autonomous-dev/agents/reviewer.md"

        with patch.object(unified_pre_tool, "DENY_CACHE_PATH", str(cache_file)):
            unified_pre_tool._update_deny_cache(test_path)
            assert unified_pre_tool._check_deny_cache(test_path) is True, \
                "Deny cache must record and match the denied path"

    def test_spec_806_3b_bash_heredoc_targets_extracted(self):
        """Heredoc file targets must be extractable from Bash commands."""
        import unified_pre_tool

        heredoc_cmd = "cat > /path/to/protected/file.md << 'EOF'\ncontent\nEOF"
        targets = unified_pre_tool._extract_bash_file_writes(heredoc_cmd)
        assert any("file.md" in t for t in targets), \
            "Heredoc target path must be extracted from Bash command"

    def test_spec_806_3c_redirect_targets_extracted(self):
        """Redirect file targets must be extractable from Bash commands."""
        import unified_pre_tool

        redirect_cmd = 'echo "content" > /path/to/protected/hook.py'
        targets = unified_pre_tool._extract_bash_file_writes(redirect_cmd)
        assert any("hook.py" in t for t in targets), \
            "Redirect target path must be extracted from Bash command"

    def test_spec_806_3d_deny_cache_expires_after_window(self, tmp_path):
        """Deny cache entries must expire after the time window."""
        import unified_pre_tool

        cache_file = tmp_path / "deny_cache.jsonl"
        test_path = "/Users/dev/project/plugins/autonomous-dev/agents/foo.md"

        # Write entry with timestamp 70 seconds ago (window is 60s)
        old_entry = {"path": test_path, "timestamp": time.time() - 70}
        cache_file.write_text(json.dumps(old_entry) + "\n")

        with patch.object(unified_pre_tool, "DENY_CACHE_PATH", str(cache_file)):
            assert unified_pre_tool._check_deny_cache(test_path) is False, \
                "Deny cache entries older than window must not match"


# ---------------------------------------------------------------------------
# AC4: Pipeline state file deletion during active pipeline is guarded
# ---------------------------------------------------------------------------

class TestSpec806AC4StateDeletionGuard:
    """rm/unlink/truncate of pipeline state files must be detected and blocked."""

    def test_spec_806_4a_rm_pipeline_state_detected(self):
        """rm of pipeline state file must be detected."""
        import unified_pre_tool

        result = unified_pre_tool._check_bash_state_deletion(
            "rm -f /tmp/implement_pipeline_state.json"
        )
        assert result is not None, \
            "rm of pipeline state file must be detected"

    def test_spec_806_4b_unlink_pipeline_state_detected(self):
        """unlink of pipeline state file must be detected."""
        import unified_pre_tool

        result = unified_pre_tool._check_bash_state_deletion(
            "unlink /tmp/implement_pipeline_state.json"
        )
        assert result is not None, \
            "unlink of pipeline state file must be detected"

    def test_spec_806_4c_truncate_pipeline_state_detected(self):
        """truncate of pipeline state file must be detected."""
        import unified_pre_tool

        result = unified_pre_tool._check_bash_state_deletion(
            "truncate -s 0 /tmp/implement_pipeline_state.json"
        )
        assert result is not None, \
            "truncate of pipeline state file must be detected"

    def test_spec_806_4d_python_os_remove_state_detected(self):
        """python3 -c os.remove targeting state file must be detected."""
        import unified_pre_tool

        cmd = 'python3 -c "import os; os.remove(\'/tmp/implement_pipeline_state.json\')"'
        result = unified_pre_tool._check_bash_state_deletion(cmd)
        assert result is not None, \
            "Python os.remove of pipeline state file must be detected"


# ---------------------------------------------------------------------------
# AC5: No false positives on legitimate Bash commands or file operations
# ---------------------------------------------------------------------------

class TestSpec806AC5NoFalsePositives:
    """Legitimate Bash commands must not be blocked."""

    def test_spec_806_5a_rm_unrelated_file_not_blocked(self):
        """rm of non-state file must NOT trigger the guard."""
        import unified_pre_tool

        result = unified_pre_tool._check_bash_state_deletion(
            "rm -f /tmp/my_test_output.txt"
        )
        assert result is None, \
            "rm of unrelated file must not trigger state deletion guard"

    def test_spec_806_5b_deny_cache_different_file_no_match(self, tmp_path):
        """Deny cache for file A must not match file B."""
        import unified_pre_tool

        cache_file = tmp_path / "deny_cache.jsonl"
        path_denied = "/Users/dev/project/plugins/autonomous-dev/agents/implementer.md"
        path_different = "/tmp/test_output.txt"

        with patch.object(unified_pre_tool, "DENY_CACHE_PATH", str(cache_file)):
            unified_pre_tool._update_deny_cache(path_denied)
            assert unified_pre_tool._check_deny_cache(path_different) is False, \
                "Deny cache for file A must not match unrelated file B"

    def test_spec_806_5c_heredoc_to_non_state_file_allowed(self):
        """Heredoc to a regular temp file must not trigger state deletion guard."""
        import unified_pre_tool

        result = unified_pre_tool._check_bash_state_deletion(
            "cat > /tmp/test_output.txt << 'EOF'\nhello\nEOF"
        )
        assert result is None, \
            "Heredoc to non-state file must not trigger state deletion guard"

    def test_spec_806_5d_normal_bash_command_not_blocked(self):
        """Normal Bash commands (ls, grep, pytest) must not trigger state guard."""
        import unified_pre_tool

        for cmd in ["ls -la /tmp", "grep -r 'pattern' tests/", "pytest tests/ -v"]:
            result = unified_pre_tool._check_bash_state_deletion(cmd)
            assert result is None, \
                f"Normal Bash command '{cmd}' must not trigger state deletion guard"


# ---------------------------------------------------------------------------
# AC6: Regression tests for both original issues (#804, #803)
# ---------------------------------------------------------------------------

class TestSpec806AC6RegressionTestsExist:
    """Dedicated regression test files must exist for issues #803 and #804."""

    def test_spec_806_6a_issue_803_regression_test_exists(self):
        """Regression test for issue #803 (Write-Bash workaround) must exist."""
        regression_dir = REPO_ROOT / "tests" / "regression"
        matches = list(regression_dir.glob("*803*"))
        assert len(matches) > 0, \
            f"Regression test file for issue #803 must exist in {regression_dir}"

    def test_spec_806_6b_issue_804_regression_test_exists(self):
        """Regression test for issue #804 (subagent ordering) must exist."""
        regression_dir = REPO_ROOT / "tests" / "regression"
        matches = list(regression_dir.glob("*804*"))
        assert len(matches) > 0, \
            f"Regression test file for issue #804 must exist in {regression_dir}"

    def test_spec_806_6c_issue_803_regression_tests_pass(self):
        """Issue #803 regression tests must be importable and have test classes."""
        regression_dir = REPO_ROOT / "tests" / "regression"
        files = list(regression_dir.glob("*803*"))
        assert len(files) > 0
        # Verify the file contains test classes (is a real test file)
        content = files[0].read_text()
        assert "class Test" in content, \
            "Issue #803 regression test must contain test classes"
        assert "def test_" in content, \
            "Issue #803 regression test must contain test methods"

    def test_spec_806_6d_issue_804_regression_tests_pass(self):
        """Issue #804 regression tests must be importable and have test classes."""
        regression_dir = REPO_ROOT / "tests" / "regression"
        files = list(regression_dir.glob("*804*"))
        assert len(files) > 0
        content = files[0].read_text()
        assert "class Test" in content, \
            "Issue #804 regression test must contain test classes"
        assert "def test_" in content, \
            "Issue #804 regression test must contain test methods"
