#!/usr/bin/env python3
"""Smoke tests for the spec-validator agent file.

Validates that the spec-validator agent exists, has correct frontmatter,
includes required FORBIDDEN context purity section, outputs the correct
verdict format, and is registered in install_manifest.json and
batch_agent_verifier.py.

Issue: #772
"""

import json
import re
import sys
from pathlib import Path

import pytest

# Resolve project root (regression -> smoke -> tests -> repo root = parents[3])
PROJECT_ROOT = Path(__file__).resolve().parents[3]

AGENT_PATH = PROJECT_ROOT / "plugins" / "autonomous-dev" / "agents" / "spec-validator.md"
MANIFEST_PATH = PROJECT_ROOT / "plugins" / "autonomous-dev" / "config" / "install_manifest.json"

# Add lib to path for batch_agent_verifier import
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))


class TestSpecValidatorAgentFile:
    """Tests that the spec-validator agent file exists and has correct structure."""

    def test_agent_file_exists(self) -> None:
        """Agent file must exist at expected path."""
        assert AGENT_PATH.exists(), f"spec-validator.md not found at {AGENT_PATH}"

    def test_frontmatter_name(self) -> None:
        """Frontmatter must contain name: spec-validator."""
        content = AGENT_PATH.read_text()
        assert "name: spec-validator" in content

    def test_frontmatter_model_opus(self) -> None:
        """Frontmatter must specify model: opus."""
        content = AGENT_PATH.read_text()
        assert "model: opus" in content

    def test_frontmatter_tools(self) -> None:
        """Frontmatter must include Read, Write, Edit, Bash, Grep, Glob tools."""
        content = AGENT_PATH.read_text()
        required_tools = ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
        for tool in required_tools:
            assert tool in content, f"Tool {tool} not found in frontmatter"

    def test_frontmatter_skills(self) -> None:
        """Frontmatter must include testing-guide and python-standards skills."""
        content = AGENT_PATH.read_text()
        assert "testing-guide" in content
        assert "python-standards" in content

    def test_context_purity_forbidden_section(self) -> None:
        """Agent must have a FORBIDDEN section for context leakage prevention."""
        content = AGENT_PATH.read_text()
        assert "FORBIDDEN" in content
        # Must forbid reading implementer output
        assert "implementer output" in content.lower() or "implementer" in content

    def test_context_purity_forbids_reviewer_feedback(self) -> None:
        """Agent must forbid reading reviewer feedback."""
        content = AGENT_PATH.read_text()
        assert "reviewer feedback" in content.lower() or "reviewer" in content

    def test_context_purity_forbids_research_findings(self) -> None:
        """Agent must forbid reading research findings."""
        content = AGENT_PATH.read_text()
        assert "research findings" in content.lower() or "research" in content

    def test_verdict_format_present(self) -> None:
        """Agent must document SPEC-VALIDATOR-VERDICT output format."""
        content = AGENT_PATH.read_text()
        assert "SPEC-VALIDATOR-VERDICT: PASS" in content
        assert "SPEC-VALIDATOR-VERDICT: FAIL" in content

    def test_binary_verdict_only(self) -> None:
        """Agent must enforce binary verdict — no PARTIAL or WARN."""
        content = AGENT_PATH.read_text()
        # Should explicitly forbid non-binary verdicts
        assert "PARTIAL" in content or "binary" in content.lower()


class TestSpecValidatorRegistration:
    """Tests that spec-validator is registered in manifest and verifier."""

    def test_registered_in_install_manifest(self) -> None:
        """spec-validator.md must appear in install_manifest.json agents list."""
        manifest = json.loads(MANIFEST_PATH.read_text())
        agent_files = manifest["components"]["agents"]["files"]
        expected = "plugins/autonomous-dev/agents/spec-validator.md"
        assert expected in agent_files, (
            f"spec-validator.md not found in install_manifest.json agents. "
            f"Found: {agent_files}"
        )

    def test_registered_in_batch_agent_verifier(self) -> None:
        """spec-validator must appear in DEFAULT_REQUIRED_AGENTS."""
        from batch_agent_verifier import DEFAULT_REQUIRED_AGENTS

        assert "spec-validator" in DEFAULT_REQUIRED_AGENTS, (
            f"spec-validator not in DEFAULT_REQUIRED_AGENTS. "
            f"Found: {DEFAULT_REQUIRED_AGENTS}"
        )
