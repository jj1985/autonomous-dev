"""Unit tests for prompt quality rules and agent file inspection (Issue #842).

Tests two things:
1. TestPromptQualityRules - unit tests for the rules library
2. TestAgentFileQuality - parametrized tests over all agent .md files
"""
import sys
from pathlib import Path

import pytest

# Portable project root detection
_test_file = Path(__file__).resolve()
# tests/unit/test_prompt_quality.py -> parents[2] = repo root
PROJECT_ROOT = _test_file.parents[2]

# Add lib to path for imports
_lib_path = PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"
if str(_lib_path) not in sys.path:
    sys.path.insert(0, str(_lib_path))

from prompt_quality_rules import (
    CONSTRAINT_DENSITY_THRESHOLD,
    check_all,
    check_casual_register,
    check_constraint_density,
    check_persona,
)

# Discover agent files (excluding archived/)
AGENTS_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev" / "agents"
AGENT_FILES = sorted(
    p for p in AGENTS_DIR.glob("*.md")
    if "archived" not in str(p)
)

# Casual register threshold per file: some usage in examples/comments is acceptable
CASUAL_REGISTER_FILE_THRESHOLD = 5


class TestPromptQualityRules:
    """Unit tests for the prompt_quality_rules library."""

    # -- Persona checks --

    def test_persona_catches_banned_openers(self) -> None:
        """Banned persona patterns like 'You are an expert' are detected."""
        content = "You are an expert Python developer.\nDo the thing."
        violations = check_persona(content)
        assert len(violations) >= 1
        assert "expert" in violations[0].lower() or "persona" in violations[0].lower()

    def test_persona_catches_senior(self) -> None:
        content = "You are a senior engineer with 20 years experience."
        violations = check_persona(content)
        assert len(violations) >= 1

    def test_persona_catches_world_class(self) -> None:
        content = "You are a world-class architect."
        violations = check_persona(content)
        assert len(violations) >= 1

    def test_persona_catches_world_class_space(self) -> None:
        content = "You are a world class designer."
        violations = check_persona(content)
        assert len(violations) >= 1

    def test_persona_catches_renowned(self) -> None:
        content = "\nYou are a renowned scientist.\n"
        violations = check_persona(content)
        assert len(violations) >= 1

    def test_persona_allows_role_assignment(self) -> None:
        """Legitimate role assignments like 'You are the **implementer** agent' pass."""
        content = "You are the **implementer** agent.\nImplement the plan."
        violations = check_persona(content)
        assert len(violations) == 0

    def test_persona_allows_plain_role(self) -> None:
        content = "You are the reviewer.\nReview the code."
        violations = check_persona(content)
        assert len(violations) == 0

    def test_persona_allows_normal_text(self) -> None:
        content = "## Mission\n\nImplement production-quality code."
        violations = check_persona(content)
        assert len(violations) == 0

    # -- Casual register checks --

    def test_casual_register_catches_make_sure(self) -> None:
        content = "Make sure the tests pass."
        violations = check_casual_register(content)
        assert len(violations) >= 1
        assert "make sure" in violations[0].lower()

    def test_casual_register_catches_try_to(self) -> None:
        content = "Try to keep the code clean."
        violations = check_casual_register(content)
        assert len(violations) >= 1

    def test_casual_register_catches_feel_free(self) -> None:
        content = "Feel free to refactor."
        violations = check_casual_register(content)
        assert len(violations) >= 1

    def test_casual_register_catches_you_should(self) -> None:
        content = "You should test edge cases."
        violations = check_casual_register(content)
        assert len(violations) >= 1

    def test_casual_register_catches_check_for(self) -> None:
        content = "Check for missing imports."
        violations = check_casual_register(content)
        assert len(violations) >= 1

    def test_casual_register_catches_look_for(self) -> None:
        content = "Look for patterns in the codebase."
        violations = check_casual_register(content)
        assert len(violations) >= 1

    def test_casual_register_allows_formal(self) -> None:
        """Formal directives (MUST, REQUIRED) are not flagged."""
        content = (
            "You MUST write tests.\n"
            "REQUIRED: All public APIs have type hints.\n"
            "FORBIDDEN: bare except clauses."
        )
        violations = check_casual_register(content)
        assert len(violations) == 0

    def test_casual_register_reports_line_numbers(self) -> None:
        content = "Line one.\nLine two.\nMake sure it works.\nLine four."
        violations = check_casual_register(content)
        assert len(violations) >= 1
        assert "Line 3" in violations[0]

    # -- Constraint density checks --

    def test_constraint_density_flags_oversized(self) -> None:
        """Sections with 9+ bullet items are flagged (threshold=8)."""
        lines = ["## Rules"]
        for i in range(9):
            lines.append(f"- Rule {i + 1}")
        content = "\n".join(lines)
        violations = check_constraint_density(content)
        assert len(violations) >= 1
        assert "9 bullet items" in violations[0]

    def test_constraint_density_allows_normal(self) -> None:
        """Sections with 6 items pass (under threshold of 8)."""
        lines = ["## Rules"]
        for i in range(6):
            lines.append(f"- Rule {i + 1}")
        content = "\n".join(lines)
        violations = check_constraint_density(content)
        assert len(violations) == 0

    def test_constraint_density_exactly_at_threshold(self) -> None:
        """Exactly at threshold (8) should pass."""
        lines = ["## Rules"]
        for i in range(8):
            lines.append(f"- Rule {i + 1}")
        content = "\n".join(lines)
        violations = check_constraint_density(content)
        assert len(violations) == 0

    def test_constraint_density_custom_threshold(self) -> None:
        """Custom threshold overrides default."""
        lines = ["## Rules"]
        for i in range(4):
            lines.append(f"- Rule {i + 1}")
        content = "\n".join(lines)
        # With threshold=3, 4 items should flag
        violations = check_constraint_density(content, threshold=3)
        assert len(violations) >= 1

    def test_constraint_density_multiple_sections(self) -> None:
        """Each section is checked independently."""
        lines = ["## Section A"]
        for i in range(5):
            lines.append(f"- Item {i}")
        lines.append("## Section B")
        for i in range(10):
            lines.append(f"- Item {i}")
        content = "\n".join(lines)
        violations = check_constraint_density(content)
        assert len(violations) == 1
        assert "Section B" in violations[0]

    def test_constraint_density_star_bullets(self) -> None:
        """Star bullets (* ) are also counted."""
        lines = ["## Rules"]
        for i in range(9):
            lines.append(f"* Rule {i + 1}")
        content = "\n".join(lines)
        violations = check_constraint_density(content)
        assert len(violations) >= 1

    # -- check_all --

    def test_check_all_combines_violations(self) -> None:
        """check_all returns violations from all checks."""
        content = (
            "You are an expert coder.\n"
            "Make sure you test.\n"
            "## Rules\n"
        )
        # Add 10 bullets to trigger constraint density
        for i in range(10):
            content += f"- Rule {i}\n"
        violations = check_all(content)
        # Should have persona + casual register + constraint density
        assert len(violations) >= 3

    def test_check_all_empty_on_clean_content(self) -> None:
        """Clean content returns no violations."""
        content = (
            "You are the **reviewer** agent.\n\n"
            "## Mission\n\n"
            "Review code changes for quality.\n\n"
            "## Requirements\n\n"
            "- MUST check type hints\n"
            "- MUST verify error handling\n"
        )
        violations = check_all(content)
        assert len(violations) == 0


