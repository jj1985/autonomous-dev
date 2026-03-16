#!/usr/bin/env python3
"""
Registry consistency tests for agent infrastructure.

These tests read real files to catch drift between:
- AGENT_CONFIGS in agent_invoker.py
- Agent .md files in agents/ and agents/archived/
- AGENT_SKILL_MAP in skill_loader.py

Issue: #411 (Agent registry naming collisions)
"""

import sys
from pathlib import Path

import pytest

# Add project root to path for proper imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from plugins.autonomous_dev.lib.agent_invoker import AgentInvoker
from plugins.autonomous_dev.lib.skill_loader import AGENT_SKILL_MAP

AGENTS_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev" / "agents"
ARCHIVED_DIR = AGENTS_DIR / "archived"


def _get_active_agent_names() -> set:
    """Get names of all active agent .md files (excluding archived/)."""
    return {
        f.stem
        for f in AGENTS_DIR.glob("*.md")
        if f.is_file()
    }


def _get_archived_agent_names() -> set:
    """Get names of all archived agent .md files."""
    if not ARCHIVED_DIR.exists():
        return set()
    return {
        f.stem
        for f in ARCHIVED_DIR.glob("*.md")
        if f.is_file() and f.stem != "README"
    }


class TestRegistryConsistency:
    """Verify consistency between AGENT_CONFIGS, agent files, and skill map."""

    def test_every_config_entry_has_agent_file(self):
        """Every AGENT_CONFIGS key must have a .md file in agents/ (not archived/)."""
        active_agents = _get_active_agent_names()
        config_agents = set(AgentInvoker.AGENT_CONFIGS.keys())

        missing_files = config_agents - active_agents
        assert not missing_files, (
            f"AGENT_CONFIGS entries without active agent files: {missing_files}\n"
            f"Either create the agent file or remove the config entry."
        )

    def test_every_agent_file_has_config_entry(self):
        """Every .md in agents/ (not archived/) must have an AGENT_CONFIGS entry."""
        active_agents = _get_active_agent_names()
        config_agents = set(AgentInvoker.AGENT_CONFIGS.keys())

        missing_configs = active_agents - config_agents
        assert not missing_configs, (
            f"Active agent files without AGENT_CONFIGS entries: {missing_configs}\n"
            f"Either add a config entry or archive the agent file."
        )

    def test_skill_map_agents_in_config(self):
        """Every AGENT_SKILL_MAP key must exist in AGENT_CONFIGS."""
        config_agents = set(AgentInvoker.AGENT_CONFIGS.keys())
        skill_map_agents = set(AGENT_SKILL_MAP.keys())

        missing = skill_map_agents - config_agents
        assert not missing, (
            f"AGENT_SKILL_MAP entries without AGENT_CONFIGS: {missing}\n"
            f"Either add to AGENT_CONFIGS or remove from AGENT_SKILL_MAP."
        )

    def test_no_agent_in_both_active_and_archived(self):
        """No .md filename should exist in both agents/ and agents/archived/."""
        active_agents = _get_active_agent_names()
        archived_agents = _get_archived_agent_names()

        duplicates = active_agents & archived_agents
        assert not duplicates, (
            f"Agent files in both active and archived: {duplicates}\n"
            f"Remove one copy to avoid confusion."
        )

    def test_config_entries_have_required_fields(self):
        """All AGENT_CONFIGS entries must have progress_pct, artifacts_required, description_template, mission."""
        required_fields = {"progress_pct", "artifacts_required", "description_template", "mission"}

        for agent_name, config in AgentInvoker.AGENT_CONFIGS.items():
            missing = required_fields - set(config.keys())
            assert not missing, (
                f"Agent '{agent_name}' missing required fields: {missing}"
            )

    def test_no_ghost_registrations(self):
        """All AGENT_CONFIGS entries must have active (not archived) agent files.

        Ghost registrations are config entries whose agent files only exist
        in agents/archived/ (or don't exist at all).
        """
        active_agents = _get_active_agent_names()
        config_agents = set(AgentInvoker.AGENT_CONFIGS.keys())

        ghosts = config_agents - active_agents
        assert not ghosts, (
            f"Ghost registrations (config entries without active agent files): {ghosts}\n"
            f"These agents are registered in AGENT_CONFIGS but their .md files "
            f"are missing or only in agents/archived/."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
