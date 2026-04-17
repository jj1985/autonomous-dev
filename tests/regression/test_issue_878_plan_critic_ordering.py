"""
Regression tests for Issue #878: plan-critic ordering gate enforcement.

The bug: plan-critic was not enforced as a prerequisite for implementer,
allowing the implementer to run without plan validation in full mode.

Fix: Add plan-critic to SEQUENTIAL_REQUIRED, STEP_ORDER, and
FULL_PIPELINE_AGENTS with a conditional bypass for pre-validated plans.
"""

import sys
from pathlib import Path

import pytest

# Add lib to path — tests/regression/ -> parents[2] -> repo root
LIB_DIR = Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from agent_ordering_gate import (
    FULL_PIPELINE_AGENTS,
    FIX_PIPELINE_AGENTS,
    LIGHT_PIPELINE_AGENTS,
    check_batch_agent_completeness,
    check_ordering_prerequisites,
    get_required_agents,
)
from pipeline_intent_validator import SEQUENTIAL_REQUIRED, STEP_ORDER


class TestIssue878PlanCriticOrdering:
    """Regression tests for plan-critic ordering enforcement."""

    def test_step_order_has_plan_critic(self):
        """STEP_ORDER must include plan-critic at step 3.5."""
        assert "plan-critic" in STEP_ORDER
        assert STEP_ORDER["plan-critic"] == 3.5

    def test_sequential_required_has_planner_to_plan_critic(self):
        """SEQUENTIAL_REQUIRED must contain (planner, plan-critic)."""
        assert ("planner", "plan-critic") in SEQUENTIAL_REQUIRED

    def test_sequential_required_has_plan_critic_to_implementer(self):
        """SEQUENTIAL_REQUIRED must contain (plan-critic, implementer)."""
        assert ("plan-critic", "implementer") in SEQUENTIAL_REQUIRED

    def test_full_pipeline_includes_plan_critic(self):
        """FULL_PIPELINE_AGENTS must include plan-critic."""
        assert "plan-critic" in FULL_PIPELINE_AGENTS

    def test_fix_pipeline_excludes_plan_critic(self):
        """FIX_PIPELINE_AGENTS must NOT include plan-critic."""
        assert "plan-critic" not in FIX_PIPELINE_AGENTS

    def test_light_pipeline_excludes_plan_critic(self):
        """LIGHT_PIPELINE_AGENTS must NOT include plan-critic."""
        assert "plan-critic" not in LIGHT_PIPELINE_AGENTS

    def test_implementer_blocked_without_plan_critic_full_mode(self):
        """Core regression: implementer MUST be blocked without plan-critic in full mode."""
        completed = {"planner"}  # plan-critic missing
        result = check_ordering_prerequisites(
            "implementer", completed, pipeline_mode="full"
        )
        assert not result.passed
        assert "plan-critic" in result.missing_agents

    def test_implementer_not_blocked_in_fix_mode(self):
        """Implementer is NOT blocked by plan-critic absence in fix mode."""
        completed = set()
        result = check_ordering_prerequisites(
            "implementer", completed, pipeline_mode="fix"
        )
        assert result.passed

    def test_plan_critic_skipped_bypass(self):
        """Completeness gate respects plan_critic_skipped flag."""
        required_with = get_required_agents("full", plan_critic_skipped=False)
        required_without = get_required_agents("full", plan_critic_skipped=True)
        assert "plan-critic" in required_with
        assert "plan-critic" not in required_without

    def test_ordering_gate_bypass_with_plan_critic_skipped(self):
        """Ordering gate must pass for implementer when plan_critic_skipped=True.

        This is the core regression for BLOCKING FINDING 1: the ordering gate
        (check_ordering_prerequisites) must respect plan_critic_skipped, not just
        the completeness gate. Without the fix, implementer would be blocked even
        when plan_critic_skipped=True because get_required_agents was called
        without the flag.
        """
        completed = {"planner"}  # plan-critic NOT completed
        result = check_ordering_prerequisites(
            "implementer",
            completed,
            pipeline_mode="full",
            plan_critic_skipped=True,
        )
        assert result.passed, (
            f"Implementer should pass with plan_critic_skipped=True, "
            f"got: {result.reason}"
        )

    def test_ordering_gate_still_blocks_without_bypass(self):
        """Ordering gate must still block implementer without plan_critic_skipped."""
        completed = {"planner"}  # plan-critic NOT completed
        result = check_ordering_prerequisites(
            "implementer",
            completed,
            pipeline_mode="full",
            plan_critic_skipped=False,
        )
        assert not result.passed
        assert "plan-critic" in result.missing_agents

    def test_batch_completeness_requires_plan_critic_in_full_mode(self):
        """Batch completeness check in default mode requires plan-critic."""
        completed = FULL_PIPELINE_AGENTS - {"plan-critic"}
        result = check_batch_agent_completeness(completed, issue_number=878)
        assert not result.passed
        assert "plan-critic" in result.missing_agents
