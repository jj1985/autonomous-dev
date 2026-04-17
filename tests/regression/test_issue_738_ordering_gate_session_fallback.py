"""
Regression test for Issue #738: Ordering gate session_id mismatch.

The coordinator writes planner completion under session_id='unknown' but the
hook reads state keyed by the real CLAUDE_SESSION_ID. This caused the ordering
gate to find no completions and incorrectly block subsequent agents.

Fix: get_completed_agents and get_launched_agents in pipeline_completion_state.py
fall back to the 'unknown' session when the primary session has no completions.
The check_ordering_with_session_fallback function in agent_ordering_gate.py
wraps this behaviour so it can be tested end-to-end.
"""

import sys
from pathlib import Path

import pytest

# Add lib to path (tests/regression/ -> tests/ -> repo root -> plugins)
LIB_DIR = Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from pipeline_completion_state import (
    clear_session,
    get_completed_agents,
    get_launched_agents,
    record_agent_completion,
    record_agent_launch,
)


class TestSessionFallback:
    """Regression tests for Issue #738: 'unknown' session fallback."""

    def _real_session_id(self) -> str:
        """Return a synthetic real session ID (not 'unknown')."""
        return "test-real-session-abc123"

    def setup_method(self) -> None:
        """Clean up any state files before each test."""
        clear_session("unknown")
        clear_session(self._real_session_id())

    def teardown_method(self) -> None:
        """Clean up state files after each test."""
        clear_session("unknown")
        clear_session(self._real_session_id())

    def test_primary_session_returns_completions_when_available(self) -> None:
        """When the real session has completions, they are returned directly."""
        real_sid = self._real_session_id()
        record_agent_completion(real_sid, "planner", issue_number=0)

        result = get_completed_agents(real_sid, issue_number=0)

        assert "planner" in result

    def test_fallback_to_unknown_session_when_primary_empty(self) -> None:
        """When real session has no completions, 'unknown' session is used as fallback.

        This is the core regression: the coordinator wrote state under 'unknown'
        before CLAUDE_SESSION_ID was set, but the hook reads with the real ID.
        """
        real_sid = self._real_session_id()

        # Coordinator writes completion under 'unknown' session
        record_agent_completion("unknown", "planner", issue_number=0)
        record_agent_completion("unknown", "researcher", issue_number=0)

        # Hook reads with real session ID — should fall back to 'unknown'
        result = get_completed_agents(real_sid, issue_number=0)

        assert "planner" in result, (
            "get_completed_agents should fall back to 'unknown' session "
            "when primary session has no completions (Issue #738)"
        )
        assert "researcher" in result

    def test_no_fallback_when_session_is_already_unknown(self) -> None:
        """When session_id IS 'unknown', no infinite loop fallback occurs."""
        record_agent_completion("unknown", "planner", issue_number=0)

        result = get_completed_agents("unknown", issue_number=0)

        assert "planner" in result

    def test_primary_and_unknown_sessions_are_merged(self) -> None:
        """Completions from both primary and 'unknown' sessions are merged.

        Issue #777: When some agents complete before CLAUDE_SESSION_ID is set
        (recorded under 'unknown') and others complete after (recorded under
        the real session ID), both sets must be visible to the ordering gate.
        The old fallback-only approach missed agents when the primary session
        had SOME completions but was missing agents from 'unknown'.
        """
        real_sid = self._real_session_id()

        # Primary session has its own completions (recorded after session ID set)
        record_agent_completion(real_sid, "implementer", issue_number=0)

        # 'unknown' session has completions from before session ID was set
        record_agent_completion("unknown", "planner", issue_number=0)

        result = get_completed_agents(real_sid, issue_number=0)

        # Both must be present — merged, not fallback
        assert "implementer" in result, (
            "Primary session completion should be present"
        )
        assert "planner" in result, (
            "Completion from 'unknown' session should be merged into result "
            "even when primary session has other completions (Issue #777)"
        )

    def test_launched_agents_fallback_to_unknown_session(self) -> None:
        """get_launched_agents also falls back to 'unknown' session."""
        real_sid = self._real_session_id()

        # Coordinator launches under 'unknown'
        record_agent_launch("unknown", "planner", issue_number=0)

        # Hook reads with real session ID
        result = get_launched_agents(real_sid, issue_number=0)

        assert "planner" in result, (
            "get_launched_agents should fall back to 'unknown' session "
            "when primary session has no launches (Issue #738)"
        )

    def test_fallback_respects_issue_number(self) -> None:
        """The fallback uses the correct issue_number when consulting 'unknown'."""
        real_sid = self._real_session_id()

        # Coordinator writes for issue 42 under 'unknown'
        record_agent_completion("unknown", "planner", issue_number=42)

        # Querying issue 0 should NOT find the issue-42 completions
        result_issue_0 = get_completed_agents(real_sid, issue_number=0)
        result_issue_42 = get_completed_agents(real_sid, issue_number=42)

        assert "planner" not in result_issue_0
        assert "planner" in result_issue_42

    def test_returns_empty_when_both_sessions_empty(self) -> None:
        """Returns empty set when neither primary nor 'unknown' session has completions."""
        real_sid = self._real_session_id()

        result = get_completed_agents(real_sid, issue_number=0)

        assert result == set()


class TestOrderingGateWithSessionFallback:
    """End-to-end test: ordering gate uses fallback state from 'unknown' session."""

    def setup_method(self) -> None:
        clear_session("unknown")
        clear_session("test-real-gate-session")

    def teardown_method(self) -> None:
        clear_session("unknown")
        clear_session("test-real-gate-session")

    def test_gate_allows_implementer_after_planner_via_fallback(self) -> None:
        """Gate allows implementer when planner completed in 'unknown' session.

        This is the exact scenario described in Issue #738:
        - Coordinator writes planner completion under session_id='unknown'
        - Hook checks ordering with real session ID
        - Without fallback: gate blocks implementer (planner not found)
        - With fallback: gate allows implementer (planner found via fallback)
        """
        from agent_ordering_gate import check_ordering_with_session_fallback

        real_sid = "test-real-gate-session"

        # Coordinator writes planner and plan-critic completion under 'unknown'
        record_agent_completion("unknown", "planner", issue_number=0)
        record_agent_completion("unknown", "plan-critic", issue_number=0)

        # Gate checks with real session ID
        result = check_ordering_with_session_fallback(
            "implementer",
            real_sid,
            issue_number=0,
            validation_mode="sequential",
            pipeline_mode="full",
        )

        assert result.passed, (
            f"Gate should allow implementer after planner (via fallback). "
            f"Reason: {result.reason}. Issue #738."
        )

    def test_gate_blocks_implementer_when_no_planner_in_any_session(self) -> None:
        """Gate still blocks implementer when planner is absent everywhere."""
        from agent_ordering_gate import check_ordering_with_session_fallback

        real_sid = "test-real-gate-session"

        # Neither session has planner
        result = check_ordering_with_session_fallback(
            "implementer",
            real_sid,
            issue_number=0,
            validation_mode="sequential",
            pipeline_mode="full",
        )

        assert not result.passed
        assert "planner" in result.missing_agents
