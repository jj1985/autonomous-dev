"""
Tests for prompt integrity enforcement (Layer 5) in unified_pre_tool.py.

Validates that critical agent prompts are blocked when below the minimum
word count during active pipeline sessions.

Issue: #695
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook and lib dirs to path
HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(HOOK_DIR))
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


def _make_prompt(word_count: int) -> str:
    """Generate a prompt with exactly word_count words."""
    return " ".join(f"word{i}" for i in range(word_count))


class TestPromptIntegrityEnforcement:
    """Tests for the validate_prompt_integrity function (Layer 5)."""

    def test_non_agent_tool_allowed(self):
        """Non-Agent tools should bypass prompt integrity checks."""
        decision, reason = hook.validate_prompt_integrity(
            "Bash", {"command": "ls"}
        )
        assert decision == "allow"
        assert "Not an agent invocation" in reason

    def test_non_pipeline_allowed(self):
        """Agent tool outside active pipeline should be allowed."""
        with patch.object(hook, "_is_pipeline_active", return_value=False):
            decision, reason = hook.validate_prompt_integrity(
                "Agent", {"subagent_type": "reviewer", "prompt": "short"}
            )
            assert decision == "allow"
            assert "No active pipeline" in reason

    def test_non_critical_agent_allowed(self):
        """Non-critical agent should be allowed regardless of prompt length."""
        with patch.object(hook, "_is_pipeline_active", return_value=True):
            decision, reason = hook.validate_prompt_integrity(
                "Agent",
                {"subagent_type": "some-other-agent", "prompt": "short prompt"},
            )
            assert decision == "allow"
            assert "not compression-critical" in reason

    def test_critical_agent_below_minimum_blocked(self):
        """Reviewer with 50-word prompt should be blocked during pipeline."""
        short_prompt = _make_prompt(50)
        with patch.object(hook, "_is_pipeline_active", return_value=True):
            decision, reason = hook.validate_prompt_integrity(
                "Agent",
                {"subagent_type": "reviewer", "prompt": short_prompt},
            )
            assert decision == "deny"
            assert "BLOCKED" in reason
            assert "reviewer" in reason
            assert "50 words" in reason

    def test_critical_agent_above_minimum_allowed(self):
        """Reviewer with 100-word prompt should be allowed during pipeline."""
        long_prompt = _make_prompt(100)
        with patch.object(hook, "_is_pipeline_active", return_value=True):
            decision, reason = hook.validate_prompt_integrity(
                "Agent",
                {"subagent_type": "reviewer", "prompt": long_prompt},
            )
            assert decision == "allow"
            assert "Prompt integrity OK" in reason

    def test_security_auditor_below_minimum_blocked(self):
        """Security-auditor with 60-word prompt should be blocked."""
        short_prompt = _make_prompt(60)
        with patch.object(hook, "_is_pipeline_active", return_value=True):
            decision, reason = hook.validate_prompt_integrity(
                "Agent",
                {"subagent_type": "security-auditor", "prompt": short_prompt},
            )
            assert decision == "deny"
            assert "BLOCKED" in reason
            assert "security-auditor" in reason

    def test_implementer_below_minimum_blocked(self):
        """Implementer with 30-word prompt should be blocked."""
        short_prompt = _make_prompt(30)
        with patch.object(hook, "_is_pipeline_active", return_value=True):
            decision, reason = hook.validate_prompt_integrity(
                "Agent",
                {"subagent_type": "implementer", "prompt": short_prompt},
            )
            assert decision == "deny"
            assert "BLOCKED" in reason
            assert "implementer" in reason
            assert "30 words" in reason

    def test_missing_subagent_type_allowed(self):
        """If subagent_type is missing, should allow (fail-open)."""
        with patch.object(hook, "_is_pipeline_active", return_value=True):
            decision, reason = hook.validate_prompt_integrity(
                "Agent", {"prompt": "short prompt"}
            )
            assert decision == "allow"
            assert "Could not determine agent type" in reason

    def test_task_tool_also_checked(self):
        """Task tool (legacy) should also be subject to prompt integrity."""
        short_prompt = _make_prompt(30)
        with patch.object(hook, "_is_pipeline_active", return_value=True):
            decision, reason = hook.validate_prompt_integrity(
                "Task",
                {"subagent_type": "reviewer", "prompt": short_prompt},
            )
            assert decision == "deny"
            assert "BLOCKED" in reason
