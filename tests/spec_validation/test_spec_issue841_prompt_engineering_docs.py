"""Spec validation tests for Issue #841: Prompt engineering documentation and skill.

Validates acceptance criteria:
1. docs/PROMPT-ENGINEERING.md exists with constraint budget section
2. docs/PROMPT-ENGINEERING.md has register shifting section
3. docs/PROMPT-ENGINEERING.md has persona anti-pattern section
4. docs/PROMPT-ENGINEERING.md has self-refine loops section
5. docs/PROMPT-ENGINEERING.md has HARD GATE patterns section
6. docs/PROMPT-ENGINEERING.md cites MOSAIC, PRISM, Self-Refine
7. skills/prompt-engineering/SKILL.md has valid TRIGGER frontmatter
8. skills/prompt-engineering/SKILL.md has DO NOT TRIGGER frontmatter
9. docs/model-behavior-notes.md has "Prompt Word Selection" section
10. docs/ARCHITECTURE-OVERVIEW.md lists prompt-engineering skill
11. CLAUDE.md component counts updated for new skill
12. Cross-references between files resolve to existing files
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
SKILLS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "skills"
PROMPT_ENG_DOC = DOCS_DIR / "PROMPT-ENGINEERING.md"
SKILL_MD = SKILLS_DIR / "prompt-engineering" / "SKILL.md"
MODEL_BEHAVIOR_DOC = DOCS_DIR / "model-behavior-notes.md"
ARCH_OVERVIEW_DOC = DOCS_DIR / "ARCHITECTURE-OVERVIEW.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


# ── Criterion 1: Constraint budget section ──────────────────────────────────


def test_spec_issue841_01_constraint_budget_section():
    """PROMPT-ENGINEERING.md must exist and contain a constraint budget section."""
    assert PROMPT_ENG_DOC.exists(), f"Missing file: {PROMPT_ENG_DOC}"
    content = PROMPT_ENG_DOC.read_text()
    assert "## Constraint Budget" in content, (
        "PROMPT-ENGINEERING.md must have a '## Constraint Budget' section"
    )


# ── Criterion 2: Register shifting section ──────────────────────────────────


def test_spec_issue841_02_register_shifting_section():
    """PROMPT-ENGINEERING.md must contain a register shifting section."""
    content = PROMPT_ENG_DOC.read_text()
    assert "## Register Shifting" in content, (
        "PROMPT-ENGINEERING.md must have a '## Register Shifting' section"
    )


# ── Criterion 3: Persona anti-pattern section ───────────────────────────────


def test_spec_issue841_03_persona_anti_pattern_section():
    """PROMPT-ENGINEERING.md must contain a persona anti-pattern section."""
    content = PROMPT_ENG_DOC.read_text()
    assert "Persona Anti-Pattern" in content, (
        "PROMPT-ENGINEERING.md must have a persona anti-pattern section"
    )


# ── Criterion 4: Self-refine loops section ───────────────────────────────────


def test_spec_issue841_04_self_refine_section():
    """PROMPT-ENGINEERING.md must contain a self-refine loop section."""
    content = PROMPT_ENG_DOC.read_text()
    assert "Self-Refine" in content, (
        "PROMPT-ENGINEERING.md must have a self-refine section"
    )


# ── Criterion 5: HARD GATE patterns section ─────────────────────────────────


def test_spec_issue841_05_hard_gate_patterns_section():
    """PROMPT-ENGINEERING.md must contain a HARD GATE patterns section."""
    content = PROMPT_ENG_DOC.read_text()
    assert "HARD GATE" in content, (
        "PROMPT-ENGINEERING.md must have a HARD GATE patterns section"
    )


# ── Criterion 6: MOSAIC citation ────────────────────────────────────────────


def test_spec_issue841_06_mosaic_citation():
    """PROMPT-ENGINEERING.md must cite MOSAIC research."""
    content = PROMPT_ENG_DOC.read_text()
    assert "MOSAIC" in content, "PROMPT-ENGINEERING.md must cite MOSAIC"


# ── Criterion 7: PRISM citation ─────────────────────────────────────────────


def test_spec_issue841_07_prism_citation():
    """PROMPT-ENGINEERING.md must cite PRISM research."""
    content = PROMPT_ENG_DOC.read_text()
    assert "PRISM" in content, "PROMPT-ENGINEERING.md must cite PRISM"


# ── Criterion 8: Self-Refine NeurIPS 2023 citation ──────────────────────────


def test_spec_issue841_08_self_refine_neurips_citation():
    """PROMPT-ENGINEERING.md must cite Self-Refine NeurIPS 2023."""
    content = PROMPT_ENG_DOC.read_text()
    assert "Self-Refine" in content, "Must cite Self-Refine"
    assert "NeurIPS 2023" in content, "Must cite NeurIPS 2023"


# ── Criterion 9: SKILL.md has TRIGGER frontmatter ───────────────────────────


def test_spec_issue841_09_skill_trigger_frontmatter():
    """SKILL.md must have valid TRIGGER frontmatter."""
    assert SKILL_MD.exists(), f"Missing file: {SKILL_MD}"
    content = SKILL_MD.read_text()
    # Frontmatter is between --- delimiters
    assert content.startswith("---"), "SKILL.md must start with YAML frontmatter"
    # Must contain TRIGGER directive
    assert "TRIGGER" in content, "SKILL.md must contain TRIGGER directive"
    # Specifically look for the activation pattern in description
    assert re.search(r"TRIGGER\s+when:", content, re.IGNORECASE), (
        "SKILL.md must have 'TRIGGER when:' pattern in frontmatter"
    )


# ── Criterion 10: SKILL.md has DO NOT TRIGGER frontmatter ───────────────────


def test_spec_issue841_10_skill_do_not_trigger_frontmatter():
    """SKILL.md must have DO NOT TRIGGER frontmatter."""
    content = SKILL_MD.read_text()
    assert re.search(r"DO NOT TRIGGER\s+when:", content, re.IGNORECASE), (
        "SKILL.md must have 'DO NOT TRIGGER when:' pattern in frontmatter"
    )


# ── Criterion 11: model-behavior-notes.md has Prompt Word Selection ─────────


def test_spec_issue841_11_prompt_word_selection_section():
    """model-behavior-notes.md must have a 'Prompt Word Selection' section."""
    assert MODEL_BEHAVIOR_DOC.exists(), f"Missing file: {MODEL_BEHAVIOR_DOC}"
    content = MODEL_BEHAVIOR_DOC.read_text()
    assert "## Prompt Word Selection" in content, (
        "model-behavior-notes.md must have '## Prompt Word Selection' section"
    )


# ── Criterion 12: ARCHITECTURE-OVERVIEW.md lists prompt-engineering skill ────


def test_spec_issue841_12_architecture_overview_skill_listing():
    """ARCHITECTURE-OVERVIEW.md must list prompt-engineering in skills section."""
    assert ARCH_OVERVIEW_DOC.exists(), f"Missing file: {ARCH_OVERVIEW_DOC}"
    content = ARCH_OVERVIEW_DOC.read_text()
    assert "prompt-engineering" in content, (
        "ARCHITECTURE-OVERVIEW.md must list prompt-engineering skill"
    )


# ── Criterion 13: CLAUDE.md component counts updated ────────────────────────


def test_spec_issue841_13_claude_md_skill_count_updated():
    """CLAUDE.md must reflect updated skill count (was 17, now 18)."""
    assert CLAUDE_MD.exists(), f"Missing file: {CLAUDE_MD}"
    content = CLAUDE_MD.read_text()
    # The skill count should be 18 (17 original + prompt-engineering)
    # Look for the pattern "18 skills" or "18 domain packages"
    assert re.search(r"1[89]\s+(skill|domain)", content), (
        "CLAUDE.md must have updated skill count (18 or 19)"
    )


# ── Criterion 14: Cross-references resolve ──────────────────────────────────


def test_spec_issue841_14_cross_references_resolve():
    """Cross-references between the changed files must point to existing files."""
    # PROMPT-ENGINEERING.md references model-behavior-notes.md
    assert MODEL_BEHAVIOR_DOC.exists(), (
        "PROMPT-ENGINEERING.md references model-behavior-notes.md which must exist"
    )

    # PROMPT-ENGINEERING.md references the skill file
    assert SKILL_MD.exists(), (
        "PROMPT-ENGINEERING.md references the SKILL.md which must exist"
    )

    # ARCHITECTURE-OVERVIEW.md references PROMPT-ENGINEERING.md
    arch_content = ARCH_OVERVIEW_DOC.read_text()
    assert "PROMPT-ENGINEERING.md" in arch_content, (
        "ARCHITECTURE-OVERVIEW.md should reference PROMPT-ENGINEERING.md"
    )
    assert PROMPT_ENG_DOC.exists(), (
        "ARCHITECTURE-OVERVIEW.md references PROMPT-ENGINEERING.md which must exist"
    )

    # model-behavior-notes.md references PROMPT-ENGINEERING.md
    model_content = MODEL_BEHAVIOR_DOC.read_text()
    assert "PROMPT-ENGINEERING.md" in model_content, (
        "model-behavior-notes.md should cross-reference PROMPT-ENGINEERING.md"
    )
