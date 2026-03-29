"""
Tests for gh issue create blocking in unified_pre_tool.py (Issue #599).

Validates:
1. _detect_gh_issue_create blocks direct gh issue create usage
2. Allow-through for pipeline active, authorized agents, marker file
3. Non-matching commands pass through

Date: 2026-03-29
"""

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook and lib directories to path
HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOK_DIR))

LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove pipeline/agent env vars to ensure clean state."""
    env_keys = [
        "SANDBOX_ENABLED", "PRE_TOOL_MCP_SECURITY", "PRE_TOOL_AGENT_AUTH",
        "PRE_TOOL_BATCH_PERMISSION", "MCP_AUTO_APPROVE", "ENFORCEMENT_LEVEL",
        "CLAUDE_AGENT_NAME", "PIPELINE_STATE_FILE", "CLAUDE_SESSION_ID",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def no_pipeline():
    """Patch _is_pipeline_active to return False."""
    with patch.object(hook, "_is_pipeline_active", return_value=False):
        yield


@pytest.fixture
def no_agent():
    """Patch _get_active_agent_name to return empty string."""
    with patch.object(hook, "_get_active_agent_name", return_value=""):
        yield


@pytest.fixture
def no_marker(tmp_path):
    """Patch GH_ISSUE_MARKER_PATH to a non-existent file."""
    fake_path = str(tmp_path / "nonexistent_marker")
    with patch.object(hook, "GH_ISSUE_MARKER_PATH", fake_path):
        yield fake_path


# ---------------------------------------------------------------------------
# TestGhIssueCreateBlocking — commands that SHOULD be blocked
# ---------------------------------------------------------------------------

class TestGhIssueCreateBlocking:
    """Tests for commands that should be blocked."""

    def test_bare_gh_issue_create(self, no_pipeline, no_agent, no_marker):
        """Basic 'gh issue create --title ...' should be blocked."""
        cmd = 'gh issue create --title "bug report" --body "details"'
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None
        assert "BLOCKED" in result
        assert "/create-issue" in result

    def test_gh_issue_create_with_flags(self, no_pipeline, no_agent, no_marker):
        """gh issue create with various flags should be blocked."""
        cmd = 'gh issue create -R owner/repo --title "test" --label "bug"'
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None
        assert "BLOCKED" in result

    def test_case_insensitive_blocking(self, no_pipeline, no_agent, no_marker):
        """Case variations like 'GH Issue Create' should be blocked."""
        cmd = 'GH Issue Create --title "test"'
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None
        assert "BLOCKED" in result

    def test_gh_issue_create_with_body_file(self, no_pipeline, no_agent, no_marker):
        """gh issue create --body-file should be blocked."""
        cmd = 'gh issue create --title "test" --body-file /tmp/body.md'
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None
        assert "BLOCKED" in result

    def test_stale_marker_blocks(self, no_pipeline, no_agent, tmp_path):
        """Marker file older than 1 hour should NOT allow through."""
        marker = tmp_path / "stale_marker"
        marker.touch()
        # Set mtime to 2 hours ago
        old_time = time.time() - 7200
        os.utime(str(marker), (old_time, old_time))

        with patch.object(hook, "GH_ISSUE_MARKER_PATH", str(marker)):
            cmd = 'gh issue create --title "test"'
            result = hook._detect_gh_issue_create(cmd)
            assert result is not None
            assert "BLOCKED" in result


# ---------------------------------------------------------------------------
# TestGhIssueCreateAllowThrough — commands that should be allowed
# ---------------------------------------------------------------------------

class TestGhIssueCreateAllowThrough:
    """Tests for commands that should be allowed through."""

    def test_non_matching_gh_issue_list(self, no_pipeline, no_agent, no_marker):
        """'gh issue list' should not be blocked."""
        result = hook._detect_gh_issue_create("gh issue list --state open")
        assert result is None

    def test_non_matching_gh_pr_create(self, no_pipeline, no_agent, no_marker):
        """'gh pr create' should not be blocked."""
        result = hook._detect_gh_issue_create("gh pr create --title 'test'")
        assert result is None

    def test_non_matching_gh_issue_close(self, no_pipeline, no_agent, no_marker):
        """'gh issue close' should not be blocked."""
        result = hook._detect_gh_issue_create("gh issue close 123")
        assert result is None

    def test_non_matching_gh_issue_view(self, no_pipeline, no_agent, no_marker):
        """'gh issue view' should not be blocked."""
        result = hook._detect_gh_issue_create("gh issue view 456")
        assert result is None

    def test_no_gh_at_all(self, no_pipeline, no_agent, no_marker):
        """Commands without gh should pass through."""
        result = hook._detect_gh_issue_create('echo "hello world"')
        assert result is None

    def test_pipeline_active_allows(self, no_agent, no_marker):
        """When pipeline is active, gh issue create should be allowed."""
        with patch.object(hook, "_is_pipeline_active", return_value=True):
            cmd = 'gh issue create --title "test"'
            result = hook._detect_gh_issue_create(cmd)
            assert result is None

    def test_continuous_improvement_analyst_allowed(self, no_pipeline, no_marker):
        """continuous-improvement-analyst agent should be allowed."""
        with patch.object(hook, "_get_active_agent_name",
                          return_value="continuous-improvement-analyst"):
            cmd = 'gh issue create --title "test"'
            result = hook._detect_gh_issue_create(cmd)
            assert result is None

    def test_issue_creator_agent_allowed(self, no_pipeline, no_marker):
        """issue-creator agent should be allowed."""
        with patch.object(hook, "_get_active_agent_name",
                          return_value="issue-creator"):
            cmd = 'gh issue create --title "test"'
            result = hook._detect_gh_issue_create(cmd)
            assert result is None

    def test_fresh_marker_allows(self, no_pipeline, no_agent, tmp_path):
        """Fresh marker file (< 1 hour) should allow through."""
        marker = tmp_path / "fresh_marker"
        marker.touch()  # Creates with current time

        with patch.object(hook, "GH_ISSUE_MARKER_PATH", str(marker)):
            cmd = 'gh issue create --title "test"'
            result = hook._detect_gh_issue_create(cmd)
            assert result is None


# ---------------------------------------------------------------------------
# TestGhIssueCreateEdgeCases
# ---------------------------------------------------------------------------

class TestGhIssueCreateEdgeCases:
    """Edge case tests for robustness."""

    def test_empty_command(self, no_pipeline, no_agent, no_marker):
        """Empty command should pass through."""
        result = hook._detect_gh_issue_create("")
        assert result is None

    def test_gh_issue_agents_constant_exists(self):
        """GH_ISSUE_AGENTS constant should be defined."""
        assert hasattr(hook, "GH_ISSUE_AGENTS")
        assert "continuous-improvement-analyst" in hook.GH_ISSUE_AGENTS
        assert "issue-creator" in hook.GH_ISSUE_AGENTS

    def test_gh_issue_marker_path_constant_exists(self):
        """GH_ISSUE_MARKER_PATH constant should be defined."""
        assert hasattr(hook, "GH_ISSUE_MARKER_PATH")
        assert "autonomous_dev_gh_issue" in hook.GH_ISSUE_MARKER_PATH

    def test_block_message_content(self, no_pipeline, no_agent, no_marker):
        """Block message should include actionable guidance."""
        cmd = 'gh issue create --title "test"'
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None
        assert "/create-issue" in result
        assert "/create-issue --quick" in result
        assert "duplicate detection" in result


# ---------------------------------------------------------------------------
# TestGhIssueCreateFalsePositives — regression tests for Issue #601
# ---------------------------------------------------------------------------

class TestGhIssueCreateFalsePositives:
    """Regression tests: text mentioning 'gh issue create' inside strings/heredocs
    should NOT trigger blocking. Only actual command invocations should be blocked."""

    def test_commit_message_with_gh_issue_create_allowed(
        self, no_pipeline, no_agent, no_marker
    ):
        """git commit -m with 'gh issue create' in the message should NOT be blocked."""
        cmd = 'git commit -m "fix: write gh-issue-create marker file"'
        result = hook._detect_gh_issue_create(cmd)
        assert result is None, (
            "Commit message mentioning 'gh issue create' should not be blocked"
        )

    def test_heredoc_commit_message_allowed(
        self, no_pipeline, no_agent, no_marker
    ):
        """Heredoc commit message mentioning 'gh issue create' should NOT be blocked."""
        cmd = (
            "git commit -m \"$(cat <<'EOF'\n"
            "fix gh issue create bug\n"
            "EOF\n"
            ")\""
        )
        result = hook._detect_gh_issue_create(cmd)
        assert result is None, (
            "Heredoc body mentioning 'gh issue create' should not be blocked"
        )

    def test_echo_mentioning_allowed(
        self, no_pipeline, no_agent, no_marker
    ):
        """echo statement mentioning 'gh issue create' should NOT be blocked."""
        cmd = 'echo "use gh issue create to file bugs"'
        result = hook._detect_gh_issue_create(cmd)
        assert result is None, (
            "echo with quoted 'gh issue create' should not be blocked"
        )

    def test_actual_gh_issue_create_still_blocked(
        self, no_pipeline, no_agent, no_marker
    ):
        """Actual 'gh issue create' command must STILL be blocked."""
        cmd = 'gh issue create --title "test" --body "details"'
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None
        assert "BLOCKED" in result

    def test_gh_issue_create_after_heredoc_blocked(
        self, no_pipeline, no_agent, no_marker
    ):
        """Heredoc followed by actual gh issue create should still be blocked."""
        cmd = (
            "cat <<'EOF'\nsome docs\nEOF\n"
            "gh issue create --title \"real command\""
        )
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None, (
            "Actual gh issue create after a heredoc should still be blocked"
        )
        assert "BLOCKED" in result

    def test_single_quoted_mention_allowed(
        self, no_pipeline, no_agent, no_marker
    ):
        """Single-quoted string mentioning 'gh issue create' should NOT be blocked."""
        cmd = "echo 'run gh issue create for issues'"
        result = hook._detect_gh_issue_create(cmd)
        assert result is None

    def test_commit_message_double_quoted_allowed(
        self, no_pipeline, no_agent, no_marker
    ):
        """Double-quoted commit message with 'gh issue create' should NOT be blocked."""
        cmd = 'git commit -m "docs: document gh issue create workflow"'
        result = hook._detect_gh_issue_create(cmd)
        assert result is None


# ---------------------------------------------------------------------------
# TestGhIssueCreateSubprocessBypass — Issue #618 regression tests
# ---------------------------------------------------------------------------

class TestGhIssueCreateSubprocessBypass:
    """Tests for subprocess bypass patterns that wrap 'gh issue create' inside
    python3 -c, sh -c, bash -c, backticks, etc. (Issue #618)."""

    def test_python3_subprocess_run_blocked(self, no_pipeline, no_agent, no_marker):
        """python3 -c with subprocess.run(['gh', 'issue', 'create']) should be blocked."""
        cmd = (
            "python3 -c \"import subprocess; "
            "subprocess.run(['gh', 'issue', 'create', '--title', 'test'])\""
        )
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None, (
            "subprocess.run(['gh', 'issue', 'create']) bypass must be blocked"
        )
        assert "BLOCKED" in result

    def test_python3_subprocess_call_blocked(self, no_pipeline, no_agent, no_marker):
        """python3 -c with subprocess.call(['gh', 'issue', 'create']) should be blocked."""
        cmd = (
            "python3 -c \"import subprocess; "
            "subprocess.call(['gh', 'issue', 'create', '--title', 'bug'])\""
        )
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None, (
            "subprocess.call(['gh', 'issue', 'create']) bypass must be blocked"
        )
        assert "BLOCKED" in result

    def test_python3_subprocess_popen_blocked(self, no_pipeline, no_agent, no_marker):
        """python3 -c with subprocess.Popen(['gh', 'issue', 'create']) should be blocked."""
        cmd = (
            "python3 -c \"import subprocess; "
            "subprocess.Popen(['gh', 'issue', 'create', '--title', 'test'])\""
        )
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None, (
            "subprocess.Popen(['gh', 'issue', 'create']) bypass must be blocked"
        )
        assert "BLOCKED" in result

    def test_python_os_system_blocked(self, no_pipeline, no_agent, no_marker):
        """python3 -c with os.system('gh issue create') should be blocked."""
        cmd = (
            "python3 -c \"import os; "
            "os.system('gh issue create --title test --body details')\""
        )
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None, (
            "os.system('gh issue create') bypass must be blocked"
        )
        assert "BLOCKED" in result

    def test_sh_c_gh_issue_create_blocked(self, no_pipeline, no_agent, no_marker):
        """sh -c 'gh issue create ...' should be blocked."""
        cmd = "sh -c 'gh issue create --title \"bypass\" --body \"test\"'"
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None, (
            "sh -c 'gh issue create' bypass must be blocked"
        )
        assert "BLOCKED" in result

    def test_bash_c_gh_issue_create_blocked(self, no_pipeline, no_agent, no_marker):
        """bash -c 'gh issue create ...' should be blocked."""
        cmd = "bash -c 'gh issue create --title \"bypass\" --body \"test\"'"
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None, (
            "bash -c 'gh issue create' bypass must be blocked"
        )
        assert "BLOCKED" in result

    def test_backtick_gh_issue_create_blocked(self, no_pipeline, no_agent, no_marker):
        """Backtick command substitution `gh issue create ...` should be blocked."""
        cmd = "RESULT=`gh issue create --title 'test' --body 'details'`"
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None, (
            "Backtick `gh issue create` bypass must be blocked"
        )
        assert "BLOCKED" in result

    def test_dollar_subst_gh_issue_create_blocked(self, no_pipeline, no_agent, no_marker):
        """$(gh issue create ...) command substitution should be blocked."""
        cmd = "RESULT=$(gh issue create --title 'test' --body 'details')"
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None, (
            "$(gh issue create) bypass must be blocked"
        )
        assert "BLOCKED" in result

    def test_python_subprocess_check_output_blocked(self, no_pipeline, no_agent, no_marker):
        """subprocess.check_output(['gh', 'issue', 'create']) should be blocked."""
        cmd = (
            "python3 -c \"import subprocess; "
            "subprocess.check_output(['gh', 'issue', 'create', '--title', 'x'])\""
        )
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None, (
            "subprocess.check_output(['gh', 'issue', 'create']) bypass must be blocked"
        )
        assert "BLOCKED" in result

    def test_bypass_blocked_pipeline_inactive_no_marker(
        self, no_pipeline, no_agent, no_marker
    ):
        """Bypass detection respects the same allow-throughs as direct detection."""
        cmd = (
            "python3 -c \"import subprocess; "
            "subprocess.run(['gh', 'issue', 'create', '--title', 'test'])\""
        )
        result = hook._detect_gh_issue_create(cmd)
        assert result is not None
        assert "BLOCKED" in result
        assert "/create-issue" in result

    def test_bypass_allowed_when_pipeline_active(self, no_agent, no_marker):
        """Subprocess bypass is allowed when pipeline is active."""
        with patch.object(hook, "_is_pipeline_active", return_value=True):
            cmd = (
                "python3 -c \"import subprocess; "
                "subprocess.run(['gh', 'issue', 'create', '--title', 'x'])\""
            )
            result = hook._detect_gh_issue_create(cmd)
            assert result is None

    def test_bypass_allowed_when_authorized_agent(self, no_pipeline, no_marker):
        """Subprocess bypass is allowed for authorized agents."""
        with patch.object(hook, "_get_active_agent_name",
                          return_value="continuous-improvement-analyst"):
            cmd = (
                "python3 -c \"import subprocess; "
                "subprocess.run(['gh', 'issue', 'create', '--title', 'x'])\""
            )
            result = hook._detect_gh_issue_create(cmd)
            assert result is None

    def test_subprocess_no_gh_issue_create_allowed(self, no_pipeline, no_agent, no_marker):
        """subprocess.run without gh issue create should NOT be blocked."""
        cmd = (
            "python3 -c \"import subprocess; "
            "subprocess.run(['gh', 'issue', 'list'])\""
        )
        result = hook._detect_gh_issue_create(cmd)
        assert result is None, (
            "subprocess.run without gh issue create must not be blocked"
        )

    def test_subprocess_gh_pr_create_allowed(self, no_pipeline, no_agent, no_marker):
        """subprocess.run(['gh', 'pr', 'create']) should NOT be blocked."""
        cmd = (
            "python3 -c \"import subprocess; "
            "subprocess.run(['gh', 'pr', 'create', '--title', 'x'])\""
        )
        result = hook._detect_gh_issue_create(cmd)
        assert result is None, (
            "subprocess.run with gh pr create must not be blocked"
        )


# ---------------------------------------------------------------------------
# TestContainsGhIssueCreateBypass — unit tests for the helper function
# ---------------------------------------------------------------------------

class TestContainsGhIssueCreateBypass:
    """Unit tests for the _contains_gh_issue_create_bypass helper (Issue #618)."""

    def test_subprocess_run_detected(self):
        """subprocess.run with gh issue create is detected."""
        cmd = "python3 -c \"subprocess.run(['gh', 'issue', 'create'])\""
        assert hook._contains_gh_issue_create_bypass(cmd) is True

    def test_subprocess_call_detected(self):
        """subprocess.call with gh issue create is detected."""
        cmd = "python3 -c \"subprocess.call(['gh', 'issue', 'create'])\""
        assert hook._contains_gh_issue_create_bypass(cmd) is True

    def test_subprocess_popen_detected(self):
        """subprocess.Popen with gh issue create is detected."""
        cmd = "python3 -c \"subprocess.Popen(['gh', 'issue', 'create'])\""
        assert hook._contains_gh_issue_create_bypass(cmd) is True

    def test_os_system_detected(self):
        """os.system('gh issue create') is detected."""
        cmd = "python3 -c \"os.system('gh issue create --title x')\""
        assert hook._contains_gh_issue_create_bypass(cmd) is True

    def test_sh_c_detected(self):
        """sh -c 'gh issue create' is detected."""
        cmd = "sh -c 'gh issue create --title test'"
        assert hook._contains_gh_issue_create_bypass(cmd) is True

    def test_bash_c_detected(self):
        """bash -c 'gh issue create' is detected."""
        cmd = "bash -c 'gh issue create --title test'"
        assert hook._contains_gh_issue_create_bypass(cmd) is True

    def test_backtick_detected(self):
        """Backtick gh issue create is detected."""
        cmd = "X=`gh issue create --title test`"
        assert hook._contains_gh_issue_create_bypass(cmd) is True

    def test_dollar_subst_detected(self):
        """$(gh issue create) is detected."""
        cmd = "X=$(gh issue create --title test)"
        assert hook._contains_gh_issue_create_bypass(cmd) is True

    def test_gh_issue_list_not_detected(self):
        """subprocess.run with gh issue list is NOT detected."""
        cmd = "python3 -c \"subprocess.run(['gh', 'issue', 'list'])\""
        assert hook._contains_gh_issue_create_bypass(cmd) is False

    def test_gh_pr_create_not_detected(self):
        """subprocess.run with gh pr create is NOT detected."""
        cmd = "python3 -c \"subprocess.run(['gh', 'pr', 'create'])\""
        assert hook._contains_gh_issue_create_bypass(cmd) is False

    def test_empty_command_not_detected(self):
        """Empty command is not detected as a bypass."""
        assert hook._contains_gh_issue_create_bypass("") is False

    def test_direct_gh_issue_create_not_detected_by_bypass(self):
        """Direct 'gh issue create' (no subprocess wrapper) is not a bypass pattern."""
        # The bypass detector is specifically for subprocess wrapping.
        # Direct calls are caught by the primary detector.
        cmd = "gh issue create --title test"
        assert hook._contains_gh_issue_create_bypass(cmd) is False
