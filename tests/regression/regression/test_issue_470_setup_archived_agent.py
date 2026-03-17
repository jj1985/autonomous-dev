"""
Regression test for Issue #470: Remove archived setup-wizard agent reference
from commands/setup.md.

Bug: commands/setup.md referenced the archived `setup-wizard` agent and used
Task tool delegation to invoke it. The agent is archived in
agents/archived/setup-wizard.md, so the command should not delegate to it.

Fix: Replaced agent delegation with inline execution instructions and removed
Task from allowed-tools since no agent delegation is needed.
"""

from pathlib import Path

import pytest


@pytest.fixture
def setup_cmd_path() -> Path:
    """Path to the setup command file."""
    return (
        Path(__file__).parent.parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "commands"
        / "setup.md"
    )


@pytest.fixture
def setup_content(setup_cmd_path: Path) -> str:
    """Load setup command content."""
    assert setup_cmd_path.exists(), f"setup.md not found at {setup_cmd_path}"
    return setup_cmd_path.read_text()


class TestIssue470SetupArchivedAgentReference:
    """Verify setup-wizard agent references are removed from setup.md."""

    def test_no_setup_wizard_reference(self, setup_content: str):
        """The archived setup-wizard agent must not be referenced."""
        assert "setup-wizard" not in setup_content, (
            "commands/setup.md still references the archived 'setup-wizard' agent.\n"
            "This agent was archived and references should use inline execution instead.\n"
            "See Issue #470."
        )

    def test_no_task_tool_in_allowed_tools(self, setup_content: str):
        """Task tool should not be in allowed-tools since no agent delegation is needed."""
        parts = setup_content.split("---")
        assert len(parts) >= 3, "setup.md missing YAML frontmatter"
        frontmatter = parts[1]

        for line in frontmatter.splitlines():
            if "allowed-tools" in line:
                assert "Task" not in line, (
                    "Task tool still in allowed-tools frontmatter.\n"
                    "Since setup-wizard agent delegation was removed,\n"
                    "Task is no longer needed. See Issue #470."
                )
                break

    def test_essential_tools_still_present(self, setup_content: str):
        """Read, Write, Bash, Grep, Glob should remain in allowed-tools."""
        parts = setup_content.split("---")
        frontmatter = parts[1]

        for line in frontmatter.splitlines():
            if "allowed-tools" in line:
                for tool in ["Read", "Write", "Bash", "Grep", "Glob"]:
                    assert tool in line, (
                        f"{tool} missing from allowed-tools. "
                        f"The setup command needs {tool} for inline execution."
                    )
                break

    def test_inline_execution_instructions_present(self, setup_content: str):
        """Step 2 should contain inline execution instructions, not agent delegation."""
        assert "inline" in setup_content.lower(), (
            "Setup command should reference inline execution\n"
            "instead of delegating to the archived setup-wizard agent."
        )

    def test_disable_model_invocation_preserved(self, setup_content: str):
        """disable-model-invocation should remain true."""
        assert "disable-model-invocation: true" in setup_content, (
            "disable-model-invocation: true must be preserved in setup.md.\n"
            "This command provides step-by-step instructions for Claude to follow."
        )

    def test_no_context_for_setup_wizard_block(self, setup_content: str):
        """The old 'CONTEXT FOR SETUP-WIZARD' instruction block must be removed."""
        assert "CONTEXT FOR SETUP-WIZARD" not in setup_content, (
            "commands/setup.md still contains the 'CONTEXT FOR SETUP-WIZARD' block.\n"
            "This was part of the agent delegation pattern that has been replaced\n"
            "with inline execution. See Issue #470."
        )
