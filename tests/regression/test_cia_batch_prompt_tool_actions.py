"""
Regression test for per-issue CIA batch prompt requiring tool actions (Issue #683).

Bug: Per-issue CIA agents in batch mode produced reports entirely from context
passed in the prompt, without reading any log files, git diffs, or hook outputs.
They completed in <13s with 0 tool uses because everything was pre-digested.

Fix: Added REQUIRED TOOL ACTIONS block to the per-issue CIA prompt template in
implement-batch.md, forcing the agent to run git diff, read bypass patterns,
and grep for skip markers.

Date fixed: 2026-04-07
Issue: #683
"""

from pathlib import Path

import pytest


# Path to the implement-batch.md command file
BATCH_CMD_PATH = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "autonomous-dev"
    / "commands"
    / "implement-batch.md"
)


class TestCIABatchPromptToolActions:
    """Verify per-issue CIA prompt contains mandatory tool-use instructions."""

    def test_batch_command_file_exists(self) -> None:
        """Precondition: implement-batch.md must exist."""
        assert BATCH_CMD_PATH.exists(), f"Missing: {BATCH_CMD_PATH}"

    def test_prompt_contains_required_tool_actions_header(self) -> None:
        """The CIA prompt template must include REQUIRED TOOL ACTIONS block.

        Without this, the CIA agent reports from pre-digested context alone
        and performs 0 tool uses (the bug from Issue #683).
        """
        content = BATCH_CMD_PATH.read_text()
        assert "REQUIRED TOOL ACTIONS" in content, (
            "implement-batch.md missing 'REQUIRED TOOL ACTIONS' block in "
            "per-issue CIA prompt template. CIA agents will run 0 tool uses. "
            "See Issue #683."
        )

    def test_prompt_requires_git_diff_check(self) -> None:
        """CIA must be instructed to run git diff on tests/ directory."""
        content = BATCH_CMD_PATH.read_text()
        assert "git diff" in content and "tests/" in content, (
            "implement-batch.md CIA prompt must require 'git diff' on tests/ "
            "to detect @pytest.mark.skip additions and weakened assertions."
        )

    def test_prompt_requires_bypass_patterns_check(self) -> None:
        """CIA must be instructed to read known_bypass_patterns.json."""
        content = BATCH_CMD_PATH.read_text()
        assert "known_bypass_patterns" in content, (
            "implement-batch.md CIA prompt must require reading "
            "known_bypass_patterns.json to verify no undocumented bypasses."
        )

    def test_prompt_requires_skip_marker_grep(self) -> None:
        """CIA must be instructed to grep for pytest.mark.skip markers."""
        content = BATCH_CMD_PATH.read_text()
        assert "pytest.mark.skip" in content, (
            "implement-batch.md CIA prompt must require grepping for "
            "pytest.mark.skip to report skip marker count."
        )

    def test_description_says_required_tool_calls(self) -> None:
        """The description line must say 'REQUIRED tool calls', not just 'tool calls'."""
        content = BATCH_CMD_PATH.read_text()
        assert "REQUIRED tool calls" in content, (
            "implement-batch.md must describe CIA batch check as having "
            "'REQUIRED tool calls' (not optional). See Issue #683."
        )

    def test_prompt_forbids_context_only_reporting(self) -> None:
        """CIA prompt must explicitly say not to report from context alone."""
        content = BATCH_CMD_PATH.read_text()
        assert "do not report from context alone" in content.lower(), (
            "implement-batch.md CIA prompt must explicitly forbid reporting "
            "from context alone to prevent 0-tool-use behavior."
        )
