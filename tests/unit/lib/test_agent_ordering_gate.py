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
    FIX_PIPELINE_AGENTS,
    FULL_PIPELINE_AGENTS,
    LIGHT_PIPELINE_AGENTS,
    GateResult,
    check_batch_agent_completeness,
    check_minimum_agent_count,
    check_ordering_prerequisites,
    get_required_agents,
)


# ---------------------------------------------------------------------------
# check_ordering_prerequisites — Sequential mode
# ---------------------------------------------------------------------------


class TestSequentialOrdering:
    """Tests for sequential (default) mode ordering."""

    def test_security_auditor_blocked_without_reviewer(self):
        completed = {"implementer", "pytest-gate"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "reviewer" in result.missing_agents

    def test_security_auditor_allowed_with_reviewer(self):
        completed = {"implementer", "pytest-gate", "reviewer"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="sequential"
        )
        assert result.passed

    def test_reviewer_allowed_without_security_auditor(self):
        completed = {"implementer", "pytest-gate"}
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

    def test_implementer_allowed_with_planner_plan_critic_and_test_master(self):
        completed = {"planner", "plan-critic", "test-master"}
        result = check_ordering_prerequisites(
            "implementer", completed, validation_mode="sequential"
        )
        assert result.passed

    def test_reviewer_blocked_without_implementer(self):
        completed = {"planner", "pytest-gate"}
        result = check_ordering_prerequisites(
            "reviewer", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "implementer" in result.missing_agents

    def test_security_auditor_blocked_without_implementer(self):
        completed = {"planner", "pytest-gate", "reviewer"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "implementer" in result.missing_agents

    def test_doc_master_blocked_without_implementer(self):
        completed = {"planner", "pytest-gate"}
        result = check_ordering_prerequisites(
            "doc-master", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "implementer" in result.missing_agents

    def test_doc_master_allowed_with_implementer(self):
        completed = {"planner", "implementer", "pytest-gate"}
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

    def test_test_master_passes_without_planner(self):
        """test-master has no core prerequisites — TDD-first pairs are only
        enforced after test-master has completed (Issue #636)."""
        completed = set()
        result = check_ordering_prerequisites(
            "test-master", completed, validation_mode="sequential"
        )
        # test-master is not in STEP_ORDER (no core prerequisites defined),
        # so it passes as an unknown agent
        assert result.passed

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
    """Tests for parallel mode — Issue #838: reviewer->security-auditor always enforced."""

    def test_security_auditor_blocked_without_reviewer_in_parallel(self):
        """Issue #838: reviewer->security-auditor is now always enforced, even in parallel."""
        completed = {"implementer", "pytest-gate"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="parallel"
        )
        assert not result.passed
        assert "reviewer" in result.missing_agents

    def test_security_auditor_allowed_with_all_prereqs_parallel(self):
        """Security-auditor passes in parallel mode when all prereqs met."""
        completed = {"implementer", "pytest-gate", "reviewer"}
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
        completed = {"planner", "pytest-gate"}
        result = check_ordering_prerequisites(
            "reviewer", completed, validation_mode="parallel"
        )
        assert not result.passed

    def test_doc_master_still_requires_implementer_in_parallel(self):
        completed = {"planner", "pytest-gate"}
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
        completed = {"implementer", "pytest-gate"}
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
        completed = {"planner", "implementer", "pytest-gate", "doc-master", "continuous-improvement-analyst"}
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

    def test_light_mode_core_agents_subset_of_full(self):
        """Light mode core agents (excluding CIA) should be a subset of full pipeline agents.

        CIA is included in light and fix pipeline completeness checks but not in
        FULL_PIPELINE_AGENTS because it runs as a background agent in full mode
        and is not part of the synchronous completeness gate there.
        """
        light_without_cia = LIGHT_PIPELINE_AGENTS - {"continuous-improvement-analyst"}
        assert light_without_cia.issubset(FULL_PIPELINE_AGENTS)


# ---------------------------------------------------------------------------
# get_required_agents
# ---------------------------------------------------------------------------


class TestGetRequiredAgents:
    """Tests for get_required_agents() — mode-aware agent set resolution."""

    def test_fix_mode_returns_fix_agents(self):
        result = get_required_agents("fix")
        assert result == {"implementer", "pytest-gate", "reviewer", "doc-master", "continuous-improvement-analyst"}

    def test_light_mode_returns_light_agents(self):
        result = get_required_agents("light")
        assert result == {"planner", "implementer", "pytest-gate", "doc-master", "continuous-improvement-analyst"}

    def test_full_mode_returns_full_pipeline_agents(self):
        result = get_required_agents("full")
        assert result == FULL_PIPELINE_AGENTS

    def test_full_mode_with_research_skipped(self):
        result = get_required_agents("full", research_skipped=True)
        assert "researcher-local" not in result
        assert "researcher" not in result
        assert len(result) == len(FULL_PIPELINE_AGENTS) - 2
        assert "pytest-gate" in result

    def test_tdd_first_mode_returns_full_plus_test_master(self):
        result = get_required_agents("tdd-first")
        assert result == FULL_PIPELINE_AGENTS | {"test-master"}
        assert len(result) == len(FULL_PIPELINE_AGENTS) + 1

    def test_research_skipped_only_affects_full_mode(self):
        """research_skipped should have no effect on non-full modes."""
        fix_normal = get_required_agents("fix")
        fix_skipped = get_required_agents("fix", research_skipped=True)
        assert fix_normal == fix_skipped

        light_normal = get_required_agents("light")
        light_skipped = get_required_agents("light", research_skipped=True)
        assert light_normal == light_skipped

    def test_returns_copy_not_reference_full(self):
        """Must return a copy so callers can mutate without affecting constants."""
        result = get_required_agents("full")
        result.add("fake-agent")
        assert "fake-agent" not in FULL_PIPELINE_AGENTS

    def test_returns_copy_not_reference_fix(self):
        result = get_required_agents("fix")
        result.add("fake-agent")
        assert "fake-agent" not in FIX_PIPELINE_AGENTS

    def test_returns_copy_not_reference_light(self):
        result = get_required_agents("light")
        result.add("fake-agent")
        assert "fake-agent" not in LIGHT_PIPELINE_AGENTS

    def test_default_mode_is_full(self):
        result = get_required_agents()
        assert result == FULL_PIPELINE_AGENTS

    def test_full_with_research_skipped_has_7_agents(self):
        """Issue #878: plan-critic added, so 7 agents with research skipped."""
        result = get_required_agents("full", research_skipped=True)
        assert len(result) == 7
        assert result == {"planner", "plan-critic", "implementer", "pytest-gate", "reviewer", "security-auditor", "doc-master"}


# ---------------------------------------------------------------------------
# check_batch_agent_completeness — Fix mode
# ---------------------------------------------------------------------------


class TestBatchCompletenessFixMode:
    """Tests for check_batch_agent_completeness with fix and other modes."""

    def test_fix_mode_with_all_5_agents_passes(self):
        completed = {"implementer", "pytest-gate", "reviewer", "doc-master", "continuous-improvement-analyst"}
        result = check_batch_agent_completeness(completed, issue_number=100, mode="fix")
        assert result.passed

    def test_fix_mode_missing_reviewer_fails(self):
        completed = {"implementer", "doc-master"}
        result = check_batch_agent_completeness(completed, issue_number=100, mode="fix")
        assert not result.passed
        assert "reviewer" in result.missing_agents

    def test_fix_mode_missing_implementer_fails(self):
        completed = {"reviewer", "doc-master"}
        result = check_batch_agent_completeness(completed, issue_number=100, mode="fix")
        assert not result.passed
        assert "implementer" in result.missing_agents

    def test_light_mode_with_all_5_agents_passes(self):
        completed = {"planner", "implementer", "pytest-gate", "doc-master", "continuous-improvement-analyst"}
        result = check_batch_agent_completeness(completed, issue_number=10, mode="light")
        assert result.passed

    def test_full_mode_with_research_skipped_and_5_agents_passes(self):
        """Full mode with all 7 agents (including researchers) passes."""
        completed = FULL_PIPELINE_AGENTS.copy()
        result = check_batch_agent_completeness(completed, issue_number=50)
        assert result.passed

    def test_fix_mode_issue_number_in_reason(self):
        result = check_batch_agent_completeness(set(), issue_number=42, mode="fix")
        assert "#42" in result.reason


# ---------------------------------------------------------------------------
# CIA agent definition — mode-aware requirements
# ---------------------------------------------------------------------------


class TestCIAAgentDefinition:
    """Verify the CIA agent markdown documents mode-aware agent requirements."""

    CIA_PATH = (
        Path(__file__).resolve().parents[3]
        / "plugins"
        / "autonomous-dev"
        / "agents"
        / "continuous-improvement-analyst.md"
    )

    def test_cia_contains_fix_mode_entry(self):
        """CIA agent must document --fix mode agent requirements."""
        content = self.CIA_PATH.read_text()
        assert "--fix" in content

    def test_cia_contains_light_mode_entry(self):
        """CIA agent must document --light mode agent requirements."""
        content = self.CIA_PATH.read_text()
        assert "--light" in content

    def test_cia_contains_self_reference(self):
        """CIA agent must reference continuous-improvement-analyst in mode requirements."""
        content = self.CIA_PATH.read_text()
        assert "continuous-improvement-analyst" in content


# ---------------------------------------------------------------------------
# Issue #669: security-auditor ordering recurrence regression tests
# ---------------------------------------------------------------------------


class TestIssue669SecurityAuditorOrdering:
    """Regression tests for Issue #669: security-auditor ordering violation recurrence.

    The bug: In batch sessions, security-auditor ran before reviewer completed.
    This violated the pipeline spec (reviewer must complete before security-auditor).

    Root cause: hooks failing to load in worktrees (#651) + fail-open exception handler.
    Fix: defensive parallel-mode check + warning logging.
    """

    def test_sequential_mode_blocks_security_auditor_without_reviewer(self):
        """Core regression: security-auditor MUST be blocked without reviewer in sequential mode."""
        completed = {"planner", "implementer", "pytest-gate"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "reviewer" in result.missing_agents

    def test_sequential_mode_allows_security_auditor_with_reviewer(self):
        """security-auditor allowed when reviewer has completed."""
        completed = {"planner", "implementer", "pytest-gate", "reviewer"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="sequential"
        )
        assert result.passed

    def test_parallel_mode_blocks_when_reviewer_not_completed(self):
        """Issue #838: reviewer->security-auditor is now always enforced.
        Parallel mode no longer relaxes this — reviewer must complete."""
        completed = {"planner", "implementer", "pytest-gate"}
        launched = {"planner", "implementer", "pytest-gate", "reviewer"}
        result = check_ordering_prerequisites(
            "security-auditor",
            completed,
            validation_mode="parallel",
            launched_agents=launched,
        )
        assert not result.passed
        assert "reviewer" in result.missing_agents

    def test_parallel_mode_allows_when_reviewer_completed(self):
        """Parallel mode allows security-auditor when reviewer has completed."""
        completed = {"planner", "implementer", "pytest-gate", "reviewer"}
        launched = {"planner", "implementer", "pytest-gate", "reviewer"}
        result = check_ordering_prerequisites(
            "security-auditor",
            completed,
            validation_mode="parallel",
            launched_agents=launched,
        )
        assert result.passed

    def test_parallel_mode_no_warning_when_reviewer_completed(self):
        """No warning when reviewer has completed in parallel mode."""
        completed = {"planner", "implementer", "pytest-gate", "reviewer"}
        launched = {"planner", "implementer", "pytest-gate", "reviewer"}
        result = check_ordering_prerequisites(
            "security-auditor",
            completed,
            validation_mode="parallel",
            launched_agents=launched,
        )
        assert result.passed
        assert result.warning is None

    def test_batch_context_sequential_enforcement(self):
        """Simulates batch context: PIPELINE_ISSUE_NUMBER set, sequential mode.
        security-auditor should still be blocked without reviewer."""
        completed_for_issue = {"planner", "implementer", "pytest-gate"}
        result = check_ordering_prerequisites(
            "security-auditor",
            completed_for_issue,
            validation_mode="sequential",
        )
        assert not result.passed
        assert "reviewer" in result.missing_agents

    def test_default_mode_is_sequential_blocks_security_auditor(self):
        """Default validation_mode must be 'sequential', which blocks
        security-auditor without reviewer. Issue #669."""
        completed = {"planner", "implementer", "pytest-gate"}
        result = check_ordering_prerequisites("security-auditor", completed)
        assert not result.passed
        assert "reviewer" in result.missing_agents

    def test_gate_result_has_warning_field(self):
        """GateResult dataclass includes optional warning field (Issue #669)."""
        r = GateResult(passed=True, reason="ok")
        assert r.warning is None
        r2 = GateResult(passed=True, reason="ok", warning="test warning")
        assert r2.warning == "test warning"


# ---------------------------------------------------------------------------
# Issue #697 — pipeline_mode filtering of prerequisites
# ---------------------------------------------------------------------------


class TestPipelineModeFiltering:
    """Tests that ordering prerequisites respect pipeline_mode.

    In --fix mode, planner is not part of the pipeline, so the
    planner→implementer prerequisite must be skipped. Issue #697.
    """

    def test_fix_mode_implementer_not_blocked_by_planner(self):
        """In --fix mode, implementer should NOT require planner (planner never runs)."""
        completed = set()
        result = check_ordering_prerequisites(
            "implementer", completed, pipeline_mode="fix"
        )
        assert result.passed, f"Implementer should pass in fix mode but got: {result.reason}"

    def test_fix_mode_reviewer_still_blocked_by_implementer(self):
        """In --fix mode, reviewer should still require implementer."""
        completed = {"pytest-gate"}
        result = check_ordering_prerequisites(
            "reviewer", completed, pipeline_mode="fix"
        )
        assert not result.passed
        assert "implementer" in result.missing_agents

    def test_fix_mode_reviewer_allowed_with_implementer(self):
        """In --fix mode, reviewer passes when implementer and pytest-gate are done."""
        completed = {"implementer", "pytest-gate"}
        result = check_ordering_prerequisites(
            "reviewer", completed, pipeline_mode="fix"
        )
        assert result.passed

    def test_full_mode_implementer_still_blocked_by_planner(self):
        """In full mode, the original planner→implementer constraint is preserved."""
        completed = set()
        result = check_ordering_prerequisites(
            "implementer", completed, pipeline_mode="full"
        )
        assert not result.passed
        assert "planner" in result.missing_agents

    def test_light_mode_implementer_blocked_by_planner(self):
        """In --light mode, planner IS part of the pipeline, so constraint is enforced."""
        completed = set()
        result = check_ordering_prerequisites(
            "implementer", completed, pipeline_mode="light"
        )
        assert not result.passed
        assert "planner" in result.missing_agents

    def test_light_mode_implementer_allowed_with_planner(self):
        """In --light mode, implementer passes when planner is done."""
        completed = {"planner"}
        result = check_ordering_prerequisites(
            "implementer", completed, pipeline_mode="light"
        )
        assert result.passed

    def test_default_pipeline_mode_is_full(self):
        """Default pipeline_mode should be 'full', preserving backward compatibility."""
        completed = set()
        result = check_ordering_prerequisites("implementer", completed)
        assert not result.passed
        assert "planner" in result.missing_agents

    def test_fix_mode_doc_master_blocked_by_implementer(self):
        """In --fix mode, doc-master still requires implementer."""
        completed = {"pytest-gate"}
        result = check_ordering_prerequisites(
            "doc-master", completed, pipeline_mode="fix"
        )
        assert not result.passed
        assert "implementer" in result.missing_agents


# ---------------------------------------------------------------------------
# Issue #751 — CIA missing from fix and light pipeline final issue group
# ---------------------------------------------------------------------------


class TestCIAInFixAndLightPipelines:
    """Regression tests for Issue #751: CIA missing from fix/light pipeline completeness.

    The bug: --fix and --light batch runs passed completeness checks without
    continuous-improvement-analyst completing, because CIA was not in
    FIX_PIPELINE_AGENTS or LIGHT_PIPELINE_AGENTS.

    Fix: Add "continuous-improvement-analyst" to both sets.
    """

    def test_fix_pipeline_agents_includes_cia(self):
        """FIX_PIPELINE_AGENTS must include continuous-improvement-analyst. Issue #751."""
        assert "continuous-improvement-analyst" in FIX_PIPELINE_AGENTS

    def test_light_pipeline_agents_includes_cia(self):
        """LIGHT_PIPELINE_AGENTS must include continuous-improvement-analyst. Issue #751."""
        assert "continuous-improvement-analyst" in LIGHT_PIPELINE_AGENTS

    def test_fix_mode_missing_cia_fails(self):
        """Completeness check fails when CIA is absent in fix mode.

        This is the core regression: before the fix, 3 agents were sufficient
        to pass the completeness gate. After the fix, CIA is required.
        """
        completed = {"implementer", "pytest-gate", "reviewer", "doc-master"}  # CIA missing
        result = check_batch_agent_completeness(completed, issue_number=751, mode="fix")
        assert not result.passed
        assert "continuous-improvement-analyst" in result.missing_agents

    def test_light_mode_missing_cia_fails(self):
        """Completeness check fails when CIA is absent in light mode.

        Before the fix, 3 agents (planner, implementer, doc-master) were enough.
        After the fix, CIA is also required.
        """
        completed = {"planner", "implementer", "pytest-gate", "doc-master"}  # CIA missing
        result = check_batch_agent_completeness(completed, issue_number=751, mode="light")
        assert not result.passed
        assert "continuous-improvement-analyst" in result.missing_agents

    def test_get_required_agents_fix_includes_cia(self):
        """get_required_agents('fix') must return 5 agents including CIA and pytest-gate."""
        result = get_required_agents("fix")
        assert "continuous-improvement-analyst" in result
        assert "pytest-gate" in result
        assert len(result) == 5

    def test_get_required_agents_light_includes_cia(self):
        """get_required_agents('light') must return 5 agents including CIA and pytest-gate."""
        result = get_required_agents("light")
        assert "continuous-improvement-analyst" in result
        assert "pytest-gate" in result
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Issue #878 — plan-critic ordering enforcement
# ---------------------------------------------------------------------------


class TestPlanCriticOrdering:
    """Tests for plan-critic in the ordering gate. Issue #878."""

    def test_plan_critic_in_full_pipeline_agents(self):
        """FULL_PIPELINE_AGENTS must include plan-critic."""
        assert "plan-critic" in FULL_PIPELINE_AGENTS

    def test_plan_critic_not_in_fix_pipeline_agents(self):
        """FIX_PIPELINE_AGENTS must NOT include plan-critic (fix mode skips planning)."""
        assert "plan-critic" not in FIX_PIPELINE_AGENTS

    def test_plan_critic_not_in_light_pipeline_agents(self):
        """LIGHT_PIPELINE_AGENTS must NOT include plan-critic."""
        assert "plan-critic" not in LIGHT_PIPELINE_AGENTS

    def test_implementer_blocked_without_plan_critic_in_full_mode(self):
        """In full mode, implementer requires plan-critic to complete first."""
        completed = {"planner"}  # plan-critic missing
        result = check_ordering_prerequisites(
            "implementer", completed, pipeline_mode="full"
        )
        assert not result.passed
        assert "plan-critic" in result.missing_agents

    def test_implementer_allowed_with_planner_and_plan_critic(self):
        """In full mode, implementer passes when both planner and plan-critic completed."""
        completed = {"planner", "plan-critic"}
        result = check_ordering_prerequisites(
            "implementer", completed, pipeline_mode="full"
        )
        assert result.passed

    def test_plan_critic_blocked_without_planner(self):
        """plan-critic requires planner to complete first."""
        completed = set()
        result = check_ordering_prerequisites(
            "plan-critic", completed, pipeline_mode="full"
        )
        assert not result.passed
        assert "planner" in result.missing_agents

    def test_plan_critic_allowed_with_planner(self):
        """plan-critic passes when planner has completed."""
        completed = {"planner"}
        result = check_ordering_prerequisites(
            "plan-critic", completed, pipeline_mode="full"
        )
        assert result.passed

    def test_fix_mode_implementer_not_blocked_by_plan_critic(self):
        """In fix mode, plan-critic is not part of the pipeline, so not enforced."""
        completed = set()
        result = check_ordering_prerequisites(
            "implementer", completed, pipeline_mode="fix"
        )
        # In fix mode, neither planner nor plan-critic are required
        assert result.passed

    def test_get_required_agents_full_includes_plan_critic(self):
        """get_required_agents('full') must include plan-critic."""
        result = get_required_agents("full")
        assert "plan-critic" in result

    def test_get_required_agents_full_plan_critic_skipped(self):
        """get_required_agents('full', plan_critic_skipped=True) excludes plan-critic."""
        result = get_required_agents("full", plan_critic_skipped=True)
        assert "plan-critic" not in result

    def test_plan_critic_skipped_only_affects_full_mode(self):
        """plan_critic_skipped should have no effect on non-full modes."""
        fix_normal = get_required_agents("fix")
        fix_skipped = get_required_agents("fix", plan_critic_skipped=True)
        assert fix_normal == fix_skipped

        light_normal = get_required_agents("light")
        light_skipped = get_required_agents("light", plan_critic_skipped=True)
        assert light_normal == light_skipped

    def test_full_with_both_skips(self):
        """Full mode with both research and plan-critic skipped."""
        result = get_required_agents("full", research_skipped=True, plan_critic_skipped=True)
        assert "researcher-local" not in result
        assert "researcher" not in result
        assert "plan-critic" not in result
        assert "planner" in result
        assert "implementer" in result
        assert len(result) == 6  # 9 full - 2 researchers - 1 plan-critic

    def test_ordering_gate_respects_plan_critic_skipped(self):
        """check_ordering_prerequisites must respect plan_critic_skipped parameter.

        Without the fix (Issue #878 BLOCKING FINDING 1), check_ordering_prerequisites
        called get_required_agents without plan_critic_skipped, so plan-critic was
        always required even when the bypass was active.
        """
        # With plan_critic_skipped=True, implementer should pass with only planner
        result = check_ordering_prerequisites(
            "implementer",
            {"planner"},
            pipeline_mode="full",
            plan_critic_skipped=True,
        )
        assert result.passed, f"Should pass with plan_critic_skipped=True: {result.reason}"

    def test_ordering_gate_blocks_without_plan_critic_skipped(self):
        """Without plan_critic_skipped, implementer requires plan-critic."""
        result = check_ordering_prerequisites(
            "implementer",
            {"planner"},
            pipeline_mode="full",
            plan_critic_skipped=False,
        )
        assert not result.passed
        assert "plan-critic" in result.missing_agents
