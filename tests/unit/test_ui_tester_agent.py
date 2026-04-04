"""Unit tests for the ui-tester agent definition.

Validates that the ui-tester agent is properly defined, registered
in all required systems, and contains the expected HARD GATE sections.
"""

import json
import sys
from pathlib import Path

import pytest
import yaml

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Add lib to path for imports
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))


class TestUITesterAgentFile:
    """Tests for the ui-tester.md agent definition file."""

    @pytest.fixture
    def agent_path(self) -> Path:
        return PROJECT_ROOT / "plugins" / "autonomous-dev" / "agents" / "ui-tester.md"

    @pytest.fixture
    def agent_content(self, agent_path: Path) -> str:
        assert agent_path.exists(), f"Agent file not found: {agent_path}"
        return agent_path.read_text()

    @pytest.fixture
    def frontmatter(self, agent_content: str) -> dict:
        """Parse YAML frontmatter from agent file."""
        parts = agent_content.split("---", 2)
        assert len(parts) >= 3, "Agent file must have YAML frontmatter delimited by ---"
        return yaml.safe_load(parts[1])

    def test_agent_file_exists(self, agent_path: Path) -> None:
        """Agent file must exist at expected path."""
        assert agent_path.exists()

    def test_frontmatter_name(self, frontmatter: dict) -> None:
        """Frontmatter must have name: ui-tester."""
        assert frontmatter["name"] == "ui-tester"

    def test_frontmatter_model(self, frontmatter: dict) -> None:
        """Frontmatter must specify sonnet model."""
        assert frontmatter["model"] == "sonnet"

    def test_frontmatter_tools(self, frontmatter: dict) -> None:
        """Frontmatter must list required tools."""
        tools = frontmatter["tools"]
        assert "Read" in tools
        assert "Write" in tools
        assert "Edit" in tools
        assert "Bash" in tools

    def test_frontmatter_skills(self, frontmatter: dict) -> None:
        """Frontmatter must list required skills."""
        skills = frontmatter["skills"]
        assert "testing-guide" in skills
        assert "python-standards" in skills

    def test_hard_gate_playwright_availability(self, agent_content: str) -> None:
        """Agent must have a HARD GATE for Playwright MCP availability check."""
        assert "HARD GATE: Playwright MCP Availability Check" in agent_content
        assert "UI-TESTER-SKIP: Playwright MCP not available" in agent_content

    def test_hard_gate_url_security(self, agent_content: str) -> None:
        """Agent must have a HARD GATE for URL security."""
        assert "HARD GATE: URL Security" in agent_content
        assert "localhost" in agent_content
        assert "127.0.0.1" in agent_content
        assert "adversarial" in agent_content

    def test_hard_gate_timeout(self, agent_content: str) -> None:
        """Agent must have a 60-second timeout HARD GATE."""
        assert "HARD GATE: 60-Second Timeout" in agent_content
        assert "60 seconds" in agent_content

    def test_forbidden_list_present(self, agent_content: str) -> None:
        """Agent must have a FORBIDDEN list with actual entries."""
        assert "FORBIDDEN" in agent_content
        # Check for specific forbidden items
        forbidden_items = [line for line in agent_content.splitlines() if "MUST NOT" in line]
        assert len(forbidden_items) >= 5, (
            f"Expected at least 5 FORBIDDEN items, found {len(forbidden_items)}"
        )

    def test_verdict_output_format(self, agent_content: str) -> None:
        """Agent must define UI-TESTER-VERDICT output format."""
        assert "UI-TESTER-VERDICT: PASS" in agent_content
        assert "UI-TESTER-VERDICT: SKIP" in agent_content

    def test_no_blocking_verdict(self, agent_content: str) -> None:
        """Agent verdict must never be BLOCK — E2E is advisory."""
        assert "UI-TESTER-VERDICT: BLOCK" not in agent_content
        assert "advisory" in agent_content.lower()


class TestUITesterRegistration:
    """Tests for ui-tester registration in infrastructure files."""

    def test_registered_in_install_manifest(self) -> None:
        """ui-tester.md must appear in install_manifest.json agents list."""
        manifest_path = (
            PROJECT_ROOT / "plugins" / "autonomous-dev" / "config" / "install_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text())
        agent_files = manifest["components"]["agents"]["files"]
        assert "plugins/autonomous-dev/agents/ui-tester.md" in agent_files

    def test_registered_in_agent_configs(self) -> None:
        """ui-tester must appear in AgentInvoker.AGENT_CONFIGS."""
        from agent_invoker import AgentInvoker

        assert "ui-tester" in AgentInvoker.AGENT_CONFIGS
        config = AgentInvoker.AGENT_CONFIGS["ui-tester"]
        assert "progress_pct" in config
        assert "artifacts_required" in config
        assert "description_template" in config
        assert "mission" in config

    def test_registered_in_skill_map(self) -> None:
        """ui-tester must appear in AGENT_SKILL_MAP."""
        from skill_loader import AGENT_SKILL_MAP

        assert "ui-tester" in AGENT_SKILL_MAP
        skills = AGENT_SKILL_MAP["ui-tester"]
        assert "testing-guide" in skills
        assert "python-standards" in skills

    def test_agent_config_values(self) -> None:
        """Verify specific config values for ui-tester."""
        from agent_invoker import AgentInvoker

        config = AgentInvoker.AGENT_CONFIGS["ui-tester"]
        assert config["progress_pct"] == 72
        assert "implementation" in config["artifacts_required"]
        assert "E2E" in config["description_template"]
