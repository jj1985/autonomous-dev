"""
Regression test for Issue #471: Active agents/skills referencing archived skills.

Bug: Two agents (pr-description-generator.md, project-progress-tracker.md) were in
the active agents/ directory despite having ARCHIVED banners, and referenced archived
skills (agent-output-formats, semantic-validation). Three active skills referenced the
archived project-alignment skill in their Cross-References sections.

Fix: Moved the two agents to agents/archived/ and removed the stale project-alignment
references from the three active skills.
"""

from pathlib import Path

import pytest

PLUGIN_DIR = (
    Path(__file__).parent.parent.parent.parent / "plugins" / "autonomous-dev"
)

# Archived skills that should NOT be referenced by active agents/skills
ARCHIVED_SKILLS = [
    "agent-output-formats",
    "semantic-validation",
    "project-alignment",
]

# Agents that were moved to archived/ as part of this fix
MOVED_TO_ARCHIVED = [
    "pr-description-generator.md",
    "project-progress-tracker.md",
]


@pytest.fixture
def active_agent_files() -> list[Path]:
    """All .md files in agents/ (not archived/)."""
    agents_dir = PLUGIN_DIR / "agents"
    assert agents_dir.exists(), f"agents directory not found at {agents_dir}"
    return [f for f in agents_dir.glob("*.md") if f.name != "README.md"]


@pytest.fixture
def active_skill_files() -> list[Path]:
    """All SKILL.md files in skills/ (not archived/)."""
    skills_dir = PLUGIN_DIR / "skills"
    assert skills_dir.exists(), f"skills directory not found at {skills_dir}"
    return [
        f
        for f in skills_dir.glob("*/SKILL.md")
        if "archived" not in str(f)
    ]


class TestIssue471ArchivedSkillReferences:
    """Verify active agents and skills do not reference archived skills."""

    def test_no_archived_skill_refs_in_active_agents(
        self, active_agent_files: list[Path]
    ) -> None:
        """Active agents must not reference archived skills."""
        violations = []
        for agent_file in active_agent_files:
            content = agent_file.read_text()
            for skill_name in ARCHIVED_SKILLS:
                if skill_name in content:
                    violations.append(
                        f"{agent_file.name} references archived skill '{skill_name}'"
                    )
        assert violations == [], (
            f"Active agents reference archived skills:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_archived_skill_refs_in_active_skills(
        self, active_skill_files: list[Path]
    ) -> None:
        """Active skills must not reference archived skills."""
        violations = []
        for skill_file in active_skill_files:
            content = skill_file.read_text()
            for skill_name in ARCHIVED_SKILLS:
                if skill_name in content:
                    rel_path = skill_file.relative_to(PLUGIN_DIR / "skills")
                    violations.append(
                        f"{rel_path} references archived skill '{skill_name}'"
                    )
        assert violations == [], (
            f"Active skills reference archived skills:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_misplaced_agents_moved_to_archived(self) -> None:
        """Agents with ARCHIVED banners must be in agents/archived/, not agents/."""
        agents_dir = PLUGIN_DIR / "agents"
        for agent_name in MOVED_TO_ARCHIVED:
            active_path = agents_dir / agent_name
            archived_path = agents_dir / "archived" / agent_name
            assert not active_path.exists(), (
                f"{agent_name} should not be in active agents/ directory "
                f"(it has an ARCHIVED banner)"
            )
            assert archived_path.exists(), (
                f"{agent_name} should be in agents/archived/"
            )
