"""Spec validation tests for Issue #855: STEP 5.5 plan-critic gate in /implement pipeline.

Validates acceptance criteria:
1. /implement without prior /plan invokes budget plan-critic at STEP 5.5
2. /implement after /plan (with validated plan file) skips plan-critic with log message
3. Structural validation catches plans with 0 file paths or no acceptance criteria
4. FORBIDDEN list prevents skipping plan-critic when no validated plan exists
5. Regression test validates HARD GATE language presence
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_MD = PROJECT_ROOT / "plugins/autonomous-dev/commands/implement.md"


@pytest.fixture(scope="module")
def content() -> str:
    """Read implement.md content."""
    assert IMPLEMENT_MD.exists(), f"implement.md not found at {IMPLEMENT_MD}"
    return IMPLEMENT_MD.read_text()


@pytest.fixture(scope="module")
def step_55_section(content: str) -> str:
    """Extract the full STEP 5.5 section (from its header to the next ### STEP header)."""
    start = content.find("### STEP 5.5")
    assert start != -1, "STEP 5.5 section not found in implement.md"
    # Find next STEP header after 5.5
    next_step = content.find("### STEP 6", start)
    assert next_step != -1, "STEP 6 not found after STEP 5.5"
    return content[start:next_step]


class TestSpecCriterion1PlanCriticInvocation:
    """AC1: /implement without prior /plan invokes budget plan-critic at STEP 5.5."""

    def test_spec_855_1_step_55_exists_after_step_5(self, content: str):
        """STEP 5.5 MUST appear after STEP 5 (planner) in the pipeline."""
        step_5_pos = content.find("### STEP 5:")
        if step_5_pos == -1:
            step_5_pos = content.find("### STEP 5 ")
        step_55_pos = content.find("### STEP 5.5")
        step_6_pos = content.find("### STEP 6")
        assert step_5_pos != -1, "STEP 5 not found"
        assert step_55_pos != -1, "STEP 5.5 not found"
        assert step_6_pos != -1, "STEP 6 not found"
        assert step_5_pos < step_55_pos < step_6_pos, (
            "STEP 5.5 must be positioned between STEP 5 and STEP 6"
        )

    def test_spec_855_1_plan_critic_agent_invoked(self, step_55_section: str):
        """When no pre-validated plan exists, plan-critic agent MUST be invoked."""
        assert "plan-critic" in step_55_section.lower(), (
            "STEP 5.5 must reference plan-critic agent invocation"
        )

    def test_spec_855_1_budget_constrained_single_round(self, step_55_section: str):
        """Plan-critic invocation MUST be budget-constrained to 1 round."""
        assert "1" in step_55_section, "Must specify single round"
        lower = step_55_section.lower()
        assert "single pass" in lower or "rounds: 1" in lower or "single-pass" in lower, (
            "Plan-critic must be constrained to a single pass/round"
        )

    def test_spec_855_1_three_axes_specified(self, step_55_section: str):
        """Plan-critic MUST use exactly 3 axes: Assumption Audit, Existing Solution Search, Minimalism Pressure."""
        lower = step_55_section.lower()
        assert "assumption audit" in lower, "Must specify Assumption Audit axis"
        assert "existing solution search" in lower, "Must specify Existing Solution Search axis"
        assert "minimalism pressure" in lower, "Must specify Minimalism Pressure axis"

    def test_spec_855_1_verdict_outcomes_defined(self, step_55_section: str):
        """Plan-critic must produce one of PROCEED, REVISE, or BLOCKED verdicts."""
        assert "PROCEED" in step_55_section, "Must define PROCEED verdict"
        assert "REVISE" in step_55_section, "Must define REVISE verdict"
        assert "BLOCKED" in step_55_section, "Must define BLOCKED verdict"


class TestSpecCriterion2PreValidatedPlanSkip:
    """AC2: /implement after /plan (with validated plan file) skips plan-critic with log message."""

    def test_spec_855_2_pre_validated_plan_check(self, step_55_section: str):
        """STEP 5.5 MUST check .claude/plans/ for pre-validated plan files."""
        assert ".claude/plans/" in step_55_section, (
            "Must reference .claude/plans/ directory for pre-validated plan lookup"
        )

    def test_spec_855_2_skip_on_validated_plan(self, step_55_section: str):
        """When a pre-validated plan with 'Verdict: PROCEED' exists, plan-critic MUST be skipped."""
        lower = step_55_section.lower()
        assert "skip" in lower, "Must mention skipping plan-critic for validated plans"
        assert "Verdict: PROCEED" in step_55_section, (
            "Must check for 'Verdict: PROCEED' string in plan file"
        )

    def test_spec_855_2_log_message_format(self, step_55_section: str):
        """Skip action MUST produce a log message indicating the pre-validated plan path."""
        assert "Plan validation: SKIPPED" in step_55_section, (
            "Must include log message format 'Plan validation: SKIPPED (pre-validated plan: {path})'"
        )


class TestSpecCriterion3StructuralValidation:
    """AC3: Structural validation catches plans with 0 file paths or no acceptance criteria."""

    def test_spec_855_3_structural_validation_section_exists(self, step_55_section: str):
        """A structural validation subsection MUST exist within STEP 5.5."""
        lower = step_55_section.lower()
        assert "structural validation" in lower, (
            "STEP 5.5 must contain a structural validation subsection"
        )

    def test_spec_855_3_file_path_requirement(self, step_55_section: str):
        """Structural validation MUST require at least 1 file path in the plan."""
        lower = step_55_section.lower()
        assert "file path" in lower, "Must validate file paths"
        # Check for the >= 1 requirement
        assert re.search(r"(?:≥\s*1|at least 1|at least one|>=\s*1)", lower), (
            "Must require at least 1 file path"
        )

    def test_spec_855_3_acceptance_criteria_requirement(self, step_55_section: str):
        """Structural validation MUST require an acceptance criteria section."""
        lower = step_55_section.lower()
        assert "acceptance criteria" in lower, (
            "Must validate presence of acceptance criteria section"
        )

    def test_spec_855_3_always_runs(self, step_55_section: str):
        """Structural validation MUST always run, even when plan-critic is skipped."""
        lower = step_55_section.lower()
        assert "always runs" in lower, (
            "Must explicitly state structural validation always runs"
        )

    def test_spec_855_3_block_on_failure(self, step_55_section: str):
        """Structural validation failure MUST block the pipeline after one revision attempt."""
        assert "BLOCKED (STEP 5.5)" in step_55_section, (
            "Must block pipeline with 'BLOCKED (STEP 5.5)' message on structural validation failure"
        )


class TestSpecCriterion4ForbiddenList:
    """AC4: FORBIDDEN list prevents skipping plan-critic when no validated plan exists."""

    def test_spec_855_4_forbidden_section_exists(self, step_55_section: str):
        """A FORBIDDEN section MUST exist within STEP 5.5."""
        assert "FORBIDDEN" in step_55_section, (
            "STEP 5.5 must contain a FORBIDDEN section"
        )

    def test_spec_855_4_forbids_zero_file_paths(self, step_55_section: str):
        """FORBIDDEN list MUST prohibit accepting a plan with 0 file paths."""
        lower = step_55_section.lower()
        assert "0 file path" in lower, (
            "FORBIDDEN list must explicitly prohibit 0 file paths"
        )

    def test_spec_855_4_forbids_no_acceptance_criteria(self, step_55_section: str):
        """FORBIDDEN list MUST prohibit accepting a plan with no acceptance criteria."""
        lower = step_55_section.lower()
        assert "no acceptance criteria" in lower, (
            "FORBIDDEN list must explicitly prohibit no acceptance criteria"
        )

    def test_spec_855_4_forbids_skipping_plan_critic_without_validated_plan(
        self, step_55_section: str
    ):
        """FORBIDDEN list MUST prohibit skipping plan-critic when no pre-validated plan exists."""
        # Look for the specific prohibition
        lower = step_55_section.lower()
        assert "skip plan-critic" in lower, (
            "FORBIDDEN list must prohibit skipping plan-critic"
        )
        assert ".claude/plans/" in step_55_section, (
            "FORBIDDEN list must reference .claude/plans/ as condition for skipping"
        )

    def test_spec_855_4_forbids_skipping_structural_validation(self, step_55_section: str):
        """FORBIDDEN list MUST prohibit skipping structural validation for any reason."""
        lower = step_55_section.lower()
        assert "skip structural validation" in lower, (
            "FORBIDDEN list must prohibit skipping structural validation"
        )


class TestSpecCriterion5HardGateLanguage:
    """AC5: Regression test validates HARD GATE language presence."""

    def test_spec_855_5_hard_gate_in_header(self, step_55_section: str):
        """STEP 5.5 header MUST contain 'HARD GATE' designation."""
        # Check the first line / header of the section
        first_line = step_55_section.split("\n")[0]
        assert "HARD GATE" in first_line, (
            f"STEP 5.5 header must contain 'HARD GATE'. Got: {first_line}"
        )

    def test_spec_855_5_must_not_language(self, step_55_section: str):
        """STEP 5.5 MUST use RFC 2119 'MUST NOT' enforcement language."""
        assert "MUST NOT" in step_55_section, (
            "STEP 5.5 must use RFC 2119 'MUST NOT' language for enforcement"
        )

    def test_spec_855_5_step_banner_format(self, step_55_section: str):
        """STEP 5.5 MUST specify the progress banner format."""
        assert "STEP 5.5/15" in step_55_section, (
            "Must specify step banner format as 'STEP 5.5/15'"
        )
