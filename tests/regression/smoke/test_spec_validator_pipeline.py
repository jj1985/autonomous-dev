#!/usr/bin/env python3
"""Smoke tests for spec-validator pipeline integration.

Validates that implement.md, implement-fix.md, and known_bypass_patterns.json
correctly reference the spec-validator agent at the expected pipeline steps.

Issue: #772
"""

import json
from pathlib import Path

import pytest

# Resolve project root (smoke -> regression -> tests -> repo root = parents[3])
PROJECT_ROOT = Path(__file__).resolve().parents[3]

IMPLEMENT_PATH = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"
IMPLEMENT_FIX_PATH = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-fix.md"
BYPASS_PATTERNS_PATH = (
    PROJECT_ROOT / "plugins" / "autonomous-dev" / "config" / "known_bypass_patterns.json"
)


class TestImplementMdSpecValidator:
    """Tests that implement.md includes STEP 8.5 with spec-validator."""

    def test_step_8_5_exists(self) -> None:
        """implement.md must contain a STEP 8.5 section."""
        content = IMPLEMENT_PATH.read_text()
        assert "STEP 8.5" in content, "STEP 8.5 not found in implement.md"

    def test_step_8_5_spec_blind_validation(self) -> None:
        """STEP 8.5 must be titled Spec-Blind Validation."""
        content = IMPLEMENT_PATH.read_text()
        assert "Spec-Blind Validation" in content

    def test_step_8_5_context_boundary_forbidden(self) -> None:
        """STEP 8.5 must include a context boundary FORBIDDEN list."""
        content = IMPLEMENT_PATH.read_text()
        # Find the STEP 8.5 section and verify FORBIDDEN appears within it
        idx_start = content.index("STEP 8.5")
        idx_end = content.index("STEP 9:", idx_start)
        step_8_5_section = content[idx_start:idx_end]
        assert "FORBIDDEN" in step_8_5_section, (
            "STEP 8.5 must include FORBIDDEN list for context boundary"
        )

    def test_step_8_5_forbids_implementer_output(self) -> None:
        """STEP 8.5 FORBIDDEN list must prohibit passing implementer output."""
        content = IMPLEMENT_PATH.read_text()
        idx_start = content.index("STEP 8.5")
        idx_end = content.index("STEP 9:", idx_start)
        step_8_5_section = content[idx_start:idx_end]
        assert "implementer output" in step_8_5_section.lower() or "Implementer output" in step_8_5_section

    def test_step_8_5_verdict_parsing(self) -> None:
        """STEP 8.5 must document SPEC-VALIDATOR-VERDICT parsing."""
        content = IMPLEMENT_PATH.read_text()
        assert "SPEC-VALIDATOR-VERDICT" in content

    def test_step_9_5_includes_spec_validator(self) -> None:
        """STEP 9.5 agent count gate must list spec-validator."""
        content = IMPLEMENT_PATH.read_text()
        idx_start = content.index("STEP 9.5")
        # Find the next STEP heading after 9.5
        idx_end = content.index("### STEP 9.7", idx_start)
        step_9_5_section = content[idx_start:idx_end]
        assert "spec-validator" in step_9_5_section, (
            "STEP 9.5 agent count gate must include spec-validator"
        )

    def test_step_12_updated_agent_count(self) -> None:
        """STEP 12 must reference updated agent count (8 default, 9 TDD)."""
        content = IMPLEMENT_PATH.read_text()
        idx_start = content.index("STEP 12")
        idx_end = content.index("### STEP 13", idx_start)
        step_12_section = content[idx_start:idx_end]
        # Must reference 8 agents (default) or spec-validator
        assert "8" in step_12_section or "spec-validator" in step_12_section, (
            "STEP 12 must reference updated agent count of 8 (default)"
        )

    def test_coordinator_forbidden_list_context_leakage(self) -> None:
        """Coordinator FORBIDDEN list must prohibit context leakage to spec-validator."""
        content = IMPLEMENT_PATH.read_text()
        # The forbidden list is near the top of the file
        forbidden_section_end = content.index("### Pipeline Progress Protocol")
        forbidden_section = content[:forbidden_section_end]
        assert "spec-validator" in forbidden_section, (
            "Coordinator FORBIDDEN list must mention spec-validator context boundary"
        )

    def test_light_pipeline_step_l3_5_exists(self) -> None:
        """Light pipeline must contain STEP L3.5."""
        content = IMPLEMENT_PATH.read_text()
        assert "STEP L3.5" in content or "L3.5" in content, (
            "Light pipeline must contain STEP L3.5 for spec-blind validation"
        )

    def test_light_pipeline_updated_agent_count(self) -> None:
        """Light pipeline description must reference 5 agents."""
        content = IMPLEMENT_PATH.read_text()
        idx_start = content.index("LIGHT PIPELINE")
        # The first paragraph describes agent count
        idx_end = content.index("### STEP L0", idx_start)
        light_intro = content[idx_start:idx_end]
        assert "5 agents" in light_intro, (
            f"Light pipeline must reference 5 agents. Found: {light_intro[:200]}"
        )


class TestImplementFixMdSpecValidator:
    """Tests that implement-fix.md includes STEP F3.5."""

    def test_step_f3_5_exists(self) -> None:
        """implement-fix.md must contain STEP F3.5."""
        content = IMPLEMENT_FIX_PATH.read_text()
        assert "STEP F3.5" in content or "F3.5" in content, (
            "implement-fix.md must contain STEP F3.5 for spec-blind validation"
        )

    def test_step_f3_5_context_boundary(self) -> None:
        """STEP F3.5 must include context boundary FORBIDDEN list."""
        content = IMPLEMENT_FIX_PATH.read_text()
        idx_start = content.index("F3.5")
        idx_end = content.index("STEP F4", idx_start)
        step_f3_5_section = content[idx_start:idx_end]
        assert "FORBIDDEN" in step_f3_5_section, (
            "STEP F3.5 must include FORBIDDEN list for context boundary"
        )


class TestKnownBypassPatternsSpecValidator:
    """Tests that known_bypass_patterns.json includes spec-validator."""

    def test_full_pipeline_includes_spec_validator(self) -> None:
        """full_pipeline required_agents must include spec-validator."""
        data = json.loads(BYPASS_PATTERNS_PATH.read_text())
        agents = data["expected_end_states"]["full_pipeline"]["required_agents"]
        assert "spec-validator" in agents

    def test_batch_issues_includes_spec_validator(self) -> None:
        """batch-issues required_agents must include spec-validator."""
        data = json.loads(BYPASS_PATTERNS_PATH.read_text())
        agents = data["expected_end_states"]["batch-issues"]["required_agents"]
        assert "spec-validator" in agents

    def test_batch_includes_spec_validator(self) -> None:
        """batch required_agents must include spec-validator."""
        data = json.loads(BYPASS_PATTERNS_PATH.read_text())
        agents = data["expected_end_states"]["batch"]["required_agents"]
        assert "spec-validator" in agents
