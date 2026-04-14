"""
Regression tests for Issue #857: Plan-implementation alignment check after STEP 8 test gate.

Bug: The implementer could silently work on different files than the planner intended,
causing scope creep or under-delivery with no visible signal.

Fix: Added OUTPUT VALIDATION GATE: Plan-Implementation Alignment section in implement.md
between the Regression Test Requirement HARD GATE and STEP 8.5.

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


class TestIssue857PlanAlignmentGate:
    """Regression: implement.md must have a plan-implementation alignment gate."""

    def test_plan_alignment_gate_exists(self):
        """implement.md must have the Plan-Implementation Alignment gate section header."""
        content = IMPLEMENT_MD.read_text()
        assert "Plan-Implementation Alignment" in content, (
            "Regression #857: implement.md must contain Plan-Implementation Alignment gate"
        )

    def test_plan_alignment_gate_has_warning_language(self):
        """The alignment gate must use WARNING language for divergent files."""
        content = IMPLEMENT_MD.read_text()
        # Isolate the section containing the gate
        assert "WARNING" in content, (
            "Regression #857: alignment gate must include WARNING verdict language"
        )
        # Check specifically in the alignment section
        section_start = content.find("Plan-Implementation Alignment")
        assert section_start != -1, "Alignment gate section not found"
        section = content[section_start:section_start + 2000]
        assert "WARNING" in section, (
            "Regression #857: WARNING must appear within the alignment gate section"
        )

    def test_plan_alignment_gate_has_block_threshold(self):
        """The alignment gate must specify the 50% block threshold."""
        content = IMPLEMENT_MD.read_text()
        section_start = content.find("Plan-Implementation Alignment")
        assert section_start != -1, "Alignment gate section not found"
        section = content[section_start:section_start + 2000]
        assert "50%" in section, (
            "Regression #857: alignment gate must specify 50% divergence threshold for BLOCK"
        )

    def test_plan_alignment_gate_excludes_test_files(self):
        """The alignment gate must explicitly exclude test files from comparison."""
        content = IMPLEMENT_MD.read_text()
        section_start = content.find("Plan-Implementation Alignment")
        assert section_start != -1, "Alignment gate section not found"
        section = content[section_start:section_start + 2000]
        # Must mention exclusion of test files and/or docs
        assert "tests/**" in section or "test files" in section.lower(), (
            "Regression #857: alignment gate must exclude test files from comparison"
        )

    def test_plan_alignment_gate_ordered_before_step_85(self):
        """The alignment gate must appear before STEP 8.5 in the document."""
        content = IMPLEMENT_MD.read_text()
        alignment_pos = content.find("Plan-Implementation Alignment")
        step_85_pos = content.find("### STEP 8.5:")
        assert alignment_pos != -1, "Alignment gate section not found"
        assert step_85_pos != -1, "STEP 8.5 section not found"
        assert alignment_pos < step_85_pos, (
            "Regression #857: Plan-Implementation Alignment gate must appear before STEP 8.5"
        )

    def test_plan_alignment_gate_has_forbidden_list(self):
        """The alignment gate must have a FORBIDDEN list."""
        content = IMPLEMENT_MD.read_text()
        section_start = content.find("Plan-Implementation Alignment")
        assert section_start != -1, "Alignment gate section not found"
        # Find STEP 8.5 as the end boundary
        step_85_pos = content.find("### STEP 8.5:")
        section = content[section_start:step_85_pos]
        assert "FORBIDDEN" in section, (
            "Regression #857: alignment gate must have a FORBIDDEN list"
        )

    def test_plan_alignment_gate_has_output_format(self):
        """The alignment gate must specify an output format with Verdict line."""
        content = IMPLEMENT_MD.read_text()
        section_start = content.find("Plan-Implementation Alignment")
        assert section_start != -1, "Alignment gate section not found"
        step_85_pos = content.find("### STEP 8.5:")
        section = content[section_start:step_85_pos]
        assert "Verdict" in section, (
            "Regression #857: alignment gate output format must include a Verdict line"
        )
        assert "PASS" in section, (
            "Regression #857: alignment gate must include PASS verdict"
        )
        assert "BLOCKED" in section, (
            "Regression #857: alignment gate must include BLOCKED verdict"
        )
