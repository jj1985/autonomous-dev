"""
Regression tests for Issue #858: Structural plan validation gate for --light pipeline.

Bug: The --light pipeline's STEP L3 Implementer received unvalidated planner output.
A planner that returned vague language ("update relevant files") with no specific
file paths or testing strategy would silently pass to the implementer, resulting in
wasted tokens or incorrect implementation scope.

Fix: Added STEP L2.5 Plan Structural Validation HARD GATE between STEP L2 and STEP L3
in the LIGHT PIPELINE MODE section of implement.md. The gate checks for:
  1. At least one specific file path in the plan
  2. A testing strategy or explicit "no new tests" statement
  3. A "Recommended implementer model: sonnet|opus" line

These tests verify the gate infrastructure exists and would break if removed.
"""

from pathlib import Path

import pytest

# Portable project root detection
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

PLUGIN_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev"
IMPLEMENT_MD = PLUGIN_DIR / "commands" / "implement.md"


def _get_light_section(content: str) -> str:
    """Extract the LIGHT PIPELINE MODE section from implement.md."""
    start = content.find("# LIGHT PIPELINE MODE")
    assert start != -1, "LIGHT PIPELINE MODE section not found in implement.md"
    return content[start:]


def _get_step_l2_5_section(content: str) -> str:
    """Extract the STEP L2.5 section, bounded by STEP L3."""
    light_section = _get_light_section(content)
    step_start = light_section.find("### STEP L2.5:")
    assert step_start != -1, "STEP L2.5 not found in LIGHT PIPELINE MODE section"
    step_l3_pos = light_section.find("### STEP L3:")
    assert step_l3_pos != -1, "STEP L3 not found as boundary in LIGHT PIPELINE MODE section"
    return light_section[step_start:step_l3_pos]


class TestIssue858LightPlanValidationGate:
    """Regression: implement.md must have STEP L2.5 Plan Structural Validation HARD GATE."""

    def test_step_l2_5_exists(self):
        """STEP L2.5 heading must be present in the LIGHT PIPELINE MODE section."""
        content = IMPLEMENT_MD.read_text()
        light_section = _get_light_section(content)
        assert "### STEP L2.5:" in light_section, (
            "Regression #858: STEP L2.5 heading must exist in LIGHT PIPELINE MODE section "
            "of implement.md"
        )

    def test_step_l2_5_is_hard_gate(self):
        """STEP L2.5 must be designated as a HARD GATE."""
        content = IMPLEMENT_MD.read_text()
        section = _get_step_l2_5_section(content)
        assert "HARD GATE" in section, (
            "Regression #858: STEP L2.5 must be designated as a HARD GATE"
        )

    def test_structural_check_file_paths(self):
        """STEP L2.5 must specify a check for specific file paths in the plan."""
        content = IMPLEMENT_MD.read_text()
        section = _get_step_l2_5_section(content)
        # Must mention file paths as a required element
        assert "file path" in section.lower(), (
            "Regression #858: STEP L2.5 must require at least one specific file path "
            "in the planner output"
        )

    def test_structural_check_testing_strategy(self):
        """STEP L2.5 must specify a check for a testing strategy or opt-out statement."""
        content = IMPLEMENT_MD.read_text()
        section = _get_step_l2_5_section(content)
        assert "testing" in section.lower(), (
            "Regression #858: STEP L2.5 must include a check for a testing strategy "
            "or an explicit 'no new tests' statement in the planner output"
        )

    def test_structural_check_implementer_model(self):
        """STEP L2.5 must require the planner to include a model recommendation."""
        content = IMPLEMENT_MD.read_text()
        section = _get_step_l2_5_section(content)
        assert "Recommended implementer model:" in section, (
            "Regression #858: STEP L2.5 must require the exact phrase "
            "'Recommended implementer model:' in the planner output"
        )

    def test_forbidden_list_present(self):
        """STEP L2.5 must have a FORBIDDEN list preventing bypass."""
        content = IMPLEMENT_MD.read_text()
        section = _get_step_l2_5_section(content)
        assert "FORBIDDEN" in section, (
            "Regression #858: STEP L2.5 must include a FORBIDDEN list"
        )

    def test_step_l2_5_positioned_between_l2_and_l3(self):
        """STEP L2.5 must appear after STEP L2 and before STEP L3 in the document."""
        content = IMPLEMENT_MD.read_text()
        light_section = _get_light_section(content)

        l2_pos = light_section.find("### STEP L2:")
        l2_5_pos = light_section.find("### STEP L2.5:")
        l3_pos = light_section.find("### STEP L3:")

        assert l2_pos != -1, "STEP L2 not found in LIGHT PIPELINE MODE section"
        assert l2_5_pos != -1, "STEP L2.5 not found in LIGHT PIPELINE MODE section"
        assert l3_pos != -1, "STEP L3 not found in LIGHT PIPELINE MODE section"

        assert l2_pos < l2_5_pos < l3_pos, (
            "Regression #858: STEP L2.5 must be positioned after STEP L2 and "
            f"before STEP L3 (L2 at {l2_pos}, L2.5 at {l2_5_pos}, L3 at {l3_pos})"
        )
