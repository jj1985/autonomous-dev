#!/usr/bin/env python3
"""
Tests for agent tracker state idempotency (Issue #541).

Validates that terminal-state agents (completed/failed) cannot have their
status overwritten by subsequent complete_agent() or fail_agent() calls.

This prevents the pipeline JSON status corruption where agents are marked
failed despite actually succeeding — caused by the SubagentStop race condition
where complete_agent() fires first (via Task tool), then fail_agent() fires
from unified_session_tracker's text scan.

Date: 2026-03-22
Issue: GitHub #541 - Pipeline JSON status corruption
Agent: implementer
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Portable project root detection
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

from agent_tracker import AgentTracker


@pytest.fixture
def tracker(tmp_path):
    """Provide an AgentTracker with a temporary session file."""
    session_file = str(tmp_path / "test-pipeline.json")
    t = AgentTracker(session_file=session_file)
    return t


class TestFailAgentIdempotency:
    """Tests for fail_agent() not overwriting terminal states (Issue #541)."""

    def test_fail_agent_noop_when_already_completed(self, tracker):
        """fail_agent() is a no-op when the agent already has status 'completed'.

        Regression test for Issue #541: the Task tool completes the agent, then
        SubagentStop fires fail_agent() based on a false-positive text scan.
        The completed status must be preserved.
        """
        tracker.start_agent("implementer", "Starting implementation")
        tracker.complete_agent("implementer", "All tests pass")

        # Verify status is completed before the race-condition call
        agent_entry = next(
            e for e in tracker.session_data["agents"] if e["agent"] == "implementer"
        )
        assert agent_entry["status"] == "completed"

        # Simulate SubagentStop incorrectly calling fail_agent after completion
        tracker.fail_agent("implementer", "Failed to connect — false positive from text scan")

        # Status must remain "completed"
        agent_entry_after = next(
            e for e in tracker.session_data["agents"] if e["agent"] == "implementer"
        )
        assert agent_entry_after["status"] == "completed", (
            "fail_agent() must NOT overwrite a completed agent (Issue #541). "
            f"Got status: {agent_entry_after['status']!r}"
        )
        # Original completion message must be preserved
        assert "All tests pass" in agent_entry_after["message"]

    def test_fail_agent_noop_when_already_failed(self, tracker):
        """fail_agent() preserves original failure when called twice.

        Second call with a different message must not overwrite the first.
        This ensures the first (real) failure reason is preserved.
        """
        tracker.start_agent("researcher", "Starting research")
        tracker.fail_agent("researcher", "Network timeout — original failure")

        # Attempt to overwrite with a different failure message
        tracker.fail_agent("researcher", "Secondary error — must not overwrite")

        agent_entry = next(
            e for e in tracker.session_data["agents"] if e["agent"] == "researcher"
        )
        assert agent_entry["status"] == "failed"
        assert "original failure" in agent_entry["message"], (
            "Second fail_agent() call must not overwrite the original failure message."
        )

    def test_complete_agent_noop_when_already_failed(self, tracker):
        """complete_agent() is a no-op when the agent already has status 'failed'.

        Once an agent has truly failed, a late complete_agent() call (e.g. from
        a retry path) must not overwrite the failure record.
        """
        tracker.start_agent("planner", "Starting planning")
        tracker.fail_agent("planner", "Fatal: out of context window")

        # Simulate a late/spurious complete call
        tracker.complete_agent("planner", "Plan created — spurious late completion")

        agent_entry = next(
            e for e in tracker.session_data["agents"] if e["agent"] == "planner"
        )
        assert agent_entry["status"] == "failed", (
            "complete_agent() must NOT overwrite a failed agent. "
            f"Got status: {agent_entry['status']!r}"
        )
        assert "Fatal" in agent_entry["message"]

    def test_race_condition_complete_then_fail(self, tracker):
        """Simulates Task+SubagentStop race: complete fires first, then fail.

        This is the exact sequence from Issue #541:
        1. Task tool marks agent as completed (tracker.complete_agent called)
        2. SubagentStop hook fires, text scan sees 'failed' pattern in output
        3. unified_session_tracker calls tracker.fail_agent (spurious)
        4. Without the fix: status becomes 'failed' (WRONG)
        5. With the fix: status stays 'completed' (CORRECT)
        """
        tracker.start_agent("implementer", "Starting implementation")

        # Step 1: Task tool marks completion
        tracker.complete_agent("implementer", "Implementation complete. All 42 tests pass.")

        # Step 2: SubagentStop fires fail_agent due to text-scan false positive
        # (e.g. output contained "Failed to connect to cache")
        tracker.fail_agent("implementer", "Failed to connect — false positive")

        agent_entry = next(
            e for e in tracker.session_data["agents"] if e["agent"] == "implementer"
        )

        # With the fix, the terminal state is preserved
        assert agent_entry["status"] == "completed", (
            "Race condition: complete_then_fail must preserve 'completed' status. "
            f"Got: {agent_entry['status']!r}. "
            "This is the core regression for Issue #541."
        )
        assert "All 42 tests pass" in agent_entry["message"], (
            "Original completion message must be preserved after spurious fail_agent()."
        )
