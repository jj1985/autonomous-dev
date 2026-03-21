"""Unit tests for STEP 15 continuous improvement enforcement in implement.md.

TDD Red Phase: These tests validate structural properties of the implement command
to ensure STEP 15 enforcement is properly configured with HARD GATE, FORBIDDEN list,
cleanup ordering, and coordinator-level references.
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
def step15_section(implement_content: str) -> str:
    """Extract STEP 15 section content."""
    match = re.search(
        r"### STEP 15.*?(?=\n---|\n# |\Z)", implement_content, re.DOTALL
    )
    assert match, "STEP 15 section not found in implement.md"
    return match.group(0)


@pytest.fixture
def step13_section(implement_content: str) -> str:
    """Extract STEP 13 section content."""
    match = re.search(
        r"### STEP 13.*?(?=\n### STEP 14|\n---\s*\n### STEP 14|\Z)",
        implement_content,
        re.DOTALL,
    )
    assert match, "STEP 13 section not found in implement.md"
    return match.group(0)


@pytest.fixture
def coordinator_forbidden(implement_content: str) -> str:
    """Extract COORDINATOR FORBIDDEN LIST section."""
    match = re.search(
        r"COORDINATOR FORBIDDEN LIST.*?(?=\nARGUMENTS|\n---|\n###)",
        implement_content,
        re.DOTALL,
    )
    assert match, "COORDINATOR FORBIDDEN LIST not found"
    return match.group(0)


@pytest.fixture
def quick_mode_section(implement_content: str) -> str:
    """Extract QUICK MODE section (removed in v3.50.0)."""
    match = re.search(r"# QUICK MODE.*?(?=\n# [A-Z]|\Z)", implement_content, re.DOTALL)
    if not match:
        pytest.skip("QUICK MODE section was removed from implement.md (quick mode deprecated)")
    return match.group(0)


class TestStep15HardGate:
    """STEP 15 must have HARD GATE enforcement markers."""

    def test_step15_contains_hard_gate(self, step15_section: str):
        """STEP 15 should contain a HARD GATE marker."""
        assert "HARD GATE" in step15_section, (
            "STEP 15 missing HARD GATE marker — enforcement requires explicit gate"
        )

    def test_step15_contains_forbidden_keyword(self, step15_section: str):
        """STEP 15 should contain FORBIDDEN keyword."""
        assert "FORBIDDEN" in step15_section

    def test_step15_has_at_least_3_forbidden_items(self, step15_section: str):
        """STEP 15 FORBIDDEN list should have at least 3 items."""
        # Count lines starting with - or * after FORBIDDEN
        forbidden_match = re.search(
            r"FORBIDDEN.*?\n((?:\s*[-*].*\n){1,})", step15_section, re.DOTALL
        )
        assert forbidden_match, "No FORBIDDEN list items found in STEP 15"
        items = [
            line.strip()
            for line in forbidden_match.group(1).splitlines()
            if line.strip().startswith(("-", "*"))
        ]
        assert len(items) >= 3, (
            f"STEP 15 FORBIDDEN list has only {len(items)} items, need >= 3"
        )

    def test_step15_contains_required_keyword(self, step15_section: str):
        """STEP 15 should contain REQUIRED keyword."""
        assert "REQUIRED" in step15_section


class TestStep15Content:
    """STEP 15 must reference the right agent and execution model."""

    def test_step15_mentions_run_in_background(self, step15_section: str):
        """STEP 15 should mention run_in_background for non-blocking execution."""
        assert "run_in_background" in step15_section, (
            "STEP 15 should specify run_in_background for async execution"
        )

    def test_step15_mentions_analyst_agent(self, step15_section: str):
        """STEP 15 should reference the continuous-improvement-analyst agent."""
        assert "continuous-improvement-analyst" in step15_section


class TestCleanupOrdering:
    """Pipeline state cleanup must be in STEP 15, not STEP 13."""

    def test_cleanup_not_in_step13(self, step13_section: str):
        """Cleanup (rm implement_pipeline_state.json) should NOT be in STEP 13."""
        assert "implement_pipeline_state.json" not in step13_section, (
            "Cleanup should be moved from STEP 13 to STEP 15"
        )

    def test_cleanup_in_step15(self, step15_section: str):
        """Cleanup (rm implement_pipeline_state.json) should be in STEP 15."""
        assert "implement_pipeline_state.json" in step15_section, (
            "STEP 15 should contain pipeline state cleanup"
        )


class TestCoordinatorForbiddenList:
    """Coordinator-level FORBIDDEN list must reference STEP 15."""

    def test_coordinator_forbidden_mentions_step15(self, coordinator_forbidden: str):
        """Coordinator FORBIDDEN list should include skipping STEP 15."""
        # Either "STEP 15" or "continuous improvement" should appear
        has_step15 = "STEP 15" in coordinator_forbidden
        has_ci = "continuous improvement" in coordinator_forbidden.lower()
        assert has_step15 or has_ci, (
            "COORDINATOR FORBIDDEN LIST must reference STEP 15 or continuous improvement"
        )


class TestQuickModeStep15:
    """QUICK MODE must also invoke STEP 15."""

    def test_quick_mode_mentions_step15(self, quick_mode_section: str):
        """QUICK MODE should reference STEP 15 or continuous improvement."""
        has_step15 = "STEP 15" in quick_mode_section or "step 15" in quick_mode_section.lower()
        has_ci = "continuous improvement" in quick_mode_section.lower()
        assert has_step15 or has_ci, (
            "QUICK MODE must invoke STEP 15 continuous improvement analysis"
        )

    def test_quick_mode_cleanup_after_step15(self, quick_mode_section: str):
        """In QUICK MODE, cleanup should appear AFTER STEP 15 reference."""
        step15_pos = quick_mode_section.lower().find("step 15")
        if step15_pos == -1:
            step15_pos = quick_mode_section.lower().find("continuous improvement")
        cleanup_pos = quick_mode_section.find("implement_pipeline_state.json")

        assert step15_pos != -1, "QUICK MODE missing STEP 15 reference"
        assert cleanup_pos != -1, "QUICK MODE missing cleanup"
        assert cleanup_pos > step15_pos, (
            "QUICK MODE cleanup must appear AFTER STEP 15 reference"
        )
