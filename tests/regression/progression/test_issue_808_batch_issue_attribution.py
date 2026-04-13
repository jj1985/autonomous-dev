#!/usr/bin/env python3
"""
Regression test for Issue #808: batch_issue_number mis-attribution in --fix mode.

Bug: doc-master, reviewer, CIA, and other downstream agents were logged as
issue=0 because BATCH CONTEXT block did not contain 'Issue #NNN' — only
the implementer prompt body did. The fix adds a structured 'Issue Number: N'
field to the BATCH CONTEXT template and updates the extractor to prefer it.

Date fixed: 2026-04-13
Issue: #808
"""

import sys
from pathlib import Path

# Add hooks directory to path
sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[3]
        / "plugins"
        / "autonomous-dev"
        / "hooks"
    ),
)

import session_activity_logger as sal


class TestIssue808BatchIssueAttribution:
    """Regression tests: batch_issue_number extracted for all downstream agents."""

    def _make_downstream_prompt(self, agent: str, issue_number: int) -> str:
        """Simulate the BATCH CONTEXT prompt as seen by doc-master/reviewer/CIA.

        These prompts include 'Issue Number: N' in the BATCH CONTEXT block
        but typically do NOT include 'Issue #N' in the body text.
        """
        return (
            f"**BATCH CONTEXT** (CRITICAL - Operating in worktree):\n"
            f"- Worktree Path: /Users/user/Dev/repo/.worktrees/batch-20260413-214236 (absolute path)\n"
            f"- Issue Number: {issue_number}\n"
            f"- ALL file operations MUST use absolute paths within this worktree\n"
            f"- Read/Write/Edit tools: Use absolute paths like "
            f"/Users/user/Dev/repo/.worktrees/batch-20260413-214236/src/file.py\n"
            f"- Bash commands: Run from worktree using: cd /Users/user/Dev/repo/.worktrees/batch-20260413-214236 && [command]\n\n"
            f"You are the {agent} agent. Perform your review/documentation task for this issue."
        )

    def test_doc_master_issue_extracted(self):
        """doc-master prompt with Issue Number: 808 gets batch_issue_number=808.

        This is the exact failure scenario from Issue #808.
        """
        prompt = self._make_downstream_prompt("doc-master", 808)
        result = sal._summarize_input(
            "Task",
            {
                "description": "Update documentation for implemented changes",
                "subagent_type": "doc-master",
                "prompt": prompt,
            },
        )
        assert result.get("batch_mode") is True, "batch_mode should be True"
        assert result.get("batch_issue_number") == 808, (
            f"Expected batch_issue_number=808, got {result.get('batch_issue_number')}. "
            "doc-master was logging as issue=0 before fix."
        )

    def test_reviewer_issue_extracted(self):
        """reviewer prompt with Issue Number: 808 gets batch_issue_number=808."""
        prompt = self._make_downstream_prompt("reviewer", 808)
        result = sal._summarize_input(
            "Task",
            {
                "description": "Review implementation",
                "subagent_type": "reviewer",
                "prompt": prompt,
            },
        )
        assert result.get("batch_mode") is True
        assert result.get("batch_issue_number") == 808

    def test_security_auditor_issue_extracted(self):
        """security-auditor prompt with Issue Number: 808 gets batch_issue_number=808."""
        prompt = self._make_downstream_prompt("security-auditor", 808)
        result = sal._summarize_input(
            "Task",
            {
                "description": "Security audit",
                "subagent_type": "security-auditor",
                "prompt": prompt,
            },
        )
        assert result.get("batch_mode") is True
        assert result.get("batch_issue_number") == 808

    def test_structured_field_no_inline_issue_hash(self):
        """Core regression: structured field works even when no 'Issue #N' in body.

        Before the fix, only re.search(r'Issue #(\\d+)') was used. A prompt
        with 'Issue Number: 808' but no 'Issue #808' would return issue=0.
        """
        # Deliberately omit "Issue #808" from the body — only use structured field
        prompt = (
            "**BATCH CONTEXT** (CRITICAL - Operating in worktree):\n"
            "- Worktree Path: /path/to/worktree\n"
            "- Issue Number: 808\n\n"
            "Perform documentation review. No inline issue hash present."
        )
        result = sal._summarize_input(
            "Task",
            {"description": "doc-master", "prompt": prompt},
        )
        assert result.get("batch_issue_number") == 808, (
            "Structured 'Issue Number: N' must be parsed even without 'Issue #N' in body. "
            "This is the exact bug from Issue #808."
        )

    def test_pre_fix_behavior_would_fail(self):
        """Documents that the old regex alone would miss the structured field.

        This test validates the regression guard works correctly: a prompt
        containing only 'Issue Number: 808' (not 'Issue #808') would have
        returned None under the old implementation.
        """
        import re

        prompt = (
            "**BATCH CONTEXT** (CRITICAL - Operating in worktree):\n"
            "- Issue Number: 808\n\n"
            "No inline issue hash here."
        )
        # Old pattern — should NOT match
        old_match = re.search(r"Issue #(\d+)", prompt)
        assert old_match is None, "Old regex should not match structured field"

        # New pattern — should match
        new_match = re.search(r"Issue Number:\s*(\d+)", prompt)
        assert new_match is not None, "New regex must match structured field"
        assert int(new_match.group(1)) == 808
