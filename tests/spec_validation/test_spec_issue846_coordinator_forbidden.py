"""Spec validation tests for Issue #846: Coordinator FORBIDDEN LIST in implement-fix.md.

Validates acceptance criteria:
1. Top-level coordinator role section exists before step definitions
2. Post-agent-completion window covered with permitted actions
3. At least 4 FORBIDDEN items covering required topics
4. New regression tests pass
5. Existing tests pass
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_FIX_MD = PROJECT_ROOT / "plugins/autonomous-dev/commands/implement-fix.md"


@pytest.fixture(scope="module")
def content() -> str:
    """Read implement-fix.md content."""
    assert IMPLEMENT_FIX_MD.exists(), f"implement-fix.md not found at {IMPLEMENT_FIX_MD}"
    return IMPLEMENT_FIX_MD.read_text()


class TestSpecCriterion1TopLevelSection:
    """AC1: Top-level coordinator role section before any step definitions."""

    def test_spec_846_1_coordinator_section_before_steps(self, content: str):
        """The coordinator role section MUST appear before STEP F1."""
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        assert coord_pos != -1, "No 'Coordinator Role' section found in implement-fix.md"
        assert step_pos != -1, "No 'STEP F1' found in implement-fix.md"
        assert coord_pos < step_pos, (
            f"Coordinator Role section (pos {coord_pos}) must appear before "
            f"STEP F1 (pos {step_pos})"
        )

    def test_spec_846_1b_prohibits_direct_file_operations(self, content: str):
        """The section must explicitly prohibit writing, editing, or modifying project files."""
        # Extract text between Coordinator Role and STEP F1
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        section = content[coord_pos:step_pos]

        assert "write" in section.lower(), "Section must mention 'write' prohibition"
        assert "edit" in section.lower(), "Section must mention 'edit' prohibition"
        assert "modify" in section.lower(), "Section must mention 'modify' prohibition"


class TestSpecCriterion2PostCompletionWindow:
    """AC2: Post-agent-completion window with permitted actions."""

    def test_spec_846_2_post_completion_prohibition(self, content: str):
        """The prohibition must cover the post-agent-completion window."""
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        section = content[coord_pos:step_pos]

        # Must reference post-agent/post-completion behavior
        assert "after agents complete" in section.lower() or "post-agent" in section.lower(), (
            "Section must explicitly cover the post-agent-completion window"
        )

    def test_spec_846_2b_permitted_actions_summary(self, content: str):
        """Summary output must be listed as a permitted post-agent action."""
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        section = content[coord_pos:step_pos]

        assert "summary" in section.lower(), (
            "Summary output must be listed as a permitted post-agent action"
        )

    def test_spec_846_2c_permitted_actions_git(self, content: str):
        """Git operations must be listed as a permitted post-agent action."""
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        section = content[coord_pos:step_pos]

        assert "git" in section.lower(), (
            "Git operations must be listed as a permitted post-agent action"
        )

    def test_spec_846_2d_permitted_actions_step_f5(self, content: str):
        """Launching STEP F5 must be listed as a permitted post-agent action."""
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        section = content[coord_pos:step_pos]

        assert "step f5" in section.lower() or "STEP F5" in section, (
            "Launching STEP F5 must be listed as a permitted post-agent action"
        )


class TestSpecCriterion3ForbiddenItems:
    """AC3: At least 4 FORBIDDEN items covering required topics."""

    def test_spec_846_3_minimum_four_forbidden_items(self, content: str):
        """The coordinator section must contain at least 4 FORBIDDEN items."""
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        section = content[coord_pos:step_pos]

        # Count lines starting with the FORBIDDEN marker pattern
        forbidden_lines = [
            line.strip()
            for line in section.split("\n")
            if "MUST NOT" in line and line.strip().startswith("-")
        ]
        assert len(forbidden_lines) >= 4, (
            f"Expected at least 4 FORBIDDEN items with 'MUST NOT', found {len(forbidden_lines)}: "
            f"{forbidden_lines}"
        )

    def test_spec_846_3a_no_direct_file_writes(self, content: str):
        """FORBIDDEN items must cover: no direct file writes."""
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        section = content[coord_pos:step_pos].lower()

        assert "write" in section and "must not" in section, (
            "FORBIDDEN items must cover direct file writes"
        )

    def test_spec_846_3b_no_skipping_steps(self, content: str):
        """FORBIDDEN items must cover: no skipping steps."""
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        section = content[coord_pos:step_pos].lower()

        assert "skip" in section and "step" in section, (
            "FORBIDDEN items must cover skipping steps"
        )

    def test_spec_846_3c_no_agent_substitution(self, content: str):
        """FORBIDDEN items must cover: no agent substitution."""
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        section = content[coord_pos:step_pos].lower()

        # Should prohibit doing agent work or substituting for agents
        has_substitution_prohibition = (
            "substitute" in section
            or "agent's work" in section
            or "do the work itself" in section
        )
        assert has_substitution_prohibition, (
            "FORBIDDEN items must cover agent substitution (coordinator doing agent work)"
        )

    def test_spec_846_3d_no_output_summarization(self, content: str):
        """FORBIDDEN items must cover: no output summarization."""
        coord_pos = content.find("Coordinator Role")
        step_pos = content.find("STEP F1")
        section = content[coord_pos:step_pos].lower()

        has_summarization_prohibition = (
            "summarize" in section
            or "paraphrase" in section
            or "condense" in section
        )
        assert has_summarization_prohibition, (
            "FORBIDDEN items must cover output summarization"
        )
