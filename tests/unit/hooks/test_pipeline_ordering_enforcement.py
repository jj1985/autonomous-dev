"""
Integration-style tests for pipeline ordering enforcement (Layer 4) in unified_pre_tool.py.

Tests mock the hook flow to verify that Agent tool calls during active pipeline
sessions are subject to ordering checks.

Issues: #625, #629, #632, #636
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add hook and lib dirs to path
HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(HOOK_DIR))
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook
from agent_ordering_gate import GateResult


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Reset relevant env vars for each test."""
    env_keys = [
        "PRE_TOOL_PIPELINE_ORDERING", "SANDBOX_ENABLED",
        "PRE_TOOL_MCP_SECURITY", "PRE_TOOL_AGENT_AUTH",
        "PRE_TOOL_BATCH_PERMISSION", "ENFORCEMENT_LEVEL",
        "CLAUDE_AGENT_NAME", "PIPELINE_STATE_FILE",
        "PIPELINE_ISSUE_NUMBER",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)


class TestPipelineOrderingGate:
    """Tests for the validate_pipeline_ordering function."""

    def test_non_agent_tool_skips_ordering(self):
        """Non-Agent tools should not trigger ordering checks."""
        decision, reason = hook.validate_pipeline_ordering("Bash", {"command": "ls"})
        assert decision == "allow"

    def test_agent_tool_during_no_pipeline_skips(self):
        """Agent tool when pipeline is NOT active should skip."""
        with patch.object(hook, "_is_pipeline_active", return_value=False):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"task_description": "run reviewer"}
            )
            assert decision == "allow"

    def test_ordering_disabled_via_env(self, monkeypatch):
        """PRE_TOOL_PIPELINE_ORDERING=false disables ordering checks."""
        monkeypatch.setenv("PRE_TOOL_PIPELINE_ORDERING", "false")
        decision, reason = hook.validate_pipeline_ordering(
            "Agent", {"task_description": "run reviewer"}
        )
        assert decision == "allow"

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_sequential_violation_returns_deny(
        self, mock_mode, mock_completed, monkeypatch
    ):
        """Ordering violation in active pipeline should deny."""
        mock_completed.return_value = {"implementer"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"task_description": "Run the security-auditor agent"}
            )
            assert decision == "deny"
            assert "ORDERING" in reason.upper()

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_parallel_mode_allows_simultaneous_validators(
        self, mock_mode, mock_completed, monkeypatch
    ):
        """In parallel mode, security-auditor should pass without reviewer."""
        mock_completed.return_value = {"planner", "implementer"}
        mock_mode.return_value = "parallel"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"task_description": "Run the security-auditor agent"}
            )
            assert decision == "allow"

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_prerequisites_met_allows(
        self, mock_mode, mock_completed, monkeypatch
    ):
        """When all prerequisites met, should allow."""
        mock_completed.return_value = {"planner", "test-master", "implementer", "reviewer"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"task_description": "Run the security-auditor agent"}
            )
            assert decision == "allow"

    def test_ordering_error_defaults_to_allow(self, monkeypatch):
        """Errors in ordering check should fail-open."""
        with patch.object(hook, "_is_pipeline_active", side_effect=RuntimeError("boom")):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"task_description": "run reviewer"}
            )
            assert decision == "allow"
            assert "error" in reason.lower()

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_unknown_agent_in_task_allowed(
        self, mock_mode, mock_completed, monkeypatch
    ):
        """Unknown agent names should pass through."""
        mock_completed.return_value = set()
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"task_description": "Run the custom-analysis agent"}
            )
            assert decision == "allow"

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_implementer_blocked_without_planner(
        self, mock_mode, mock_completed, monkeypatch
    ):
        """Implementer should be blocked if planner has not completed."""
        mock_completed.return_value = {"researcher"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"task_description": "Run the implementer agent"}
            )
            assert decision == "deny"

    def test_task_tool_also_checked(self):
        """Legacy 'Task' tool name should also trigger ordering checks."""
        with patch.object(hook, "_is_pipeline_active", return_value=False):
            decision, reason = hook.validate_pipeline_ordering(
                "Task", {"task_description": "run reviewer"}
            )
            assert decision == "allow"

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_doc_master_allowed_parallel_with_reviewer(
        self, mock_mode, mock_completed, monkeypatch
    ):
        """doc-master has no reviewer prerequisite, only implementer."""
        mock_completed.return_value = {"planner", "implementer"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"task_description": "Run the doc-master agent"}
            )
            assert decision == "allow"


