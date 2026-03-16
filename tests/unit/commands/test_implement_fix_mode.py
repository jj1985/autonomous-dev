"""Tests for Issue #431: /implement --fix mode.

Validates:
1. implement-fix.md command file exists with correct frontmatter
2. implement.md references --fix in STEP 0 routing
3. implement-fix.md is in install_manifest.json
4. --fix mode has correct pipeline structure (4 steps, 3 agents minimum)
"""

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
COMMANDS_DIR = PROJECT_ROOT / "plugins/autonomous-dev/commands"
MANIFEST_PATH = PROJECT_ROOT / "plugins/autonomous-dev/install_manifest.json"


class TestImplementFixCommandFile:
    """Validate implement-fix.md exists and has correct structure."""

    def test_file_exists(self):
        """implement-fix.md must exist."""
        assert (COMMANDS_DIR / "implement-fix.md").exists()

    def test_frontmatter_name(self):
        """Frontmatter must have name: implement-fix."""
        content = (COMMANDS_DIR / "implement-fix.md").read_text()
        assert "name: implement-fix" in content

    def test_not_user_invocable(self):
        """implement-fix should NOT be user-invocable (invoked via /implement --fix)."""
        content = (COMMANDS_DIR / "implement-fix.md").read_text()
        assert "user-invocable: false" in content

    def test_has_four_steps(self):
        """Pipeline must have 4 steps: F1, F2, F3, F4."""
        content = (COMMANDS_DIR / "implement-fix.md").read_text()
        for step in ["STEP F1", "STEP F2", "STEP F3", "STEP F4"]:
            assert step in content, f"Missing {step} in implement-fix.md"

    def test_step_f3_hard_gate(self):
        """STEP F3 must have a HARD GATE for 0 failures."""
        content = (COMMANDS_DIR / "implement-fix.md").read_text()
        assert "HARD GATE" in content
        assert "0 failures" in content

    def test_minimum_agents(self):
        """Must specify minimum 3 agents."""
        content = (COMMANDS_DIR / "implement-fix.md").read_text()
        assert "3 agents" in content
        # Must mention the three required agents
        for agent in ["implementer", "reviewer", "doc-master"]:
            assert agent in content, f"Missing agent '{agent}' in implement-fix.md"


class TestImplementMdFixRouting:
    """Validate implement.md routes --fix correctly."""

    def test_fix_flag_in_mode_table(self):
        """implement.md mode table must include --fix."""
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "`--fix`" in content

    def test_fix_routing_in_step0(self):
        """STEP 0 must route --fix to implement-fix.md."""
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "implement-fix.md" in content

    def test_fix_mutual_exclusivity(self):
        """--fix must be documented as mutually exclusive with --batch, --issues, --resume."""
        content = (COMMANDS_DIR / "implement.md").read_text()
        assert "mutually exclusive" in content.lower() or "mutual exclusivity" in content.lower()


class TestManifestInclusion:
    """Validate implement-fix.md is in install_manifest.json."""

    def test_in_manifest(self):
        """implement-fix.md must be listed in install_manifest.json commands."""
        manifest = json.loads(MANIFEST_PATH.read_text())
        command_files = manifest["components"]["commands"]["files"]
        assert "plugins/autonomous-dev/commands/implement-fix.md" in command_files
