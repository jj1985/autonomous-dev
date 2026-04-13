#!/usr/bin/env python3
"""
Spec validation tests for Issue #808: batch_issue_number mis-attribution in --fix mode.

Acceptance criteria:
1. Downstream agents (reviewer/doc-master/security-auditor/CIA) get correct batch_issue_number
2. BATCH CONTEXT template includes "Issue Number: $ISSUE_NUMBER"
3. _summarize_input() prefers structured "Issue Number: N" over "Issue #N"
4. All existing TestBatchContextDetection tests continue to pass
5. A regression test for Issue #808 exists and passes

Date: 2026-04-13
"""

import re
import sys
from pathlib import Path

import pytest

# Add hooks directory to path for importing session_activity_logger
sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / "plugins"
        / "autonomous-dev"
        / "hooks"
    ),
)

import session_activity_logger as sal

WORKTREE = Path(__file__).resolve().parents[2]
IMPLEMENT_BATCH_MD = (
    WORKTREE / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"
)
REGRESSION_TEST_FILE = (
    WORKTREE
    / "tests"
    / "regression"
    / "progression"
    / "test_issue_808_batch_issue_attribution.py"
)


def _make_batch_context_prompt(agent_name: str, issue_number: int) -> str:
    """Build a realistic BATCH CONTEXT prompt as downstream agents would receive."""
    return (
        f"**BATCH CONTEXT** (CRITICAL - Operating in worktree):\n"
        f"- Worktree Path: /Users/dev/repo/.worktrees/batch-20260413-214236 (absolute path)\n"
        f"- Issue Number: {issue_number}\n"
        f"- ALL file operations MUST use absolute paths within this worktree\n\n"
        f"You are the {agent_name} agent. Perform your task."
    )


class TestSpecIssue808:
    """Spec validation for Issue #808 acceptance criteria."""

    # --- Criterion 1: Downstream agents get correct batch_issue_number ---

    @pytest.mark.parametrize(
        "agent_name",
        ["reviewer", "doc-master", "security-auditor", "continuous-improvement-analyst"],
    )
    def test_spec_issue808_1_downstream_agents_get_correct_issue_number(
        self, agent_name: str
    ):
        """AC1: When batch coordinator invokes reviewer/doc-master/security-auditor/CIA,
        session activity log MUST contain batch_issue_number matching the actual issue."""
        prompt = _make_batch_context_prompt(agent_name, 808)
        result = sal._summarize_input(
            "Task",
            {
                "description": f"{agent_name} task",
                "subagent_type": agent_name,
                "prompt": prompt,
            },
        )
        assert result.get("batch_issue_number") == 808, (
            f"{agent_name} should have batch_issue_number=808, got "
            f"{result.get('batch_issue_number')}"
        )

    # --- Criterion 2: BATCH CONTEXT template includes Issue Number field ---

    def test_spec_issue808_2_batch_context_template_contains_issue_number_field(self):
        """AC2: BATCH CONTEXT template in implement-batch.md MUST include
        'Issue Number: $ISSUE_NUMBER'."""
        assert IMPLEMENT_BATCH_MD.exists(), (
            f"implement-batch.md not found at {IMPLEMENT_BATCH_MD}"
        )
        content = IMPLEMENT_BATCH_MD.read_text()
        # The template must contain the structured Issue Number field
        assert "Issue Number:" in content, (
            "BATCH CONTEXT template must include 'Issue Number:' field"
        )
        # Verify it appears within a BATCH CONTEXT block
        assert re.search(
            r"BATCH CONTEXT.*?Issue Number:", content, re.DOTALL
        ), "Issue Number field must appear within BATCH CONTEXT block"

    # --- Criterion 3: Structured field preferred over inline Issue #N ---

    def test_spec_issue808_3a_structured_field_extracted_first(self):
        """AC3: _summarize_input() MUST extract from 'Issue Number: N' first."""
        prompt = (
            "**BATCH CONTEXT** (CRITICAL - Operating in worktree):\n"
            "- Issue Number: 42\n\n"
            "Review the changes. See also Issue #99 for background."
        )
        result = sal._summarize_input(
            "Task",
            {"description": "reviewer", "subagent_type": "reviewer", "prompt": prompt},
        )
        assert result.get("batch_issue_number") == 42, (
            f"Should prefer structured 'Issue Number: 42' over 'Issue #99', "
            f"got {result.get('batch_issue_number')}"
        )

    def test_spec_issue808_3b_fallback_to_issue_hash(self):
        """AC3: Falls back to 'Issue #N' when no structured field present."""
        prompt = (
            "BATCH CONTEXT - Operating in worktree.\n"
            "Implement fixes for Issue #526 in batch mode."
        )
        result = sal._summarize_input(
            "Task",
            {"description": "implementer", "prompt": prompt},
        )
        assert result.get("batch_issue_number") == 526, (
            f"Should fall back to 'Issue #526', got {result.get('batch_issue_number')}"
        )

    def test_spec_issue808_3c_structured_only_no_inline(self):
        """AC3: Structured field works even when prompt has NO 'Issue #N' at all."""
        prompt = (
            "**BATCH CONTEXT** (CRITICAL - Operating in worktree):\n"
            "- Worktree Path: /path/to/worktree\n"
            "- Issue Number: 123\n\n"
            "Update documentation. No inline issue hash present."
        )
        result = sal._summarize_input(
            "Task",
            {"description": "doc-master", "prompt": prompt},
        )
        assert result.get("batch_issue_number") == 123, (
            f"Structured field alone must yield 123, got {result.get('batch_issue_number')}"
        )

    # --- Criterion 4: Backward compatibility ---

    def test_spec_issue808_4a_legacy_batch_context_still_detected(self):
        """AC4: Old-style BATCH CONTEXT with only 'Issue #N' still works."""
        result = sal._summarize_input(
            "Task",
            {
                "description": "implementer",
                "subagent_type": "implementer",
                "prompt": "BATCH CONTEXT - Operating in worktree. Implement Issue #42.",
            },
        )
        assert result.get("batch_mode") is True
        assert result.get("batch_issue_number") == 42

    def test_spec_issue808_4b_no_batch_context_unaffected(self):
        """AC4: Non-batch prompts remain unaffected."""
        result = sal._summarize_input(
            "Task",
            {
                "description": "normal task",
                "prompt": "Implement JWT authentication for Issue #99.",
            },
        )
        assert result.get("batch_mode") is None
        assert result.get("batch_issue_number") is None

    # --- Criterion 5: Regression test exists ---

    def test_spec_issue808_5_regression_test_exists(self):
        """AC5: A regression test for Issue #808 MUST exist."""
        assert REGRESSION_TEST_FILE.exists(), (
            f"Regression test not found at {REGRESSION_TEST_FILE}"
        )
        content = REGRESSION_TEST_FILE.read_text()
        assert "808" in content, "Regression test must reference Issue #808"
        assert "class" in content or "def test_" in content, (
            "Regression test must contain test functions"
        )
