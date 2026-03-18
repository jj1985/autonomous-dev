"""Tests for /plan-to-issues command registration and structure."""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class TestPlanToIssuesRegistration:
    """Verify /plan-to-issues is properly registered in all required files."""

    def test_command_file_exists(self):
        """Command file must exist."""
        cmd_file = PROJECT_ROOT / "plugins/autonomous-dev/commands/plan-to-issues.md"
        assert cmd_file.exists(), f"Missing command file: {cmd_file}"

    def test_command_in_manifest_commands(self):
        """Command name must appear in install_manifest.json commands array."""
        manifest = json.loads(
            (PROJECT_ROOT / "plugins/autonomous-dev/config/install_manifest.json").read_text()
        )
        assert "plan-to-issues" in manifest["commands"]

    def test_command_file_in_manifest_files(self):
        """Command file path must appear in manifest components.commands.files."""
        manifest = json.loads(
            (PROJECT_ROOT / "plugins/autonomous-dev/config/install_manifest.json").read_text()
        )
        files = manifest["components"]["commands"]["files"]
        assert "plugins/autonomous-dev/commands/plan-to-issues.md" in files

    def test_command_has_valid_frontmatter(self):
        """Command file must have required frontmatter fields."""
        cmd_file = PROJECT_ROOT / "plugins/autonomous-dev/commands/plan-to-issues.md"
        content = cmd_file.read_text()
        assert content.startswith("---")
        assert "name: plan-to-issues" in content
        assert "user-invocable: true" in content

    def test_command_in_claude_md(self):
        """Command must appear in CLAUDE.md commands table."""
        claude_md = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "/plan-to-issues" in claude_md

    def test_command_in_template(self):
        """Command must appear in claude_md_section.md template."""
        template = (
            PROJECT_ROOT / "plugins/autonomous-dev/templates/claude_md_section.md"
        ).read_text()
        assert "/plan-to-issues" in template
