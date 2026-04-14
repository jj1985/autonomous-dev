"""Spec validation tests for Issue #840: Iterative refinement loops.

Validates that generate->critique->revise (Self-Refine pattern) loops
are added to /advise, /implement reviewer, STEP 4 research, and /refactor deep mode.
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADVISE_MD = PROJECT_ROOT / "plugins/autonomous-dev/commands/advise.md"
IMPLEMENT_MD = PROJECT_ROOT / "plugins/autonomous-dev/commands/implement.md"
REFACTOR_MD = PROJECT_ROOT / "plugins/autonomous-dev/commands/refactor.md"


@pytest.fixture
def advise_content() -> str:
    return ADVISE_MD.read_text()


@pytest.fixture
def implement_content() -> str:
    return IMPLEMENT_MD.read_text()


@pytest.fixture
def refactor_content() -> str:
    return REFACTOR_MD.read_text()


class TestAdviseStepFourPointFive:
    """Criterion 1: /advise contains STEP 4.5 with self-critique between alternatives and output."""

    def test_spec_refinement_1_advise_step_4_5_exists(self, advise_content: str) -> None:
        """STEP 4.5 heading exists in advise.md."""
        assert "### STEP 4.5" in advise_content, (
            "advise.md must contain a '### STEP 4.5' heading"
        )

    def test_spec_refinement_1a_advise_step_4_5_between_step4_and_step5(
        self, advise_content: str
    ) -> None:
        """STEP 4.5 appears between STEP 4 and STEP 5."""
        step4_pos = advise_content.find("### STEP 4:")
        if step4_pos == -1:
            step4_pos = advise_content.find("### STEP 4 ")
        step4_5_pos = advise_content.find("### STEP 4.5")
        step5_pos = advise_content.find("### STEP 5")
        assert step4_pos < step4_5_pos < step5_pos, (
            "STEP 4.5 must appear between STEP 4 and STEP 5 in advise.md"
        )

    def test_spec_refinement_1b_advise_step_4_5_has_self_critique(
        self, advise_content: str
    ) -> None:
        """STEP 4.5 contains self-critique / feedback instructions."""
        step4_5_pos = advise_content.find("### STEP 4.5")
        step5_pos = advise_content.find("### STEP 5")
        step4_5_section = advise_content[step4_5_pos:step5_pos]
        # Must contain critique-related language
        critique_terms = ["critique", "feedback", "refine", "revise"]
        found = any(term.lower() in step4_5_section.lower() for term in critique_terms)
        assert found, (
            "STEP 4.5 in advise.md must contain self-critique instructions "
            f"(expected one of: {critique_terms})"
        )


class TestImplementStepFourPointFive:
    """Criterion 2: /implement contains STEP 4.5 with research completeness critique."""

    def test_spec_refinement_2_implement_step_4_5_exists(
        self, implement_content: str
    ) -> None:
        """STEP 4.5 heading exists in implement.md."""
        assert "### STEP 4.5" in implement_content, (
            "implement.md must contain a '### STEP 4.5' heading"
        )

    def test_spec_refinement_2a_implement_step_4_5_between_step4_and_step5(
        self, implement_content: str
    ) -> None:
        """STEP 4.5 appears between STEP 4 and STEP 5."""
        step4_pos = implement_content.find("### STEP 4:")
        if step4_pos == -1:
            step4_pos = implement_content.find("### STEP 4 ")
        step4_5_pos = implement_content.find("### STEP 4.5")
        step5_pos = implement_content.find("### STEP 5")
        assert step4_pos < step4_5_pos < step5_pos, (
            "STEP 4.5 must appear between STEP 4 and STEP 5 in implement.md"
        )

    def test_spec_refinement_2b_implement_step_4_5_has_research_critique(
        self, implement_content: str
    ) -> None:
        """STEP 4.5 contains research completeness critique instructions."""
        step4_5_pos = implement_content.find("### STEP 4.5")
        step5_pos = implement_content.find("### STEP 5")
        step4_5_section = implement_content[step4_5_pos:step5_pos]
        assert "research" in step4_5_section.lower(), (
            "STEP 4.5 in implement.md must reference research completeness"
        )


class TestImplementStep10FeedbackPass:
    """Criterion 3: STEP 10 reviewer prompt includes FEEDBACK pass in BOTH parallel and sequential."""

    def test_spec_refinement_3_parallel_mode_feedback_pass(
        self, implement_content: str
    ) -> None:
        """Parallel mode reviewer instruction includes FEEDBACK pass."""
        # Find the parallel mode section
        parallel_marker = "**DEFAULT: Parallel mode**"
        sequential_marker = "**SEQUENTIAL mode**"
        parallel_pos = implement_content.find(parallel_marker)
        sequential_pos = implement_content.find(sequential_marker)
        assert parallel_pos != -1, "Parallel mode section must exist in implement.md"
        assert sequential_pos != -1, "Sequential mode section must exist in implement.md"

        parallel_section = implement_content[parallel_pos:sequential_pos]
        assert "FEEDBACK" in parallel_section or "feedback" in parallel_section.lower(), (
            "Parallel mode reviewer instruction must include FEEDBACK pass"
        )
        assert "self-critique" in parallel_section.lower() or "critique" in parallel_section.lower(), (
            "Parallel mode reviewer must include critique instruction"
        )

    def test_spec_refinement_3a_sequential_mode_feedback_pass(
        self, implement_content: str
    ) -> None:
        """Sequential mode reviewer instruction includes FEEDBACK pass."""
        sequential_marker = "**SEQUENTIAL mode**"
        sequential_pos = implement_content.find(sequential_marker)
        assert sequential_pos != -1, "Sequential mode section must exist"

        # Find the end of the sequential reviewer section (STEP 10b)
        step10b_marker = "**STEP 10b:"
        step10b_pos = implement_content.find(step10b_marker, sequential_pos)
        sequential_reviewer = implement_content[sequential_pos:step10b_pos]

        assert "FEEDBACK" in sequential_reviewer or "feedback" in sequential_reviewer.lower(), (
            "Sequential mode reviewer instruction must include FEEDBACK pass"
        )
        assert "self-critique" in sequential_reviewer.lower() or "critique" in sequential_reviewer.lower(), (
            "Sequential mode reviewer must include critique instruction"
        )


class TestRefactorStepOnePointFive:
    """Criterion 4: /refactor contains STEP 1.5 gated on --deep mode."""

    def test_spec_refinement_4_refactor_step_1_5_exists(
        self, refactor_content: str
    ) -> None:
        """STEP 1.5 heading exists in refactor.md."""
        assert "### STEP 1.5" in refactor_content, (
            "refactor.md must contain a '### STEP 1.5' heading"
        )

    def test_spec_refinement_4a_refactor_step_1_5_between_step1_and_step2(
        self, refactor_content: str
    ) -> None:
        """STEP 1.5 appears between STEP 1 and STEP 2."""
        step1_pos = refactor_content.find("### STEP 1:")
        if step1_pos == -1:
            step1_pos = refactor_content.find("### STEP 1 ")
        step1_5_pos = refactor_content.find("### STEP 1.5")
        step2_pos = refactor_content.find("### STEP 2")
        assert step1_pos < step1_5_pos < step2_pos, (
            "STEP 1.5 must appear between STEP 1 and STEP 2 in refactor.md"
        )

    def test_spec_refinement_4b_refactor_step_1_5_deep_mode_only(
        self, refactor_content: str
    ) -> None:
        """STEP 1.5 is gated on --deep mode."""
        step1_5_pos = refactor_content.find("### STEP 1.5")
        step2_pos = refactor_content.find("### STEP 2")
        step1_5_section = refactor_content[step1_5_pos:step2_pos]
        assert "--deep" in step1_5_section, (
            "STEP 1.5 in refactor.md must reference --deep mode"
        )

    def test_spec_refinement_4c_refactor_step_1_5_has_findings_critique(
        self, refactor_content: str
    ) -> None:
        """STEP 1.5 contains findings self-critique."""
        step1_5_pos = refactor_content.find("### STEP 1.5")
        step2_pos = refactor_content.find("### STEP 2")
        step1_5_section = refactor_content[step1_5_pos:step2_pos]
        critique_terms = ["critique", "feedback", "audit", "verify"]
        found = any(term.lower() in step1_5_section.lower() for term in critique_terms)
        assert found, (
            "STEP 1.5 in refactor.md must contain findings self-critique instructions"
        )


class TestSelfRefinePattern:
    """Criterion 5: Each refinement loop follows Self-Refine pattern."""

    def _extract_section(self, content: str, start_heading: str, end_heading: str) -> str:
        """Extract text between two headings."""
        start = content.find(start_heading)
        end = content.find(end_heading, start + len(start_heading))
        assert start != -1, f"Could not find {start_heading}"
        assert end != -1, f"Could not find {end_heading} after {start_heading}"
        return content[start:end]

    def test_spec_refinement_5_advise_self_refine_pattern(
        self, advise_content: str
    ) -> None:
        """advise.md STEP 4.5 references the Self-Refine pattern."""
        section = self._extract_section(advise_content, "### STEP 4.5", "### STEP 5")
        assert "self-refine" in section.lower() or "Self-Refine" in section, (
            "advise.md STEP 4.5 must reference the Self-Refine pattern"
        )

    def test_spec_refinement_5a_implement_research_self_refine_pattern(
        self, implement_content: str
    ) -> None:
        """implement.md STEP 4.5 references the Self-Refine pattern."""
        section = self._extract_section(implement_content, "### STEP 4.5", "### STEP 5")
        assert "self-refine" in section.lower() or "Self-Refine" in section, (
            "implement.md STEP 4.5 must reference the Self-Refine pattern"
        )

    def test_spec_refinement_5b_refactor_self_refine_pattern(
        self, refactor_content: str
    ) -> None:
        """refactor.md STEP 1.5 references the Self-Refine pattern."""
        section = self._extract_section(refactor_content, "### STEP 1.5", "### STEP 2")
        assert "self-refine" in section.lower() or "Self-Refine" in section, (
            "refactor.md STEP 1.5 must reference the Self-Refine pattern"
        )

    def test_spec_refinement_5c_advise_has_generate_critique_revise_phases(
        self, advise_content: str
    ) -> None:
        """advise.md STEP 4.5 has all three Self-Refine phases."""
        section = self._extract_section(advise_content, "### STEP 4.5", "### STEP 5")
        section_lower = section.lower()
        # Must contain generate/initial, critique/feedback, revise/integrate concepts
        has_generate = "generate" in section_lower or "initial" in section_lower
        has_critique = "critique" in section_lower or "feedback" in section_lower
        has_revise = "revise" in section_lower or "refine" in section_lower or "integrate" in section_lower
        assert has_generate and has_critique and has_revise, (
            "STEP 4.5 must contain all three Self-Refine phases: "
            f"generate={has_generate}, critique={has_critique}, revise={has_revise}"
        )


class TestNoExistingStepsChanged:
    """Criterion 6: No existing step numbers are changed (use .5 numbering)."""

    def test_spec_refinement_6_advise_original_steps_preserved(
        self, advise_content: str
    ) -> None:
        """advise.md preserves original STEP 1-5."""
        for step in [1, 2, 3, 4, 5]:
            assert f"### STEP {step}" in advise_content, (
                f"Original STEP {step} must still exist in advise.md"
            )

    def test_spec_refinement_6a_implement_original_steps_preserved(
        self, implement_content: str
    ) -> None:
        """implement.md preserves original STEP 4, 5, 10."""
        for step in [4, 5, 10]:
            assert f"### STEP {step}" in implement_content, (
                f"Original STEP {step} must still exist in implement.md"
            )

    def test_spec_refinement_6b_refactor_original_steps_preserved(
        self, refactor_content: str
    ) -> None:
        """refactor.md preserves original STEP 0, 1, 2, 3, 4."""
        for step in [0, 1, 2, 3, 4]:
            assert f"### STEP {step}" in refactor_content, (
                f"Original STEP {step} must still exist in refactor.md"
            )

    def test_spec_refinement_6c_only_point_five_numbering_added(
        self, advise_content: str, implement_content: str, refactor_content: str
    ) -> None:
        """New steps use .5 numbering only."""
        # advise.md should have STEP 4.5 as new
        assert "### STEP 4.5" in advise_content
        # implement.md should have STEP 4.5 as new
        assert "### STEP 4.5" in implement_content
        # refactor.md should have STEP 1.5 as new
        assert "### STEP 1.5" in refactor_content


class TestRegressionTestsExist:
    """Criterion 7: Regression tests verify all four insertion points."""

    def test_spec_refinement_7_regression_test_file_exists(self) -> None:
        """tests/regression/test_refinement_loops.py exists."""
        regression_file = PROJECT_ROOT / "tests/regression/test_refinement_loops.py"
        assert regression_file.exists(), (
            "tests/regression/test_refinement_loops.py must exist"
        )

    def test_spec_refinement_7a_regression_tests_cover_all_four_points(self) -> None:
        """Regression tests cover advise, implement research, implement reviewer, refactor."""
        regression_file = PROJECT_ROOT / "tests/regression/test_refinement_loops.py"
        content = regression_file.read_text()
        # Must reference all four insertion points
        assert "advise" in content.lower(), "Regression tests must cover /advise"
        assert "implement" in content.lower(), "Regression tests must cover /implement"
        assert "refactor" in content.lower(), "Regression tests must cover /refactor"
        assert "reviewer" in content.lower() or "step 10" in content.lower() or "step_10" in content.lower(), (
            "Regression tests must cover the reviewer FEEDBACK pass"
        )


class TestExistingTestsPass:
    """Criterion 8: All existing tests continue to pass."""

    def test_spec_refinement_8_regression_tests_pass(self) -> None:
        """The new regression test file passes."""
        import subprocess

        result = subprocess.run(
            ["python3", "-m", "pytest",
             str(PROJECT_ROOT / "tests/regression/test_refinement_loops.py"),
             "-v", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=60,
        )
        assert result.returncode == 0, (
            f"Regression tests must pass.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
