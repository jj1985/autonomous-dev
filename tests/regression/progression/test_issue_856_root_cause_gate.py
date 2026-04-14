"""
Regression tests for Issue #856: Root cause analysis HARD GATE for --fix pipeline.

Bug: The --fix pipeline had no requirement for root cause analysis. The implementer
could fix a symptom without identifying the underlying cause, leading to recurrence.

Fix: Added HARD GATE: Root Cause Analysis for Bug Fixes in implementer.md requiring
a ## Root Cause Analysis section with: root cause statement, mechanism chain, 5 Whys
(min 3 levels), and root cause category. Added coordinator output gate in STEP F3 of
implement-fix.md that checks for the section and re-invokes once if absent, then blocks.

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
IMPLEMENTER_MD = PLUGIN_DIR / "agents" / "implementer.md"
IMPLEMENT_FIX_MD = PLUGIN_DIR / "commands" / "implement-fix.md"


def _get_root_cause_gate_section(content: str) -> str:
    """Extract the Root Cause Analysis HARD GATE section from implementer.md."""
    marker = "## HARD GATE: Root Cause Analysis"
    if marker not in content:
        return ""
    start = content.index(marker)
    # Find next ## section
    next_section = content.find("\n## ", start + len(marker))
    if next_section != -1:
        return content[start:next_section]
    return content[start:]


def _get_step_f3_section(content: str) -> str:
    """Extract STEP F3 and the text following it (including the output gate) from implement-fix.md."""
    marker = "### STEP F3:"
    if marker not in content:
        return ""
    start = content.index(marker)
    # Find STEP F3.5
    next_step = content.find("### STEP F3.5:", start + len(marker))
    if next_step != -1:
        return content[start:next_step]
    return content[start:]


class TestIssue856RootCauseGate:
    """Regression: implementer must require root cause analysis in fix mode."""

    def test_implementer_has_root_cause_hard_gate(self):
        """implementer.md must have a HARD GATE: Root Cause Analysis section."""
        content = IMPLEMENTER_MD.read_text()
        assert "## HARD GATE: Root Cause Analysis" in content, (
            "Regression #856: implementer.md must have "
            "'## HARD GATE: Root Cause Analysis' section"
        )

    def test_implementer_has_debugging_workflow_skill(self):
        """implementer.md frontmatter must list debugging-workflow in skills."""
        content = IMPLEMENTER_MD.read_text()
        # Check frontmatter section (before first ---)
        lines = content.split("\n")
        in_frontmatter = False
        frontmatter_lines = []
        dash_count = 0
        for line in lines:
            if line.strip() == "---":
                dash_count += 1
                if dash_count == 1:
                    in_frontmatter = True
                    continue
                elif dash_count == 2:
                    break
            if in_frontmatter:
                frontmatter_lines.append(line)
        frontmatter = "\n".join(frontmatter_lines)
        assert "debugging-workflow" in frontmatter, (
            "Regression #856: implementer.md frontmatter skills must include 'debugging-workflow'"
        )

    def test_implementer_root_cause_forbidden_list(self):
        """Root Cause Analysis HARD GATE must have a FORBIDDEN list with 4 items."""
        content = IMPLEMENTER_MD.read_text()
        section = _get_root_cause_gate_section(content)
        assert section, "Regression #856: ## HARD GATE: Root Cause Analysis section not found"
        assert "FORBIDDEN" in section, (
            "Regression #856: Root Cause Analysis gate must have a FORBIDDEN list"
        )
        # 1. No tautological 5 Whys
        assert "tautological" in section.lower(), (
            "Regression #856: FORBIDDEN list must prohibit tautological 5 Whys"
        )
        # 2. No claiming "obvious" without analysis
        assert "obvious" in section.lower(), (
            "Regression #856: FORBIDDEN list must prohibit claiming the bug is 'obvious'"
        )
        # 3. No fixing symptom without root cause
        assert "symptom" in section.lower(), (
            "Regression #856: FORBIDDEN list must prohibit fixing symptom without identifying cause"
        )
        # 4. Must not omit the section
        assert "Root Cause Analysis" in section and "omit" in section.lower(), (
            "Regression #856: FORBIDDEN list must prohibit omitting the Root Cause Analysis section"
        )

    def test_fix_pipeline_requires_root_cause_output(self):
        """implement-fix.md STEP F3 implementer prompt must require ## Root Cause Analysis output."""
        content = IMPLEMENT_FIX_MD.read_text()
        step_f3 = _get_step_f3_section(content)
        assert step_f3, "Regression #856: STEP F3 section not found in implement-fix.md"
        assert "## Root Cause Analysis" in step_f3, (
            "Regression #856: STEP F3 implementer prompt must require '## Root Cause Analysis' output"
        )
        # Must mention the 5 Whys requirement in the prompt
        assert "5 Whys" in step_f3 or "5 whys" in step_f3.lower(), (
            "Regression #856: STEP F3 implementer prompt must mention '5 Whys' methodology"
        )

    def test_fix_pipeline_has_root_cause_output_gate(self):
        """implement-fix.md must have a Root Cause Analysis Output Gate after STEP F3."""
        content = IMPLEMENT_FIX_MD.read_text()
        assert "Root Cause Analysis Output Gate" in content, (
            "Regression #856: implement-fix.md must have a 'Root Cause Analysis Output Gate' section"
        )

    def test_fix_pipeline_output_gate_has_retry_then_block(self):
        """The Root Cause Analysis Output Gate must describe retry-once then block logic."""
        content = IMPLEMENT_FIX_MD.read_text()
        # Find the gate section
        marker = "Root Cause Analysis Output Gate"
        assert marker in content, (
            "Regression #856: Root Cause Analysis Output Gate not found in implement-fix.md"
        )
        gate_start = content.index(marker)
        # Extract to end of nearby section (next ### or ## heading)
        gate_end = content.find("\n### STEP F3.5:", gate_start)
        if gate_end == -1:
            gate_end = content.find("\n## Step F4", gate_start)
        gate_section = content[gate_start:gate_end] if gate_end != -1 else content[gate_start:]

        # Must describe re-invoke once (retry)
        assert "re-invoke" in gate_section.lower() or "re-invok" in gate_section.lower(), (
            "Regression #856: Output gate must describe re-invoking the implementer once if section is absent"
        )
        # Must describe blocking if still missing after retry
        assert "block" in gate_section.lower(), (
            "Regression #856: Output gate must BLOCK if Root Cause Analysis is still absent after retry"
        )
        # Must explicitly check for the ## Root Cause Analysis string
        assert "## Root Cause Analysis" in gate_section, (
            "Regression #856: Output gate must check for the literal '## Root Cause Analysis' string"
        )
