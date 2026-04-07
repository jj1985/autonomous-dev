"""Regression tests for Issue #646: STEP 6 acceptance test generation silently skipped.

Bug: STEP 6 in implement.md could be silently skipped — the coordinator went
planner -> implementer without generating acceptance tests or logging why.
The step had no FORBIDDEN list preventing silent skips and no required logging.

Fix: Added explicit skip logging requirement, FORBIDDEN list, and banner
requirement to STEP 6 in implement.md.

These tests validate that the STEP 6 section contains the required enforcement
language so the bug cannot regress.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
IMPLEMENT_MD = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"


@pytest.fixture
def step6_section() -> str:
    """Extract the STEP 6 section from implement.md."""
    content = IMPLEMENT_MD.read_text()
    step6_start = content.find("### STEP 6")
    assert step6_start != -1, "STEP 6 section not found in implement.md"
    step7_start = content.find("### STEP 7", step6_start + 1)
    assert step7_start != -1, "STEP 7 section not found after STEP 6"
    return content[step6_start:step7_start]


class TestStep6SkipLogging:
    """Validate that STEP 6 requires explicit skip/execute logging."""

    def test_step6_contains_skipped_logging_examples(self, step6_section: str):
        """STEP 6 must contain SKIPPED logging examples so coordinator knows the format."""
        assert "SKIPPED" in step6_section, (
            "STEP 6 must contain 'SKIPPED' logging examples. "
            "Issue #646: silent skips were possible because no skip format was defined."
        )

    def test_step6_contains_executed_logging_example(self, step6_section: str):
        """STEP 6 must contain EXECUTED logging example for the happy path."""
        assert "EXECUTED" in step6_section, (
            "STEP 6 must contain 'EXECUTED' logging example. "
            "Issue #646: coordinator had no defined format for reporting execution."
        )

    def test_step6_contains_tdd_first_skip_reason(self, step6_section: str):
        """STEP 6 must document the --tdd-first skip reason."""
        assert "tdd-first mode" in step6_section.lower() or "--tdd-first mode" in step6_section, (
            "STEP 6 must document the --tdd-first skip reason explicitly."
        )

    def test_step6_contains_conftest_skip_reason(self, step6_section: str):
        """STEP 6 must document the conftest.py-not-found skip reason."""
        assert "conftest.py not found" in step6_section, (
            "STEP 6 must document the conftest.py-not-found skip reason."
        )


class TestStep6ForbiddenList:
    """Validate that STEP 6 has a FORBIDDEN section preventing silent skips."""

    def test_step6_has_forbidden_section(self, step6_section: str):
        """STEP 6 must contain a FORBIDDEN section."""
        assert "**FORBIDDEN**" in step6_section or "FORBIDDEN" in step6_section, (
            "STEP 6 must contain a FORBIDDEN section. "
            "Issue #646: without explicit forbidden behaviors, silent skips were possible."
        )

    def test_step6_forbids_silent_skipping(self, step6_section: str):
        """STEP 6 FORBIDDEN list must explicitly mention silently skipping."""
        assert "Silently skipping" in step6_section or "silently skipping" in step6_section, (
            "STEP 6 FORBIDDEN list must mention 'Silently skipping'. "
            "Issue #646: this was the exact bug — silent skips with no output."
        )

    def test_step6_forbids_skipping_step5_to_step8(self, step6_section: str):
        """STEP 6 FORBIDDEN list must prevent jumping from STEP 5 to STEP 8."""
        assert "STEP 5" in step6_section and "STEP 8" in step6_section, (
            "STEP 6 FORBIDDEN list must mention 'STEP 5 to STEP 8' to prevent "
            "the coordinator from jumping over STEP 6 entirely."
        )

    def test_step6_forbids_skip_when_conftest_exists(self, step6_section: str):
        """STEP 6 FORBIDDEN list must prevent skipping when conftest.py exists and not tdd-first."""
        section_lower = step6_section.lower()
        has_conftest_exists_rule = (
            "conftest.py exists" in section_lower
            and "not --tdd-first" in section_lower
        )
        assert has_conftest_exists_rule, (
            "STEP 6 FORBIDDEN list must prevent skipping when conftest.py exists "
            "and mode is not --tdd-first."
        )


class TestStep6BannerRequirement:
    """Validate that STEP 6 requires outputting the banner even when skipping."""

    def test_step6_requires_banner_on_skip(self, step6_section: str):
        """STEP 6 must require outputting the banner even when skipping."""
        has_banner_on_skip = (
            "banner even when skipping" in step6_section.lower()
            or "banner followed by the skip reason" in step6_section.lower()
        )
        assert has_banner_on_skip, (
            "STEP 6 must explicitly require outputting the step banner even when "
            "skipping. Issue #646: the step was invisible when skipped because "
            "no banner was output."
        )
