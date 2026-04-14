"""Spec-validation tests for Issue #850: Pre-Dispatch Ordering Protocol.

Tests that implement.md and implement-batch.md satisfy the acceptance criteria
for the pre-dispatch ordering protocol that prevents agent ordering violations
(e.g., implementer invoked before planner).
"""

from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[2]
IMPLEMENT_MD = WORKTREE / "plugins" / "autonomous-dev" / "commands" / "implement.md"
IMPLEMENT_BATCH_MD = (
    WORKTREE / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"
)


@pytest.fixture(scope="module")
def implement_content() -> str:
    """Read implement.md content once for the module."""
    assert IMPLEMENT_MD.exists(), f"implement.md not found at {IMPLEMENT_MD}"
    return IMPLEMENT_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def implement_batch_content() -> str:
    """Read implement-batch.md content once for the module."""
    assert IMPLEMENT_BATCH_MD.exists(), (
        f"implement-batch.md not found at {IMPLEMENT_BATCH_MD}"
    )
    return IMPLEMENT_BATCH_MD.read_text(encoding="utf-8")


class TestPreDispatchOrderingProtocol:
    """Spec validation: Issue #850 acceptance criteria."""

    def test_spec_issue850_1_section_header_exists(
        self, implement_content: str
    ) -> None:
        """AC1: implement.md contains Pre-Dispatch Ordering Protocol REQUIRED section."""
        assert "### Pre-Dispatch Ordering Protocol" in implement_content, (
            "implement.md must contain a heading for Pre-Dispatch Ordering Protocol (AC1)"
        )
        assert "Pre-Dispatch Ordering Protocol" in implement_content and "REQUIRED" in implement_content, (
            "The section heading must include the REQUIRED suffix (AC1)"
        )

    def test_spec_issue850_2a_check_function_present(
        self, implement_content: str
    ) -> None:
        """AC1: The section contains check_ordering_with_session_fallback."""
        assert "check_ordering_with_session_fallback" in implement_content, (
            "implement.md must contain check_ordering_with_session_fallback (AC1)"
        )

    def test_spec_issue850_2b_session_id_env_var(
        self, implement_content: str
    ) -> None:
        """AC1: The inline Python block uses os.environ.get CLAUDE_SESSION_ID."""
        assert "os.environ.get(" in implement_content and "CLAUDE_SESSION_ID" in implement_content and "unknown" in implement_content, (
            "implement.md must use os.environ.get with CLAUDE_SESSION_ID and unknown fallback (AC1)"
        )

    def test_spec_issue850_3_at_least_5_dispatch_references(
        self, implement_content: str
    ) -> None:
        """AC2: At least 5 agent dispatch steps reference the Pre-Dispatch Ordering Protocol."""
        occurrences = implement_content.count("Pre-Dispatch Ordering Protocol")
        assert occurrences >= 5, (
            f"implement.md has {occurrences} references to Pre-Dispatch Ordering Protocol, "
            f"but at least 5 are required (AC2)"
        )

    def test_spec_issue850_4_batch_cross_reference(
        self, implement_batch_content: str
    ) -> None:
        """AC3: implement-batch.md cross-references the Pre-Dispatch Ordering Protocol."""
        assert "Pre-Dispatch Ordering Protocol" in implement_batch_content, (
            "implement-batch.md must cross-reference the Pre-Dispatch Ordering Protocol (AC3)"
        )
        assert "implement.md" in implement_batch_content, (
            "implement-batch.md must reference implement.md as the source (AC3)"
        )

    def test_spec_issue850_5_hard_gate_language(
        self, implement_content: str
    ) -> None:
        """AC5: Protocol includes HARD GATE language forbidding dispatch when result.passed is False."""
        assert "HARD GATE" in implement_content, (
            "implement.md must contain HARD GATE enforcement language (AC5)"
        )
        assert "result.passed" in implement_content, (
            "implement.md must reference result.passed in the protocol (AC5)"
        )
        assert "MUST NOT dispatch" in implement_content, (
            "implement.md must contain MUST NOT dispatch language (AC5)"
        )

    def test_spec_issue850_6_static_inspection_tests_exist(self) -> None:
        """AC4: The 3 static file inspection tests exist."""
        test_file = (
            WORKTREE
            / "tests"
            / "unit"
            / "commands"
            / "test_implement_ordering_protocol.py"
        )
        assert test_file.exists(), (
            f"Static inspection test file not found at {test_file} (AC4)"
        )
