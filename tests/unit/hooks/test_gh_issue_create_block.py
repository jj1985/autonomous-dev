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
