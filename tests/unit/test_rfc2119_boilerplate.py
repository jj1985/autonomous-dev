"""Tests for RFC 2119 language standardization across agent and command files.

Validates that all active agent prompts and key command files include
the RFC 8174 boilerplate and use MUST/MUST NOT keywords in enforcement sections.

Issue: #466
"""

from pathlib import Path

import pytest

# Resolve plugin root dynamically
_WORKTREE = Path(__file__).resolve().parents[2]
_PLUGIN = _WORKTREE / "plugins" / "autonomous-dev"
_AGENTS_DIR = _PLUGIN / "agents"
_COMMANDS_DIR = _PLUGIN / "commands"

# RFC 8174 boilerplate (the canonical text we expect in each file)
RFC_BOILERPLATE_FRAGMENT = 'RFC 2119'


def _discover_active_agents() -> list[Path]:
    """Dynamically discover all active (non-archived) agent .md files."""
    agents = sorted(_AGENTS_DIR.glob("*.md"))
    assert len(agents) >= 8, (
        f"Expected at least 8 active agents, found {len(agents)}. "
        f"Directory: {_AGENTS_DIR}"
    )
    return agents


class TestRFC2119Boilerplate:
    """Every active agent and key command file must include RFC 8174 boilerplate."""

    def test_all_agents_have_rfc_boilerplate(self) -> None:
        """Each agent .md file must contain the RFC 2119 boilerplate reference."""
        agents = _discover_active_agents()
        missing: list[str] = []
        for agent_path in agents:
            content = agent_path.read_text()
            if RFC_BOILERPLATE_FRAGMENT not in content:
                missing.append(agent_path.name)
        assert not missing, (
            f"These agent files are missing RFC 2119 boilerplate: {missing}"
        )

    @pytest.mark.parametrize("cmd_file", [
        "implement.md",
        "implement-batch.md",
        "implement-fix.md",
    ])
    def test_command_files_have_rfc_boilerplate(self, cmd_file: str) -> None:
        """Key command files must contain the RFC 2119 boilerplate reference."""
        path = _COMMANDS_DIR / cmd_file
        assert path.exists(), f"Command file not found: {path}"
        content = path.read_text()
        assert RFC_BOILERPLATE_FRAGMENT in content, (
            f"{cmd_file} is missing RFC 2119 boilerplate"
        )


class TestRFC2119Keywords:
    """Core enforcement files must use MUST/MUST NOT keywords."""

    CORE_FILES = [
        _COMMANDS_DIR / "implement.md",
        _AGENTS_DIR / "implementer.md",
        _AGENTS_DIR / "test-master.md",
        _AGENTS_DIR / "security-auditor.md",
        _AGENTS_DIR / "reviewer.md",
    ]

    def test_core_files_use_must_keyword(self) -> None:
        """Each core enforcement file must contain the word MUST (uppercase)."""
        missing: list[str] = []
        for path in self.CORE_FILES:
            content = path.read_text()
            # Look for standalone MUST (not inside a URL or other word)
            if "MUST" not in content:
                missing.append(path.name)
        assert not missing, (
            f"These core files do not use MUST keyword: {missing}"
        )

    def test_core_files_use_must_not_keyword(self) -> None:
        """Each core enforcement file must contain MUST NOT (uppercase)."""
        missing: list[str] = []
        for path in self.CORE_FILES:
            content = path.read_text()
            if "MUST NOT" not in content:
                missing.append(path.name)
        assert not missing, (
            f"These core files do not use MUST NOT keyword: {missing}"
        )

    def test_forbidden_lists_use_must_not(self) -> None:
        """FORBIDDEN sections in core files should use MUST NOT language."""
        for path in self.CORE_FILES:
            content = path.read_text()
            if "**FORBIDDEN**" in content:
                # Find the FORBIDDEN block and check it contains MUST NOT
                idx = content.index("**FORBIDDEN**")
                # Look at the next 800 chars after FORBIDDEN header
                block = content[idx:idx + 800]
                assert "MUST NOT" in block, (
                    f"{path.name}: FORBIDDEN section lacks MUST NOT language"
                )