class TestAgentFileQuality:
    """Parametrized tests over all agent .md files."""

    @pytest.mark.parametrize(
        "agent_file",
        AGENT_FILES,
        ids=[p.stem for p in AGENT_FILES],
    )
    def test_no_banned_personas(self, agent_file: Path) -> None:
        """Agent files MUST NOT contain banned persona openers."""
        content = agent_file.read_text(encoding="utf-8")
        violations = check_persona(content)
        assert violations == [], (
            f"{agent_file.name} has banned persona patterns:\n"
            + "\n".join(violations)
        )

    @pytest.mark.parametrize(
        "agent_file",
        AGENT_FILES,
        ids=[p.stem for p in AGENT_FILES],
    )
    def test_no_excessive_casual_register(self, agent_file: Path) -> None:
        """Agent files MUST NOT exceed casual register threshold (5 per file)."""
        content = agent_file.read_text(encoding="utf-8")
        violations = check_casual_register(content)
        assert len(violations) <= CASUAL_REGISTER_FILE_THRESHOLD, (
            f"{agent_file.name} has {len(violations)} casual register phrases "
            f"(threshold: {CASUAL_REGISTER_FILE_THRESHOLD}):\n"
            + "\n".join(violations)
        )

    @pytest.mark.parametrize(
        "agent_file",
        AGENT_FILES,
        ids=[p.stem for p in AGENT_FILES],
    )
    def test_no_oversized_constraint_sections(self, agent_file: Path) -> None:
        """Agent files MUST NOT have constraint sections exceeding density threshold.

        Uses a higher threshold (35) for existing agent file validation since
        many HARD GATE sections legitimately contain extensive bullet lists.
        The stricter default (8) is enforced at write-time by the hook to
        prevent NEW oversized sections from being added.
        """
        # Existing agent files have sections up to 33 bullets (HARD GATE, Process, etc.)
        # The hook enforces stricter threshold at write-time for new content.
        AGENT_FILE_THRESHOLD = 35
        content = agent_file.read_text(encoding="utf-8")
        violations = check_constraint_density(content, threshold=AGENT_FILE_THRESHOLD)
        assert violations == [], (
            f"{agent_file.name} has oversized constraint sections:\n"
            + "\n".join(violations)
        )
