"""Regression tests for gh issue create self-blocking bug (Issue #647, #663).

Bug: /create-issue and related commands invoke gh issue create via Bash, but
the PreToolUse hook blocks the gh command BEFORE the context file is written.
The Skill tool must auto-write the context file so _is_issue_command_active()
returns True when the subsequent Bash call fires.

Fix: In the NATIVE_TOOLS fast path, when tool_name == "Skill" and the skill
name is in GH_ISSUE_COMMANDS, auto-write the context file.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add the hooks directory to sys.path so we can import the function under test
HOOKS_DIR = str(
    Path(__file__).resolve().parent.parent.parent.parent
    / "plugins"
    / "autonomous-dev"
    / "hooks"
)
LIB_DIR = str(
    Path(__file__).resolve().parent.parent.parent.parent
    / "plugins"
    / "autonomous-dev"
    / "lib"
)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

from unified_pre_tool import (
    GH_ISSUE_COMMAND_CONTEXT_PATH,
    GH_ISSUE_COMMANDS,
    _detect_gh_issue_create,
    _is_issue_command_active,
    _maybe_write_issue_context,
)


@pytest.fixture(autouse=True)
def clean_context_file():
    """Remove the context file before and after each test."""
    ctx = Path(GH_ISSUE_COMMAND_CONTEXT_PATH)
    if ctx.exists():
        ctx.unlink()
    yield
    if ctx.exists():
        ctx.unlink()


class TestSkillWritesContextFile:
    """Verify that the Skill tool handler writes the context file for issue commands."""

    @pytest.mark.parametrize("skill_name", sorted(GH_ISSUE_COMMANDS))
    def test_all_gh_issue_commands_write_context(self, skill_name: str) -> None:
        """Each of the 5 GH_ISSUE_COMMANDS should write a valid context file."""
        _maybe_write_issue_context({"skill": skill_name})

        ctx = Path(GH_ISSUE_COMMAND_CONTEXT_PATH)
        assert ctx.exists(), f"Context file not written for skill '{skill_name}'"

        data = json.loads(ctx.read_text())
        assert data["command"] == skill_name
        assert "timestamp" in data

    def test_slash_prefix_stripped(self) -> None:
        """Skill name with leading / should be normalized."""
        _maybe_write_issue_context({"skill": "/create-issue"})

        ctx = Path(GH_ISSUE_COMMAND_CONTEXT_PATH)
        assert ctx.exists()
        data = json.loads(ctx.read_text())
        assert data["command"] == "create-issue"

    def test_non_issue_command_does_not_write_context(self) -> None:
        """A Skill that is NOT an issue command should not create the context file."""
        _maybe_write_issue_context({"skill": "some-other-skill"})

        ctx = Path(GH_ISSUE_COMMAND_CONTEXT_PATH)
        assert not ctx.exists()


class TestIsIssueCommandActiveAfterSkill:
    """Verify _is_issue_command_active() returns True after Skill writes context."""

    def _write_context(self, command: str) -> None:
        """Write a fresh context file as the Skill tool would."""
        from datetime import datetime, timezone

        with open(GH_ISSUE_COMMAND_CONTEXT_PATH, "w") as f:
            json.dump(
                {
                    "command": command,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                f,
            )

    @pytest.mark.parametrize("command", sorted(GH_ISSUE_COMMANDS))
    def test_active_after_fresh_context(self, command: str) -> None:
        """_is_issue_command_active() returns True when context is fresh."""
        self._write_context(command)
        assert _is_issue_command_active() is True

    def test_stale_context_not_honored(self) -> None:
        """Context file older than 1 hour should NOT be honored."""
        self._write_context("create-issue")

        # Set mtime to 2 hours ago
        ctx = Path(GH_ISSUE_COMMAND_CONTEXT_PATH)
        old_time = time.time() - 7200
        os.utime(str(ctx), (old_time, old_time))

        assert _is_issue_command_active() is False

    def test_no_context_file(self) -> None:
        """No context file => not active."""
        assert _is_issue_command_active() is False


class TestFullFlowSkillThenBash:
    """End-to-end: Skill sets context, then Bash gh issue create is allowed."""

    def _write_context(self, command: str) -> None:
        """Write a fresh context file as the Skill tool would."""
        from datetime import datetime, timezone

        with open(GH_ISSUE_COMMAND_CONTEXT_PATH, "w") as f:
            json.dump(
                {
                    "command": command,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                f,
            )

    @patch("unified_pre_tool._is_pipeline_active", return_value=False)
    @patch("unified_pre_tool._get_active_agent_name", return_value="")
    def test_gh_issue_create_allowed_with_context(
        self, mock_agent: object, mock_pipeline: object
    ) -> None:
        """After Skill writes context, _detect_gh_issue_create should return None (allow)."""
        self._write_context("create-issue")

        result = _detect_gh_issue_create("gh issue create --title 'test' --body 'body'")
        assert result is None, f"Expected allow (None), got block: {result}"

    @patch("unified_pre_tool._is_pipeline_active", return_value=False)
    @patch("unified_pre_tool._get_active_agent_name", return_value="")
    @patch("unified_pre_tool.GH_ISSUE_MARKER_PATH", "/tmp/nonexistent_marker_test_selfblock")
    def test_gh_issue_create_blocked_without_context(
        self, mock_agent: object, mock_pipeline: object
    ) -> None:
        """Without context file, gh issue create should be BLOCKED."""
        # clean_context_file fixture guarantees no context file exists
        # GH_ISSUE_MARKER_PATH patched to nonexistent path
        result = _detect_gh_issue_create("gh issue create --title 'test' --body 'body'")
        assert result is not None, "Expected block, got allow"
        assert "BLOCKED" in result

    @patch("unified_pre_tool._is_pipeline_active", return_value=False)
    @patch("unified_pre_tool._get_active_agent_name", return_value="")
    def test_subprocess_bypass_allowed_with_context(
        self, mock_agent: object, mock_pipeline: object
    ) -> None:
        """Subprocess-wrapped gh issue create should also be allowed with context."""
        self._write_context("improve")

        cmd = "python3 -c \"import subprocess; subprocess.run(['gh', 'issue', 'create'])\""
        result = _detect_gh_issue_create(cmd)
        assert result is None, f"Expected allow (None), got block: {result}"
