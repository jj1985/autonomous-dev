"""Unit tests for STEP 14 documentation congruence validation in implement.md.

TDD Red Phase: These tests validate that implement.md has a STEP 14 section
for documentation congruence validation between STEP 13 (Report and Finalize)
and STEP 15 (Continuous Improvement Analysis).

Issue #393: Add documentation congruence validation step.
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
IMPLEMENT_MD = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"


@pytest.fixture
def implement_content() -> str:
    """Load implement.md content."""
    assert IMPLEMENT_MD.exists(), f"implement.md not found at {IMPLEMENT_MD}"
    return IMPLEMENT_MD.read_text()


@pytest.fixture
def step_14_section(implement_content: str) -> str:
    """Extract STEP 14 section content.

    Matches '### STEP 14' heading up to the next step heading or end of file.
    """
    match = re.search(
        r"### STEP 14.*?(?=\n### STEP [0-9]|\n---\s*\n### STEP|\n# [A-Z]|\Z)",
        implement_content,
        re.DOTALL,
    )
    assert match, (
        "STEP 14 section not found in implement.md. "
        "Expected a '### STEP 14' heading for documentation congruence validation."
    )
    return match.group(0)


class TestStep14Exists:
    """STEP 14 must exist in implement.md."""

    def test_implement_has_step_14(self, implement_content: str):
        """implement.md must contain a STEP 14 section.

        STEP 14 is the documentation congruence validation step that runs
        between STEP 13 (Report and Finalize) and STEP 15 (Continuous Improvement).
        """
        assert "STEP 14" in implement_content, (
            "implement.md is missing STEP 14 for documentation congruence validation. "
            "This step should be added between STEP 13 and STEP 15."
        )


class TestStep14Content:
    """STEP 14 must reference documentation congruence tests."""

    def test_step_14_runs_congruence_tests(self, step_14_section: str):
        """STEP 14 must reference test_documentation_congruence.py.

        The step should invoke or mention the congruence test file that validates
        documentation matches implementation.
        """
        assert "test_documentation_congruence" in step_14_section, (
            "STEP 14 does not reference test_documentation_congruence.py. "
            "This test file validates that docs match code and must be invoked in STEP 14."
        )


class TestStep14Ordering:
    """STEP 14 must appear between STEP 13 and STEP 15."""

    def test_step_14_between_13_and_15(self, implement_content: str):
        """STEP 14 must appear AFTER STEP 13 and BEFORE STEP 15 in implement.md.

        The ordering is critical: STEP 13 finalizes the report, STEP 14 validates
        documentation congruence, and STEP 15 runs continuous improvement analysis.
        """
        step13_pos = implement_content.find("### STEP 13:")
        if step13_pos == -1:
            step13_pos = implement_content.find("### STEP 13")
        step14_pos = implement_content.find("### STEP 14")
        step15_pos = implement_content.find("### STEP 15")

        assert step13_pos != -1, "STEP 13 not found in implement.md"
        assert step14_pos != -1, "STEP 14 not found in implement.md"
        assert step15_pos != -1, "STEP 15 not found in implement.md"

        assert step13_pos < step14_pos, (
            f"STEP 14 (pos {step14_pos}) must appear AFTER STEP 13 (pos {step13_pos})"
        )
        assert step14_pos < step15_pos, (
            f"STEP 14 (pos {step14_pos}) must appear BEFORE STEP 15 (pos {step15_pos})"
        )


class TestStep14HardGate:
    """STEP 14 must be a HARD GATE (blocks pipeline on failure)."""

    def test_step_14_is_hard_gate(self, step_14_section: str):
        """STEP 14 must contain 'HARD GATE' text.

        Documentation congruence failures should block the pipeline, not be
        advisory. The HARD GATE designation ensures the coordinator cannot
        skip past congruence failures.
        """
        assert "HARD GATE" in step_14_section, (
            "STEP 14 is missing HARD GATE designation. "
            "Documentation congruence validation must block on failure, "
            "not be an optional or advisory step."
        )
