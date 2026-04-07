"""Unit tests for the mobile-tester agent definition.

Validates that the mobile-tester agent is properly defined, registered
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


class TestMobileTesterAgentFile:
    """Tests for the mobile-tester.md agent definition file."""

    @pytest.fixture
    def agent_path(self) -> Path:
        return PROJECT_ROOT / "plugins" / "autonomous-dev" / "agents" / "mobile-tester.md"

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
        """Frontmatter must have name: mobile-tester."""
        assert frontmatter["name"] == "mobile-tester"

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

    def test_hard_gate_appium_availability(self, agent_content: str) -> None:
        """Agent must have a HARD GATE for Appium MCP availability check."""
        assert "HARD GATE: Appium MCP Availability Check" in agent_content
        assert "MOBILE-TESTER-SKIP: Appium MCP not available" in agent_content

    def test_hard_gate_environment_security(self, agent_content: str) -> None:
        """Agent must have a HARD GATE for environment security."""
        assert "HARD GATE: Environment Security" in agent_content
        # Must restrict to sandbox environments only
        assert "Simulator" in agent_content or "simulator" in agent_content
        assert "adversarial" in agent_content

    def test_hard_gate_screenshot_data_safety(self, agent_content: str) -> None:
        """Agent must have a HARD GATE for screenshot data safety."""
        assert "HARD GATE: Screenshot Data Safety" in agent_content

    def test_hard_gate_timeout(self, agent_content: str) -> None:
        """Agent must have a 60-second timeout HARD GATE."""
        assert "HARD GATE: 60-Second Timeout" in agent_content
        assert "60 seconds" in agent_content

    def test_forbidden_list_present(self, agent_content: str) -> None:
        """Agent must have a FORBIDDEN list with at least 7 entries."""
        assert "FORBIDDEN" in agent_content
        forbidden_items = [line for line in agent_content.splitlines() if "MUST NOT" in line]
        assert len(forbidden_items) >= 7, (
            f"Expected at least 7 FORBIDDEN items, found {len(forbidden_items)}"
        )

    def test_verdict_output_format(self, agent_content: str) -> None:
        """Agent must define MOBILE-TESTER-VERDICT output format."""
        assert "MOBILE-TESTER-VERDICT: PASS" in agent_content
        assert "MOBILE-TESTER-VERDICT: SKIP" in agent_content

    def test_no_blocking_verdict(self, agent_content: str) -> None:
        """Agent verdict must never be BLOCK — mobile testing is advisory."""
        assert "MOBILE-TESTER-VERDICT: BLOCK" not in agent_content
        assert "advisory" in agent_content.lower()

    def test_maestro_yaml_template(self, agent_content: str) -> None:
        """Agent must include a Maestro YAML template."""
        assert "maestro" in agent_content.lower()
        assert ".maestro/" in agent_content
        assert "appId" in agent_content

    def test_three_layer_testing_stack(self, agent_content: str) -> None:
        """Agent must describe all three testing layers."""
        # Layer 1: Appium MCP
        assert "Appium MCP" in agent_content
        # Layer 2: Maestro
        assert "Maestro" in agent_content
        # Layer 3: Native build tools
        assert "xcodebuild" in agent_content or "Gradle" in agent_content or "gradle" in agent_content


class TestMobileTesterRegistration:
    """Tests for mobile-tester registration in infrastructure files."""

    def test_registered_in_install_manifest(self) -> None:
        """mobile-tester.md must appear in install_manifest.json agents list."""
        manifest_path = (
            PROJECT_ROOT / "plugins" / "autonomous-dev" / "config" / "install_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text())
        agent_files = manifest["components"]["agents"]["files"]
        assert "plugins/autonomous-dev/agents/mobile-tester.md" in agent_files

    def test_registered_in_agent_configs(self) -> None:
        """mobile-tester must appear in AgentInvoker.AGENT_CONFIGS."""
        from agent_invoker import AgentInvoker

        assert "mobile-tester" in AgentInvoker.AGENT_CONFIGS
        config = AgentInvoker.AGENT_CONFIGS["mobile-tester"]
        assert "progress_pct" in config
        assert "artifacts_required" in config
        assert "description_template" in config
        assert "mission" in config

    def test_registered_in_skill_map(self) -> None:
        """mobile-tester must appear in AGENT_SKILL_MAP."""
        from skill_loader import AGENT_SKILL_MAP

        assert "mobile-tester" in AGENT_SKILL_MAP
        skills = AGENT_SKILL_MAP["mobile-tester"]
        assert "testing-guide" in skills
        assert "python-standards" in skills

    def test_agent_config_values(self) -> None:
        """Verify specific config values for mobile-tester."""
        from agent_invoker import AgentInvoker

        config = AgentInvoker.AGENT_CONFIGS["mobile-tester"]
        assert config["progress_pct"] == 73
        assert "implementation" in config["artifacts_required"]
        assert "iOS" in config["description_template"] or "Android" in config["description_template"]
