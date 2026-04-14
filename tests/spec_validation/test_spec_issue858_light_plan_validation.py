"""Spec validation tests for Issue #858: Structural plan validation for --light pipeline.

Validates acceptance criteria:
1. Light pipeline validates planner output for file paths, testing strategy, model recommendation
2. Missing items trigger planner re-invocation (1 retry)
3. Vague plans ("update relevant files") are caught and rejected
4. Regression test validates gate language presence
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_MD = PROJECT_ROOT / "plugins/autonomous-dev/commands/implement.md"
REGRESSION_TEST = (
    PROJECT_ROOT / "tests/regression/progression/test_issue_858_light_plan_validation_gate.py"
)


@pytest.fixture(scope="module")
def implement_content() -> str:
    """Read implement.md content."""
    assert IMPLEMENT_MD.exists(), f"implement.md not found at {IMPLEMENT_MD}"
    return IMPLEMENT_MD.read_text()


@pytest.fixture(scope="module")
def light_section(implement_content: str) -> str:
    """Extract the LIGHT PIPELINE MODE section from implement.md."""
    start = implement_content.find("# LIGHT PIPELINE MODE")
    assert start != -1, "LIGHT PIPELINE MODE section not found in implement.md"
    return implement_content[start:]


@pytest.fixture(scope="module")
def step_l25_section(light_section: str) -> str:
    """Extract STEP L2.5 section, bounded by STEP L3."""
    start = light_section.find("### STEP L2.5:")
    assert start != -1, "STEP L2.5 not found in LIGHT PIPELINE MODE section"
    end = light_section.find("### STEP L3:", start + 1)
    assert end != -1, "STEP L3 not found as boundary after STEP L2.5"
    return light_section[start:end]


class TestSpecCriterion1ValidatesFilePaths:
    """AC1a: Light pipeline validates planner output for file paths."""

    def test_spec_858_1a_step_l25_exists_in_light_pipeline(self, light_section: str):
        """STEP L2.5 MUST exist in the LIGHT PIPELINE MODE section."""
        assert "### STEP L2.5:" in light_section

    def test_spec_858_1a_step_l25_is_hard_gate(self, step_l25_section: str):
        """STEP L2.5 MUST be designated as a HARD GATE."""
        assert "HARD GATE" in step_l25_section

    def test_spec_858_1a_file_path_check_present(self, step_l25_section: str):
        """STEP L2.5 MUST require specific file paths in planner output."""
        lower = step_l25_section.lower()
        assert "file path" in lower, (
            "STEP L2.5 must mention file path validation"
        )


class TestSpecCriterion1ValidatesTestingStrategy:
    """AC1b: Light pipeline validates planner output for testing strategy."""

    def test_spec_858_1b_testing_strategy_check_present(self, step_l25_section: str):
        """STEP L2.5 MUST require a testing strategy or explicit opt-out."""
        lower = step_l25_section.lower()
        assert "testing" in lower, (
            "STEP L2.5 must mention testing strategy validation"
        )


class TestSpecCriterion1ValidatesModelRecommendation:
    """AC1c: Light pipeline validates planner output for model recommendation."""

    def test_spec_858_1c_model_recommendation_check_present(self, step_l25_section: str):
        """STEP L2.5 MUST require 'Recommended implementer model:' phrase."""
        assert "Recommended implementer model:" in step_l25_section, (
            "STEP L2.5 must require the exact phrase 'Recommended implementer model:'"
        )


class TestSpecCriterion2RetryOnMissing:
    """AC2: Missing items trigger planner re-invocation (1 retry)."""

    def test_spec_858_2_re_invoke_on_first_failure(self, step_l25_section: str):
        """STEP L2.5 MUST describe re-invoking the planner on first validation failure."""
        lower = step_l25_section.lower()
        # Must mention re-invocation / retry behavior
        assert any(phrase in lower for phrase in [
            "re-invoke", "re-plan", "re-invok",
        ]), (
            "STEP L2.5 must describe re-invoking the planner on first failure"
        )

    def test_spec_858_2_block_on_second_failure(self, step_l25_section: str):
        """STEP L2.5 MUST block the pipeline on second validation failure."""
        lower = step_l25_section.lower()
        assert "block" in lower, (
            "STEP L2.5 must describe blocking the pipeline on second failure"
        )

    def test_spec_858_2_exactly_one_retry(self, step_l25_section: str):
        """STEP L2.5 describes first failure -> retry, second failure -> block (1 retry total)."""
        lower = step_l25_section.lower()
        # "on validation failure" -> re-invoke, "on second failure" -> block
        has_first_failure = "on validation failure" in lower or "first failure" in lower
        has_second_failure = "second failure" in lower
        assert has_first_failure and has_second_failure, (
            "STEP L2.5 must describe both first failure (retry) and second failure (block) behavior"
        )


class TestSpecCriterion3VaguePlansRejected:
    """AC3: Vague plans ('update relevant files') are caught and rejected."""

    def test_spec_858_3_vague_language_explicitly_forbidden(self, step_l25_section: str):
        """STEP L2.5 MUST explicitly mention rejecting vague language."""
        assert "update relevant files" in step_l25_section.lower(), (
            "STEP L2.5 must explicitly call out 'update relevant files' as an example of "
            "vague language that does not count"
        )

    def test_spec_858_3_forbidden_list_present(self, step_l25_section: str):
        """STEP L2.5 MUST include a FORBIDDEN list."""
        assert "FORBIDDEN" in step_l25_section, (
            "STEP L2.5 must include a FORBIDDEN list to prevent bypass"
        )

    def test_spec_858_3_zero_file_paths_forbidden(self, step_l25_section: str):
        """STEP L2.5 MUST forbid accepting planner output with 0 specific file paths."""
        assert "0 specific file path" in step_l25_section.lower(), (
            "STEP L2.5 FORBIDDEN list must explicitly reject plans with 0 specific file paths"
        )


class TestSpecCriterion4RegressionTestExists:
    """AC4: Regression test validates gate language presence."""

    def test_spec_858_4_regression_test_file_exists(self):
        """A regression test file for issue 858 MUST exist."""
        assert REGRESSION_TEST.exists(), (
            f"Regression test not found at {REGRESSION_TEST}"
        )

    def test_spec_858_4_regression_test_covers_step_l25(self):
        """Regression test MUST verify STEP L2.5 existence and structure."""
        content = REGRESSION_TEST.read_text()
        assert "STEP L2.5" in content, (
            "Regression test must reference STEP L2.5"
        )
        assert "HARD GATE" in content, (
            "Regression test must verify HARD GATE designation"
        )

    def test_spec_858_4_step_l25_positioned_between_l2_and_l3(self, light_section: str):
        """STEP L2.5 MUST appear after STEP L2 and before STEP L3 in the document."""
        l2_pos = light_section.find("### STEP L2:")
        l25_pos = light_section.find("### STEP L2.5:")
        l3_pos = light_section.find("### STEP L3:")

        assert l2_pos != -1, "STEP L2 not found"
        assert l25_pos != -1, "STEP L2.5 not found"
        assert l3_pos != -1, "STEP L3 not found"
        assert l2_pos < l25_pos < l3_pos, (
            f"STEP L2.5 must be positioned between L2 and L3 "
            f"(L2={l2_pos}, L2.5={l25_pos}, L3={l3_pos})"
        )
