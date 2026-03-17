"""
Regression test for Issue #469: Remove archived alignment-analyzer agent reference
from commands/align.md.

Bug: commands/align.md referenced the archived `alignment-analyzer` agent and used
Task tool delegation to invoke it. The agent no longer exists, so the command
would fail when trying to delegate to it.

Fix: Replaced agent delegation with inline execution instructions and removed
Task from allowed-tools since no agent delegation is needed.
"""

from pathlib import Path

import pytest


@pytest.fixture
def align_cmd_path() -> Path:
    """Path to the align command file."""
    return (
        Path(__file__).parent.parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "commands"
        / "align.md"
    )


@pytest.fixture
def align_content(align_cmd_path: Path) -> str:
    """Load align command content."""
    assert align_cmd_path.exists(), f"align.md not found at {align_cmd_path}"
    return align_cmd_path.read_text()


class TestIssue469AlignArchivedAgentReference:
    """Verify alignment-analyzer agent references are removed from align.md."""

    def test_no_alignment_analyzer_reference(self, align_content: str):
        """The archived alignment-analyzer agent must not be referenced."""
        assert "alignment-analyzer" not in align_content, (
            "commands/align.md still references the archived 'alignment-analyzer' agent.\n"
            "This agent was archived and references should use inline execution instead.\n"
            "See Issue #469."
        )

    def test_no_task_tool_in_allowed_tools(self, align_content: str):
        """Task tool should not be in allowed-tools since no agent delegation is needed."""
        # Extract frontmatter
        parts = align_content.split("---")
        assert len(parts) >= 3, "align.md missing YAML frontmatter"
        frontmatter = parts[1]

        # Find the allowed-tools line
        for line in frontmatter.splitlines():
            if "allowed-tools" in line:
                assert "Task" not in line, (
                    "Task tool still in allowed-tools frontmatter.\n"
                    "Since alignment-analyzer agent delegation was removed,\n"
                    "Task is no longer needed. See Issue #469."
                )
                break

    def test_essential_tools_still_present(self, align_content: str):
        """Read, Write, Edit, Grep, Glob should remain in allowed-tools."""
        parts = align_content.split("---")
        frontmatter = parts[1]

        for line in frontmatter.splitlines():
            if "allowed-tools" in line:
                for tool in ["Read", "Write", "Edit", "Grep", "Glob"]:
                    assert tool in line, (
                        f"{tool} missing from allowed-tools. "
                        f"The align command needs {tool} for inline execution."
                    )
                break

    def test_implementation_section_uses_inline_execution(self, align_content: str):
        """Implementation section should reference inline execution, not agent delegation."""
        # Should mention executing phases inline
        assert "inline" in align_content.lower() or "as described above" in align_content.lower(), (
            "Implementation section should reference inline execution\n"
            "instead of delegating to the archived alignment-analyzer agent."
        )

    def test_disable_model_invocation_preserved(self, align_content: str):
        """disable-model-invocation should remain true."""
        assert "disable-model-invocation: true" in align_content, (
            "disable-model-invocation: true must be preserved in align.md.\n"
            "This command provides step-by-step instructions for Claude to follow."
        )
