"""
Regression tests for Issue #206: Test gate bypass.

Bug: Model sees failing tests (e.g., "45/56 passing, 80%"), declares it a
"solid foundation", and skips to STEP 10 (validation) without fixing failures.

Fix: HARD GATE language in implement.md STEP 8 with explicit FORBIDDEN behaviors
and two allowed resolutions (fix, adjust).

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


class TestIssue206TestGateHardGate:
    """Regression: STEP 8 must enforce 0 test failures as HARD GATE."""

    def test_implement_md_step8_has_hard_gate(self):
        """STEP 8 must contain HARD GATE language."""
        content = (PLUGIN_DIR / "commands" / "implement.md").read_text()
        # Split at STEP 8 heading (Implementer + Test Gate), take content before STEP 9
        step8_section = content.split("### STEP 8:")[1].split("### STEP 9")[0]
        assert "HARD GATE" in step8_section, "Regression #206: STEP 8 must be a HARD GATE"

    def test_implement_md_step8_requires_zero_failures(self):
        """STEP 8 must explicitly require 0 failures."""
        content = (PLUGIN_DIR / "commands" / "implement.md").read_text()
        step8_section = content.split("### STEP 8:")[1].split("### STEP 9")[0]
        assert "0 failures" in step8_section, "Regression #206: must require 0 failures"

    def test_implement_md_step8_has_resolutions(self):
        """STEP 8 must offer fix/adjust resolutions and explicitly forbid skip.

        Updated by Issue #364 (testing pipeline redesign): 'Skip it' was removed
        as a resolution option. Skip is now explicitly FORBIDDEN via No New Skips
        HARD GATE. Issue #206's core requirement (prevent test gate bypass) is
        still enforced — just without listing skip as an option.
        """
        content = (PLUGIN_DIR / "commands" / "implement.md").read_text()
        step8_section = content.split("### STEP 8:")[1].split("### STEP 9")[0]
        assert "Fix it" in step8_section, "Regression #206: must offer 'Fix it' resolution"
        assert "Adjust it" in step8_section, "Regression #206: must offer 'Adjust it' resolution"
        assert "skip" in step8_section.lower(), "Regression #206: must reference skip (as forbidden)"

    def test_implement_md_step8_blocks_step10(self):
        """STEP 8 must explicitly block progression to STEP 10."""
        content = (PLUGIN_DIR / "commands" / "implement.md").read_text()
        step8_section = content.split("### STEP 8:")[1].split("### STEP 9")[0]
        assert "Do NOT proceed to STEP 10" in step8_section, (
            "Regression #206: must explicitly block STEP 10 with failures"
        )
