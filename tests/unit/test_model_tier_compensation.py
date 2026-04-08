"""Tests for model-tier-compensation blocks in agent prompts.

Validates that each agent tier has the correct compensation block,
the block tier matches the frontmatter model declaration, and
compensation blocks appear before the mission section.
"""

import re
from pathlib import Path

import pytest

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = WORKTREE_ROOT / "plugins" / "autonomous-dev" / "agents"
DOCS_DIR = WORKTREE_ROOT / "docs"


def _read_agent(name: str) -> str:
    """Read agent file contents."""
    path = AGENTS_DIR / f"{name}.md"
    assert path.exists(), f"Agent file not found: {path}"
    return path.read_text()


def _extract_frontmatter_model(content: str) -> str | None:
    """Extract model value from YAML frontmatter."""
    match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None
    frontmatter = match.group(1)
    model_match = re.search(r"^model:\s*(\S+)", frontmatter, re.MULTILINE)
    return model_match.group(1) if model_match else None


def _extract_compensation_tier(content: str) -> str | None:
    """Extract tier attribute from model-tier-compensation block."""
    match = re.search(r'<model-tier-compensation tier="([^"]+)">', content)
    return match.group(1) if match else None


def _compensation_position(content: str) -> int:
    """Return character index of the compensation block start, or -1."""
    match = re.search(r"<model-tier-compensation", content)
    return match.start() if match else -1


def _mission_position(content: str) -> int:
    """Return character index of the mission section heading, or -1."""
    match = re.search(r"^## (Mission|Your Mission)", content, re.MULTILINE)
    return match.start() if match else -1


def test_opus_agents_have_compensation_block() -> None:
    """implementer.md and planner.md must contain the Opus compensation block."""
    for agent_name in ("implementer", "planner"):
        content = _read_agent(agent_name)
        assert '<model-tier-compensation tier="opus">' in content, (
            f"Agent '{agent_name}' is missing <model-tier-compensation tier=\"opus\">"
        )


def test_sonnet_agent_has_compensation_block() -> None:
    """reviewer.md must contain the Sonnet compensation block."""
    content = _read_agent("reviewer")
    assert '<model-tier-compensation tier="sonnet">' in content, (
        'Agent "reviewer" is missing <model-tier-compensation tier="sonnet">'
    )


def test_haiku_agent_has_compensation_block() -> None:
    """researcher-local.md must contain the Haiku compensation block."""
    content = _read_agent("researcher-local")
    assert '<model-tier-compensation tier="haiku">' in content, (
        'Agent "researcher-local" is missing <model-tier-compensation tier="haiku">'
    )


def test_compensation_tier_matches_frontmatter() -> None:
    """For each agent with a compensation block, the tier must match the frontmatter model."""
    agents_to_check = {
        "implementer": "opus",
        "planner": "opus",
        "reviewer": "sonnet",
        "researcher-local": "haiku",
    }
    for agent_name, expected_model in agents_to_check.items():
        content = _read_agent(agent_name)
        frontmatter_model = _extract_frontmatter_model(content)
        assert frontmatter_model is not None, (
            f"Agent '{agent_name}' has no model in frontmatter"
        )
        compensation_tier = _extract_compensation_tier(content)
        assert compensation_tier is not None, (
            f"Agent '{agent_name}' has no compensation block"
        )
        assert compensation_tier == frontmatter_model, (
            f"Agent '{agent_name}': compensation tier '{compensation_tier}' "
            f"does not match frontmatter model '{frontmatter_model}'"
        )
        assert frontmatter_model == expected_model, (
            f"Agent '{agent_name}': frontmatter model '{frontmatter_model}' "
            f"does not match expected '{expected_model}'"
        )


def test_compensation_block_before_mission() -> None:
    """Compensation blocks must appear before ## Mission or ## Your Mission."""
    agents_to_check = ("implementer", "planner", "reviewer", "researcher-local")
    for agent_name in agents_to_check:
        content = _read_agent(agent_name)
        comp_pos = _compensation_position(content)
        mission_pos = _mission_position(content)

        assert comp_pos != -1, (
            f"Agent '{agent_name}' has no compensation block"
        )
        assert mission_pos != -1, (
            f"Agent '{agent_name}' has no '## Mission' or '## Your Mission' section"
        )
        assert comp_pos < mission_pos, (
            f"Agent '{agent_name}': compensation block (pos {comp_pos}) "
            f"must appear before mission section (pos {mission_pos})"
        )


def test_model_behavior_notes_exists() -> None:
    """docs/model-behavior-notes.md must exist with all 3 tier sections."""
    notes_path = DOCS_DIR / "model-behavior-notes.md"
    assert notes_path.exists(), f"docs/model-behavior-notes.md not found at {notes_path}"

    content = notes_path.read_text()
    for section in ("## Opus Behavioral Notes", "## Sonnet Behavioral Notes", "## Haiku Behavioral Notes"):
        assert section in content, (
            f"docs/model-behavior-notes.md is missing section: '{section}'"
        )


def test_no_meta_commentary_in_compensation() -> None:
    """Compensation blocks must not contain meta-commentary about model weaknesses."""
    forbidden_words = {"weakness", "limitation", "tends to fail"}
    agents_to_check = ("implementer", "planner", "reviewer", "researcher-local")

    for agent_name in agents_to_check:
        content = _read_agent(agent_name)
        # Extract just the compensation block content
        match = re.search(
            r"<model-tier-compensation[^>]*>(.*?)</model-tier-compensation>",
            content,
            re.DOTALL,
        )
        if match is None:
            continue
        block_text = match.group(1).lower()
        for word in forbidden_words:
            assert word not in block_text, (
                f"Agent '{agent_name}' compensation block contains forbidden "
                f"meta-commentary word: '{word}'"
            )
