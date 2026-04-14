"""
Regression tests for Pipeline Verification Protocol gates (#854-#858).

These tests verify the enforcement infrastructure introduced by issues #854-#858
exists in the relevant commands and agents files and would break if removed.

Issues covered:
    #854 - STEP 5.5 Plan Validation Gate in implement.md
    #855 - Root Cause Analysis HARD GATE in implementer.md
    #856 - Root Cause Analysis Output Gate in implement-fix.md
    #857 - debugging-workflow skill in implementer.md frontmatter
    #858 - Plan-Implementation Alignment gate in implement.md
          STEP L2.5 Plan Structural Validation in implement.md (light pipeline)
          Step 6 issue creation enforcement in plan.md
"""

from pathlib import Path

# Portable project root detection
_current = Path(__file__).resolve()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

PLUGIN_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev"


class TestVerificationProtocolGates:
    """Regression: Pipeline Verification Protocol gates must be present (#854-#858)."""

    def test_step_5_5_plan_validation_gate(self):
        """implement.md must contain STEP 5.5 Plan Validation Gate as a HARD GATE."""
        content = (PLUGIN_DIR / "commands" / "implement.md").read_text()
        assert "STEP 5.5" in content, (
            "Regression #854-#858: implement.md must contain STEP 5.5"
        )
        assert "Plan Validation Gate" in content, (
            "Regression #854-#858: implement.md must contain 'Plan Validation Gate'"
        )
        assert "HARD GATE" in content, (
            "Regression #854-#858: implement.md must contain 'HARD GATE'"
        )

    def test_root_cause_hard_gate_in_implementer(self):
        """implementer.md must contain Root Cause Analysis as a HARD GATE."""
        content = (PLUGIN_DIR / "agents" / "implementer.md").read_text()
        assert "Root Cause Analysis" in content, (
            "Regression #854-#858: implementer.md must contain 'Root Cause Analysis'"
        )
        assert "HARD GATE" in content, (
            "Regression #854-#858: implementer.md must contain 'HARD GATE'"
        )

    def test_root_cause_output_gate_in_implement_fix(self):
        """implement-fix.md must contain a Root Cause Analysis Output Gate as a HARD GATE."""
        content = (PLUGIN_DIR / "commands" / "implement-fix.md").read_text()
        assert "Root Cause Analysis Output Gate" in content, (
            "Regression #854-#858: implement-fix.md must contain 'Root Cause Analysis Output Gate'"
        )
        assert "HARD GATE" in content, (
            "Regression #854-#858: implement-fix.md must contain 'HARD GATE'"
        )

    def test_debugging_workflow_in_implementer_skills(self):
        """implementer.md frontmatter skills line must include debugging-workflow."""
        content = (PLUGIN_DIR / "agents" / "implementer.md").read_text()
        # Find the skills frontmatter line and confirm debugging-workflow is listed
        skills_line = next(
            (line for line in content.splitlines() if line.startswith("skills:")),
            None,
        )
        assert skills_line is not None, (
            "Regression #854-#858: implementer.md must have a 'skills:' frontmatter line"
        )
        assert "debugging-workflow" in skills_line, (
            "Regression #854-#858: implementer.md skills frontmatter must include 'debugging-workflow'"
        )

    def test_plan_implementation_alignment_gate(self):
        """implement.md must contain a Plan-Implementation Alignment gate."""
        content = (PLUGIN_DIR / "commands" / "implement.md").read_text()
        assert "Plan-Implementation Alignment" in content, (
            "Regression #854-#858: implement.md must contain 'Plan-Implementation Alignment'"
        )

    def test_light_pipeline_l2_5_validation(self):
        """implement.md must contain STEP L2.5 Plan Structural Validation as a HARD GATE."""
        content = (PLUGIN_DIR / "commands" / "implement.md").read_text()
        assert "STEP L2.5" in content, (
            "Regression #854-#858: implement.md must contain 'STEP L2.5'"
        )
        assert "Plan Structural Validation" in content, (
            "Regression #854-#858: implement.md must contain 'Plan Structural Validation'"
        )
        assert "HARD GATE" in content, (
            "Regression #854-#858: implement.md must contain 'HARD GATE'"
        )

    def test_plan_step_6_issue_creation_enforcement(self):
        """plan.md must enforce issue creation at Step 6 with HARD GATE or FORBIDDEN."""
        content = (PLUGIN_DIR / "commands" / "plan.md").read_text()
        # Locate the Step 6 section
        assert "STEP 6" in content, (
            "Regression #854-#858: plan.md must contain a STEP 6 section"
        )
        step6_section = content.split("STEP 6")[1].split("STEP 7")[0]
        assert "issue" in step6_section.lower(), (
            "Regression #854-#858: plan.md STEP 6 must reference issue creation"
        )
        assert "HARD GATE" in step6_section or "FORBIDDEN" in step6_section, (
            "Regression #854-#858: plan.md STEP 6 must contain HARD GATE or FORBIDDEN enforcement"
        )
