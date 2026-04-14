"""Spec validation tests for Issue #857: Plan-implementation alignment check after STEP 8.

Validates acceptance criteria:
1. Coordinator compares planned vs actual file lists after STEP 8
2. Warnings emitted for unplanned or missing files
3. Pipeline blocks when >50% of files are unplanned
4. Single planned-but-skipped file produces WARNING, not BLOCK
5. Regression test validates gate language presence in implement.md
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_MD = PROJECT_ROOT / "plugins/autonomous-dev/commands/implement.md"
REGRESSION_TEST = (
    PROJECT_ROOT / "tests/regression/progression/test_issue_857_plan_alignment_gate.py"
)


@pytest.fixture(scope="module")
def implement_content() -> str:
    """Read implement.md content."""
    assert IMPLEMENT_MD.exists(), f"implement.md not found at {IMPLEMENT_MD}"
    return IMPLEMENT_MD.read_text()


@pytest.fixture(scope="module")
def alignment_section(implement_content: str) -> str:
    """Extract the Plan-Implementation Alignment gate section from implement.md."""
    start = implement_content.find("Plan-Implementation Alignment")
    assert start != -1, "Plan-Implementation Alignment section not found in implement.md"
    # Find the next major section header (### STEP)
    rest = implement_content[start:]
    end_match = re.search(r"\n### STEP", rest)
    if end_match:
        return rest[: end_match.start()]
    return rest[:3000]


class TestSpecCriterion1CompareAfterStep8:
    """AC1: Coordinator compares planned vs actual file lists after STEP 8."""

    def test_spec_857_1_alignment_section_exists(self, implement_content: str):
        """implement.md MUST contain a Plan-Implementation Alignment section."""
        assert "Plan-Implementation Alignment" in implement_content

    def test_spec_857_1_section_after_step8_before_step85(self, implement_content: str):
        """The alignment gate MUST appear after STEP 8 content and before STEP 8.5."""
        alignment_pos = implement_content.find("Plan-Implementation Alignment")
        # Use the section header, not an earlier mention in the FORBIDDEN list
        step_85_pos = implement_content.find("### STEP 8.5")
        assert step_85_pos != -1, "STEP 8.5 section header not found"
        assert alignment_pos < step_85_pos, (
            "Alignment gate must be positioned between STEP 8 and STEP 8.5"
        )

    def test_spec_857_1_compares_planned_vs_actual(self, alignment_section: str):
        """The section MUST reference both planned files and implemented/actual files."""
        lower = alignment_section.lower()
        assert "planned" in lower, "Section must reference planned files"
        assert "implemented" in lower or "actual" in lower, (
            "Section must reference implemented/actual files"
        )

    def test_spec_857_1_uses_git_diff(self, alignment_section: str):
        """The section MUST use git diff to collect implemented files."""
        assert "git diff" in alignment_section, (
            "Section must use git diff to collect implemented files"
        )


class TestSpecCriterion2WarningsForMismatches:
    """AC2: Warnings emitted for unplanned or missing files."""

    def test_spec_857_2_warning_for_unplanned_files(self, alignment_section: str):
        """The gate MUST specify WARNING for files in implementation but not in plan."""
        # The section should mention WARNING in the context of unplanned files
        assert "WARNING" in alignment_section, (
            "Alignment gate must include WARNING language"
        )
        # Check that unplanned files get a warning
        lower = alignment_section.lower()
        assert "not in plan" in lower or "not planned" in lower or "unplanned" in lower, (
            "Gate must mention files that are not in the plan"
        )

    def test_spec_857_2_warning_for_missing_files(self, alignment_section: str):
        """The gate MUST specify WARNING for files in plan but not implemented."""
        lower = alignment_section.lower()
        assert "not in implementation" in lower or "not implemented" in lower or "missing" in lower, (
            "Gate must mention files planned but not implemented"
        )


class TestSpecCriterion3BlockOver50Percent:
    """AC3: Pipeline blocks when >50% of files are unplanned."""

    def test_spec_857_3_50_percent_threshold(self, alignment_section: str):
        """The gate MUST specify a 50% threshold for blocking."""
        assert "50%" in alignment_section, (
            "Alignment gate must specify the 50% divergence threshold"
        )

    def test_spec_857_3_block_verdict(self, alignment_section: str):
        """The gate MUST include a BLOCK verdict for exceeding the threshold."""
        assert "BLOCK" in alignment_section, (
            "Alignment gate must include BLOCK verdict for >50% divergence"
        )

    def test_spec_857_3_block_linked_to_threshold(self, alignment_section: str):
        """The BLOCK action MUST be tied to the >50% condition."""
        # Find a sentence or line that connects 50% and BLOCK
        lines = alignment_section.split("\n")
        found = False
        for line in lines:
            if "50%" in line and "BLOCK" in line:
                found = True
                break
        assert found, (
            "A single line/instruction must connect the 50% threshold to the BLOCK action"
        )


class TestSpecCriterion4SingleMissingFileWarnsNotBlocks:
    """AC4: Single planned-but-skipped file produces WARNING, not BLOCK."""

    def test_spec_857_4_individual_missing_is_warning(self, alignment_section: str):
        """Individual planned-but-not-implemented files MUST produce WARNING, not BLOCK."""
        # The section must have WARNING for individual file mismatches
        # and BLOCK only for >50% divergence
        lines = alignment_section.split("\n")
        warning_lines = [l for l in lines if "WARNING" in l]
        block_lines = [l for l in lines if "BLOCK" in l]

        # WARNING must exist for individual files (not just as part of BLOCK)
        assert len(warning_lines) > 0, "Must have WARNING lines for individual mismatches"

        # BLOCK lines must all reference the percentage threshold
        for line in block_lines:
            if "FORBIDDEN" in line or "Skipping" in line:
                continue  # Skip FORBIDDEN list items about skipping the gate
            if "BLOCK" in line and "50%" not in line and "divergence" not in line.lower():
                # Allow block lines in verdict format that reference percentage
                if "%" not in line:
                    pytest.fail(
                        f"BLOCK verdict appears without percentage qualifier: {line.strip()}"
                    )


class TestSpecCriterion5RegressionTestExists:
    """AC5: Regression test validates gate language presence in implement.md."""

    def test_spec_857_5_regression_test_file_exists(self):
        """A regression test file for issue 857 MUST exist."""
        assert REGRESSION_TEST.exists(), (
            f"Regression test not found at {REGRESSION_TEST}"
        )

    def test_spec_857_5_regression_test_validates_gate_language(self):
        """The regression test MUST check for gate language in implement.md."""
        content = REGRESSION_TEST.read_text()
        assert "Plan-Implementation Alignment" in content, (
            "Regression test must validate Plan-Implementation Alignment gate presence"
        )
        assert "implement.md" in content.lower() or "IMPLEMENT_MD" in content, (
            "Regression test must reference implement.md"
        )

    def test_spec_857_5_regression_test_checks_warning(self):
        """The regression test MUST validate WARNING language exists."""
        content = REGRESSION_TEST.read_text()
        assert "WARNING" in content, (
            "Regression test must validate WARNING language in the gate"
        )

    def test_spec_857_5_regression_test_checks_block_threshold(self):
        """The regression test MUST validate the 50% block threshold."""
        content = REGRESSION_TEST.read_text()
        assert "50%" in content, (
            "Regression test must validate the 50% block threshold"
        )
