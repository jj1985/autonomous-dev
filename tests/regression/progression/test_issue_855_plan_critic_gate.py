"""
Regression tests for Issue #855: STEP 5.5 — conditional plan-critic gate in /implement pipeline.

Bug: The /implement pipeline had no plan validation gate between STEP 5 (Planner) and
STEP 6 (Acceptance Tests). Plans with zero file paths, no acceptance criteria, or no
testing strategy could proceed unchecked.

Fix: Added STEP 5.5 Plan Validation Gate (HARD GATE) with:
- 5.5a: Pre-validated plan skip logic (checks .claude/plans/ for "Verdict: PROCEED")
- 5.5b: Budget plan-critic invocation (1 round, 3 axes: Assumption Audit, Existing
  Solution Search, Minimalism Pressure) when no pre-validated plan exists
- 5.5c: Structural validation (file paths, acceptance criteria, testing strategy)
- 5.5d: FORBIDDEN list (4 items)

These tests verify the fix infrastructure exists and would break if removed.
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


def _get_step_5_5_section(content: str) -> str:
    """Extract the STEP 5.5 section text from implement.md content."""
    marker = "### STEP 5.5:"
    if marker not in content:
        return ""
    start = content.index(marker)
    # Find the next top-level step heading (### STEP 6 or ### STEP 5.5d)
    next_step_marker = "### STEP 6:"
    if next_step_marker in content[start + len(marker):]:
        end = content.index(next_step_marker, start + len(marker))
        return content[start:end]
    return content[start:]


class TestIssue855PlanCriticGate:
    """Regression: STEP 5.5 Plan Validation Gate must exist in implement.md."""

    def test_step_5_5_exists(self):
        """implement.md must contain a STEP 5.5 heading."""
        content = IMPLEMENT_MD.read_text()
        assert "### STEP 5.5:" in content, (
            "Regression #855: implement.md must have a STEP 5.5 section"
        )

    def test_step_5_5_is_hard_gate(self):
        """STEP 5.5 section must declare itself a HARD GATE."""
        content = IMPLEMENT_MD.read_text()
        section = _get_step_5_5_section(content)
        assert section, "Regression #855: STEP 5.5 section not found"
        assert "HARD GATE" in section, (
            "Regression #855: STEP 5.5 must be declared a HARD GATE"
        )

    def test_pre_validated_plan_skip_documented(self):
        """STEP 5.5 must document the pre-validated plan skip logic."""
        content = IMPLEMENT_MD.read_text()
        section = _get_step_5_5_section(content)
        assert section, "Regression #855: STEP 5.5 section not found"
        # Must reference the plans directory
        assert ".claude/plans/" in section, (
            "Regression #855: STEP 5.5 must reference .claude/plans/ for pre-validated plan check"
        )
        # Must reference the PROCEED verdict skip logic
        assert "Verdict: PROCEED" in section, (
            "Regression #855: STEP 5.5 must check for 'Verdict: PROCEED' in pre-validated plan"
        )

    def test_budget_plan_critic_3_axes(self):
        """STEP 5.5 must name all 3 plan-critic axes."""
        content = IMPLEMENT_MD.read_text()
        section = _get_step_5_5_section(content)
        assert section, "Regression #855: STEP 5.5 section not found"
        assert "Assumption Audit" in section, (
            "Regression #855: STEP 5.5 must name 'Assumption Audit' as one of the 3 axes"
        )
        assert "Existing Solution Search" in section, (
            "Regression #855: STEP 5.5 must name 'Existing Solution Search' as one of the 3 axes"
        )
        assert "Minimalism Pressure" in section, (
            "Regression #855: STEP 5.5 must name 'Minimalism Pressure' as one of the 3 axes"
        )

    def test_forbidden_list_complete(self):
        """STEP 5.5 FORBIDDEN list must contain all 4 required items."""
        content = IMPLEMENT_MD.read_text()
        section = _get_step_5_5_section(content)
        assert section, "Regression #855: STEP 5.5 section not found"
        assert "FORBIDDEN" in section, (
            "Regression #855: STEP 5.5 must have a FORBIDDEN list"
        )
        # 1. No plan with 0 file paths
        assert "0 file paths" in section or "zero file path" in section.lower(), (
            "Regression #855: FORBIDDEN list must prohibit plans with 0 file paths"
        )
        # 2. No plan without acceptance criteria
        assert "acceptance criteria" in section.lower(), (
            "Regression #855: FORBIDDEN list must prohibit plans without acceptance criteria"
        )
        # 3. No skipping plan-critic when no pre-validated plan
        assert "skip plan-critic" in section.lower() or "skip the plan-critic" in section.lower(), (
            "Regression #855: FORBIDDEN list must prohibit skipping plan-critic when no "
            "pre-validated plan exists"
        )
        # 4. No skipping structural validation
        assert "structural validation" in section.lower(), (
            "Regression #855: FORBIDDEN list must prohibit skipping structural validation"
        )

    def test_structural_validation_checks(self):
        """STEP 5.5 structural validation must check file paths, acceptance criteria, and testing strategy."""
        content = IMPLEMENT_MD.read_text()
        section = _get_step_5_5_section(content)
        assert section, "Regression #855: STEP 5.5 section not found"
        # File path check
        assert "file path" in section.lower(), (
            "Regression #855: structural validation must check for file paths"
        )
        # Acceptance criteria check
        assert "acceptance criteria" in section.lower(), (
            "Regression #855: structural validation must check for acceptance criteria"
        )
        # Testing strategy check
        assert "testing strategy" in section.lower() or "test" in section.lower(), (
            "Regression #855: structural validation must check for testing strategy"
        )

    def test_step_5_5_positioned_between_step5_and_step6(self):
        """STEP 5.5 must appear after STEP 5 and before STEP 6 in the file."""
        content = IMPLEMENT_MD.read_text()
        assert "### STEP 5:" in content, "STEP 5 heading not found"
        assert "### STEP 5.5:" in content, "STEP 5.5 heading not found"
        assert "### STEP 6:" in content, "STEP 6 heading not found"
        pos_5 = content.index("### STEP 5:")
        pos_5_5 = content.index("### STEP 5.5:")
        pos_6 = content.index("### STEP 6:")
        assert pos_5 < pos_5_5 < pos_6, (
            "Regression #855: STEP 5.5 must appear between STEP 5 and STEP 6"
        )
