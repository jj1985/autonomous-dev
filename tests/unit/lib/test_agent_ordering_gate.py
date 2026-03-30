"""
Tests for agent_ordering_gate.py — pure logic for pipeline ordering decisions.

Issues: #625, #629, #632
"""

import sys
from pathlib import Path

import pytest

# Add lib to path
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from agent_ordering_gate import (
    FULL_PIPELINE_AGENTS,
    LIGHT_PIPELINE_AGENTS,
    GateResult,
    check_batch_agent_completeness,
    check_minimum_agent_count,
    check_ordering_prerequisites,
)


# ---------------------------------------------------------------------------
# check_ordering_prerequisites — Sequential mode
# ---------------------------------------------------------------------------


class TestSequentialOrdering:
    """Tests for sequential (default) mode ordering."""

    def test_security_auditor_blocked_without_reviewer(self):
        completed = {"implementer"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "reviewer" in result.missing_agents

    def test_security_auditor_allowed_with_reviewer(self):
        completed = {"implementer", "reviewer"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="sequential"
        )
        assert result.passed

    def test_reviewer_allowed_without_security_auditor(self):
        completed = {"implementer"}
        result = check_ordering_prerequisites(
            "reviewer", completed, validation_mode="sequential"
        )
        assert result.passed

    def test_implementer_blocked_without_planner(self):
        completed = set()
        result = check_ordering_prerequisites(
            "implementer", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "planner" in result.missing_agents

    def test_implementer_allowed_with_planner_and_test_master(self):
        completed = {"planner", "test-master"}
        result = check_ordering_prerequisites(
            "implementer", completed, validation_mode="sequential"
        )
        assert result.passed

    def test_reviewer_blocked_without_implementer(self):
        completed = {"planner"}
        result = check_ordering_prerequisites(
            "reviewer", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "implementer" in result.missing_agents

    def test_security_auditor_blocked_without_implementer(self):
        completed = {"planner", "reviewer"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "implementer" in result.missing_agents

    def test_doc_master_blocked_without_implementer(self):
        completed = {"planner"}
        result = check_ordering_prerequisites(
            "doc-master", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "implementer" in result.missing_agents

    def test_doc_master_allowed_with_implementer(self):
        completed = {"planner", "implementer"}
        result = check_ordering_prerequisites(
            "doc-master", completed, validation_mode="sequential"
        )
        assert result.passed

    def test_planner_blocked_without_nothing(self):
        """Planner has no prerequisites (researchers are parallel/optional)."""
        completed = set()
        result = check_ordering_prerequisites(
            "planner", completed, validation_mode="sequential"
        )
        assert result.passed

    def test_researcher_has_no_prerequisites(self):
        completed = set()
        result = check_ordering_prerequisites(
            "researcher", completed, validation_mode="sequential"
        )
        assert result.passed

    def test_test_master_blocked_without_planner(self):
        completed = set()
        result = check_ordering_prerequisites(
            "test-master", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "planner" in result.missing_agents

    def test_empty_completed_blocks_dependents(self):
        for agent in ["implementer", "reviewer", "security-auditor", "doc-master"]:
            result = check_ordering_prerequisites(
                agent, set(), validation_mode="sequential"
            )
            assert not result.passed, f"{agent} should be blocked with empty completed set"


# ---------------------------------------------------------------------------
# check_ordering_prerequisites — Parallel mode
# ---------------------------------------------------------------------------


class TestParallelOrdering:
    """Tests for parallel mode — relaxes reviewer->security-auditor."""

    def test_security_auditor_allowed_without_reviewer(self):
        completed = {"implementer"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="parallel"
        )
        assert result.passed

    def test_implementer_still_blocked_without_planner(self):
        """Core ordering is still enforced in parallel mode."""
        completed = set()
        result = check_ordering_prerequisites(
            "implementer", completed, validation_mode="parallel"
        )
        assert not result.passed
        assert "planner" in result.missing_agents

    def test_reviewer_still_requires_implementer_in_parallel(self):
        completed = {"planner"}
        result = check_ordering_prerequisites(
            "reviewer", completed, validation_mode="parallel"
        )
        assert not result.passed

    def test_doc_master_still_requires_implementer_in_parallel(self):
        completed = {"planner"}
        result = check_ordering_prerequisites(
            "doc-master", completed, validation_mode="parallel"
        )
        assert not result.passed


# ---------------------------------------------------------------------------
# check_ordering_prerequisites — Edge cases
# ---------------------------------------------------------------------------


class TestOrderingEdgeCases:
    """Edge cases for ordering checks."""

    def test_unknown_agent_allowed(self):
        result = check_ordering_prerequisites("unknown-agent", set())
        assert result.passed
        assert "Unknown agent" in result.reason

    def test_whitespace_agent_name_stripped(self):
        result = check_ordering_prerequisites("  researcher  ", set())
        assert result.passed

    def test_case_insensitive_target(self):
        result = check_ordering_prerequisites("IMPLEMENTER", set())
        assert not result.passed

    def test_default_mode_is_sequential(self):
        """Default validation_mode should be sequential."""
        completed = {"implementer"}
        result = check_ordering_prerequisites("security-auditor", completed)
        assert not result.passed  # reviewer missing, sequential enforced

    def test_gate_result_dataclass(self):
        r = GateResult(passed=True, reason="ok")
        assert r.passed
        assert r.reason == "ok"
        assert r.missing_agents == []

    def test_multiple_missing_agents(self):
        """security-auditor with nothing completed misses implementer AND reviewer."""
        result = check_ordering_prerequisites(
            "security-auditor", set(), validation_mode="sequential"
        )
        assert not result.passed
        assert len(result.missing_agents) >= 1  # at least implementer


# ---------------------------------------------------------------------------
# check_minimum_agent_count
# ---------------------------------------------------------------------------


class TestMinimumAgentCount:
    """Tests for minimum agent count checks (git operations)."""

    def test_all_required_present(self):
        required = {"reviewer", "security-auditor"}
        completed = {"reviewer", "security-auditor", "doc-master"}
        result = check_minimum_agent_count(completed, required_agents=required)
        assert result.passed

    def test_missing_required_agents(self):
        required = {"reviewer", "security-auditor"}
        completed = {"reviewer"}
        result = check_minimum_agent_count(completed, required_agents=required)
        assert not result.passed
        assert "security-auditor" in result.missing_agents

    def test_empty_completed_fails(self):
        required = {"reviewer"}
        result = check_minimum_agent_count(set(), required_agents=required)
        assert not result.passed

    def test_empty_required_passes(self):
        result = check_minimum_agent_count(set(), required_agents=set())
        assert result.passed


# ---------------------------------------------------------------------------
# check_batch_agent_completeness
# ---------------------------------------------------------------------------


class TestBatchCompleteness:
    """Tests for batch agent completeness checks."""

    def test_full_pipeline_all_agents(self):
        result = check_batch_agent_completeness(
            FULL_PIPELINE_AGENTS, issue_number=42
        )
        assert result.passed

    def test_full_pipeline_missing_agents(self):
        completed = {"planner", "implementer"}
        result = check_batch_agent_completeness(completed, issue_number=42)
        assert not result.passed
        assert len(result.missing_agents) > 0

    def test_light_mode_requires_fewer(self):
        completed = {"planner", "implementer", "doc-master"}
        result = check_batch_agent_completeness(
            completed, issue_number=10, mode="light"
        )
        assert result.passed

    def test_light_mode_missing_implementer(self):
        completed = {"planner", "doc-master"}
        result = check_batch_agent_completeness(
            completed, issue_number=10, mode="light"
        )
        assert not result.passed
        assert "implementer" in result.missing_agents

    def test_issue_number_in_reason(self):
        result = check_batch_agent_completeness(set(), issue_number=99)
        assert "#99" in result.reason

    def test_light_mode_agents_subset_of_full(self):
        """Light mode agents should be a subset of full pipeline agents."""
        assert LIGHT_PIPELINE_AGENTS.issubset(FULL_PIPELINE_AGENTS)