class TestSubagentTypePriority:
    """Regression tests for subagent_type field taking priority over prompt text extraction.

    Issue #636: When a planner's prompt contained "implementer" in research context,
    _extract_subagent_type matched the wrong agent, causing false ORDERING VIOLATION.
    Fix: check tool_input["subagent_type"] before falling back to text extraction.
    """

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_subagent_type_overrides_prompt_text(
        self, mock_mode, mock_completed
    ):
        """subagent_type='planner' should be used even when prompt mentions 'implementer'."""
        mock_completed.return_value = {"researcher", "researcher-local"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {
                    "subagent_type": "planner",
                    "prompt": "Plan the implementation. The implementer agent will handle code changes.",
                }
            )
            assert decision == "allow"
            assert "planner" in reason.lower()

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_subagent_type_prevents_false_ordering_violation(
        self, mock_mode, mock_completed
    ):
        """Without subagent_type fix, this would match 'implementer' and deny."""
        mock_completed.return_value = set()  # No agents completed yet
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            # planner has no prerequisites — should allow
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {
                    "subagent_type": "planner",
                    "prompt": "Research found that implementer needs test-master first.",
                }
            )
            assert decision == "allow"

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_falls_back_to_text_extraction_without_subagent_type(
        self, mock_mode, mock_completed
    ):
        """When subagent_type is missing, text extraction should still work."""
        mock_completed.return_value = {"planner", "test-master"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {
                    "prompt": "Run the implementer agent to write code",
                }
            )
            assert decision == "allow"
            assert "implementer" in reason.lower()

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_empty_subagent_type_falls_back_to_text(
        self, mock_mode, mock_completed
    ):
        """Empty string subagent_type should fall back to text extraction."""
        mock_completed.return_value = {"planner", "test-master"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {
                    "subagent_type": "",
                    "prompt": "Run the implementer agent",
                }
            )
            assert decision == "allow"
            assert "implementer" in reason.lower()

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_subagent_type_with_multiple_agents_in_prompt(
        self, mock_mode, mock_completed
    ):
        """subagent_type should resolve correctly even with many agent names in prompt."""
        mock_completed.return_value = {"researcher"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {
                    "subagent_type": "planner",
                    "prompt": (
                        "Plan implementation. researcher-local found patterns. "
                        "implementer will write code. test-master handles tests. "
                        "reviewer validates. doc-master updates docs."
                    ),
                }
            )
            assert decision == "allow"
            assert "planner" in reason.lower()


class TestTddFirstModeDependentPairs:
    """Regression tests for test-master prerequisites being mode-dependent.

    Issue #636: test-master -> implementer was unconditionally enforced as a core
    prerequisite, but test-master only runs in --tdd-first mode. In acceptance-first
    mode (the default), this blocked implementer from ever running.

    Fix: test-master pairs are only enforced when test-master has completed
    (indicating TDD-first mode is active).
    """

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_implementer_allowed_without_test_master_acceptance_first(
        self, mock_mode, mock_completed
    ):
        """In acceptance-first mode, implementer should not require test-master."""
        mock_completed.return_value = {"researcher", "planner"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True),              patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"subagent_type": "implementer", "prompt": "Implement changes"}
            )
            assert decision == "allow"

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_implementer_allowed_in_tdd_first_when_test_master_done(
        self, mock_mode, mock_completed
    ):
        """In TDD-first mode, implementer should pass when test-master completed."""
        mock_completed.return_value = {"researcher", "planner", "test-master"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True),              patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"subagent_type": "implementer", "prompt": "Implement changes"}
            )
            assert decision == "allow"

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_implementer_still_requires_planner(
        self, mock_mode, mock_completed
    ):
        """Planner is still a core prerequisite for implementer in all modes."""
        mock_completed.return_value = {"researcher"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True),              patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"subagent_type": "implementer", "prompt": "Implement changes"}
            )
            assert decision == "deny"
            assert "planner" in reason.lower()
