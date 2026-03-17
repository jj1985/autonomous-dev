"""
Tests for the Stop-verify-test-coverage agent hook PoC.

Validates that:
1. The hook file exists at the expected path
2. It references only read-only tools (no Bash/Write/Edit)
3. It contains a non-blocking approve decision
4. It does NOT contain enforcement/blocking language
5. It follows the agent hook markdown format

Date: 2026-03-17
Issue: #467
"""

from pathlib import Path

import pytest

# Path to the agent hook relative to repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_PATH = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks" / "Stop-verify-test-coverage.md"
ADR_PATH = REPO_ROOT / "docs" / "ADR-001-agent-hooks.md"


@pytest.fixture
def hook_content() -> str:
    """Read the agent hook markdown content."""
    assert HOOK_PATH.exists(), f"Hook file not found at {HOOK_PATH}"
    return HOOK_PATH.read_text()


class TestAgentHookFileExists:
    """Verify the hook file exists at the expected location."""

    def test_hook_file_exists(self) -> None:
        """The Stop-verify-test-coverage.md file must exist in the hooks directory."""
        assert HOOK_PATH.exists(), (
            f"Agent hook file not found: {HOOK_PATH}\n"
            f"Expected markdown prompt file for type:agent hook."
        )

    def test_hook_file_is_markdown(self) -> None:
        """The hook file must be a .md file (required for type:agent hooks)."""
        assert HOOK_PATH.suffix == ".md", (
            f"Agent hook must be a .md file, got: {HOOK_PATH.suffix}\n"
            f"type:agent hooks use markdown prompts, not Python scripts."
        )


class TestAgentHookReadOnlyTools:
    """Verify the hook only references read-only tools."""

    # Tools that agent hooks are allowed to use
    ALLOWED_TOOLS = {"Read", "Grep", "Glob"}

    # Tools that MUST NOT appear as instructions to use
    FORBIDDEN_TOOLS = {"Bash", "Write", "Edit"}

    def test_references_only_readonly_tools(self, hook_content: str) -> None:
        """The hook must not instruct the agent to USE forbidden tools.

        Mentions in a prohibition context (e.g., "Do NOT use Bash") are allowed.
        Positive instructions (e.g., "Use Bash to run...") are forbidden.
        """
        import re

        for tool in self.FORBIDDEN_TOOLS:
            # Find all lines mentioning the tool
            for line in hook_content.splitlines():
                if tool not in line:
                    continue
                # Skip lines that are prohibitions (contain "NOT" or "not" or "never")
                if re.search(r"\b(NOT|not|never|Never|NEVER|Don.t|don.t)\b", line):
                    continue
                # Skip lines that are just listing tools in a negative context
                if "ONLY" in line or "only" in line:
                    continue
                # If the line positively instructs use of a forbidden tool, fail
                positive_patterns = [
                    rf"\b[Uu]se {tool}\b",
                    rf"\b[Rr]un {tool}\b",
                ]
                for pattern in positive_patterns:
                    assert not re.search(pattern, line), (
                        f"Agent hook positively instructs use of forbidden tool '{tool}'.\n"
                        f"Line: {line.strip()}\n"
                        f"Agent hooks may only use: {self.ALLOWED_TOOLS}"
                    )

    def test_explicitly_forbids_write_tools(self, hook_content: str) -> None:
        """The hook should explicitly state that Bash/Write/Edit are not allowed."""
        # The hook should contain language forbidding these tools
        assert "Do NOT use Bash" in hook_content or "do NOT use Bash" in hook_content, (
            "Agent hook should explicitly forbid Bash tool usage.\n"
            "Add instruction like: 'Do NOT use Bash, Write, or Edit.'"
        )


class TestAgentHookNonBlocking:
    """Verify the hook is advisory-only and never blocks."""

    def test_contains_approve_decision(self, hook_content: str) -> None:
        """The hook must contain a non-blocking approve decision."""
        assert '"decision": "approve"' in hook_content or '"decision":"approve"' in hook_content, (
            'Agent hook must contain {"decision": "approve"}.\n'
            "Agent hooks are advisory-only and must never block operations.\n"
            "See ADR-001-agent-hooks.md for rationale."
        )

    def test_does_not_contain_block_decision(self, hook_content: str) -> None:
        """The hook must NOT contain any blocking decision."""
        assert '"decision": "block"' not in hook_content, (
            'Agent hook must NOT contain {"decision": "block"}.\n'
            "Agent hooks are advisory-only per ADR-001."
        )
        assert '"decision":"block"' not in hook_content, (
            'Agent hook must NOT contain {"decision":"block"}.\n'
            "Agent hooks are advisory-only per ADR-001."
        )

    def test_does_not_contain_enforcement_language(self, hook_content: str) -> None:
        """The hook must not use enforcement language (FORBIDDEN, EXIT_BLOCK, etc.)."""
        enforcement_terms = ["EXIT_BLOCK", "FORBIDDEN", "must block", "MUST BLOCK"]
        for term in enforcement_terms:
            assert term not in hook_content, (
                f"Agent hook contains enforcement language: '{term}'.\n"
                f"Agent hooks are advisory-only. Use informational language instead.\n"
                f"See ADR-001-agent-hooks.md for rationale."
            )


class TestADRExists:
    """Verify the ADR document exists."""

    def test_adr_file_exists(self) -> None:
        """ADR-001-agent-hooks.md must exist in docs/."""
        assert ADR_PATH.exists(), (
            f"ADR file not found: {ADR_PATH}\n"
            f"The Architecture Decision Record for agent hooks is required."
        )
