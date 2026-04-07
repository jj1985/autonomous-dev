"""
Tests for pipeline_completion_state.py — shared state for agent ordering enforcement.

Issues: #625, #629, #632
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add lib to path
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from pipeline_completion_state import (
    _state_file_path,
    clear_session,
    get_completed_agents,
    get_launched_agents,
    get_prompt_baseline,
    get_validation_mode,
    record_agent_completion,
    record_agent_launch,
    record_prompt_baseline,
    set_validation_mode,
)


@pytest.fixture()
def session_id():
    """Unique session ID for test isolation."""
    return f"test_session_{os.getpid()}_{time.time_ns()}"


@pytest.fixture(autouse=True)
def cleanup_state(session_id):
    """Clean up state file after each test."""
    yield
    clear_session(session_id)


class TestRecordAndRead:
    """Round-trip tests for recording and reading completions."""

    def test_record_and_read_single(self, session_id):
        record_agent_completion(session_id, "planner")
        completed = get_completed_agents(session_id)
        assert "planner" in completed

    def test_multiple_agents_accumulate(self, session_id):
        record_agent_completion(session_id, "planner")
        record_agent_completion(session_id, "implementer")
        completed = get_completed_agents(session_id)
        assert completed == {"planner", "implementer"}

    def test_issue_isolation(self, session_id):
        record_agent_completion(session_id, "planner", issue_number=1)
        record_agent_completion(session_id, "reviewer", issue_number=2)

        issue1 = get_completed_agents(session_id, issue_number=1)
        issue2 = get_completed_agents(session_id, issue_number=2)

        assert issue1 == {"planner"}
        assert issue2 == {"reviewer"}

    def test_success_false_not_in_completed(self, session_id):
        record_agent_completion(session_id, "planner", success=False)
        completed = get_completed_agents(session_id)
        assert "planner" not in completed

    def test_missing_file_returns_empty_set(self, session_id):
        completed = get_completed_agents(session_id)
        assert completed == set()


class TestPromptBaselines:
    """Tests for prompt baseline tracking."""

    def test_record_and_get_baseline(self, session_id):
        record_prompt_baseline(session_id, "reviewer", 718, 0)
        baseline = get_prompt_baseline(session_id, "reviewer")
        assert baseline == 718

    def test_missing_baseline_returns_none(self, session_id):
        baseline = get_prompt_baseline(session_id, "reviewer")
        assert baseline is None

    def test_baseline_for_unknown_agent_returns_none(self, session_id):
        record_prompt_baseline(session_id, "reviewer", 718, 0)
        baseline = get_prompt_baseline(session_id, "unknown")
        assert baseline is None


class TestValidationMode:
    """Tests for validation mode management."""

    def test_default_mode_is_sequential(self, session_id):
        mode = get_validation_mode(session_id)
        assert mode == "sequential"

    def test_set_and_get_mode(self, session_id):
        set_validation_mode(session_id, "parallel")
        mode = get_validation_mode(session_id)
        assert mode == "parallel"


class TestClearSession:
    """Tests for session cleanup."""

    def test_clear_removes_file(self, session_id):
        record_agent_completion(session_id, "planner")
        path = _state_file_path(session_id)
        assert path.exists()
        clear_session(session_id)
        assert not path.exists()

    def test_clear_nonexistent_session_is_safe(self):
        clear_session("nonexistent_session_12345")


class TestLaunchTracking:
    """Tests for agent launch tracking. Issue #686."""

    def test_record_and_get_single_launch(self, session_id):
        record_agent_launch(session_id, "reviewer")
        launched = get_launched_agents(session_id)
        assert "reviewer" in launched

    def test_multiple_launches_accumulate(self, session_id):
        record_agent_launch(session_id, "reviewer")
        record_agent_launch(session_id, "security-auditor")
        launched = get_launched_agents(session_id)
        assert launched == {"reviewer", "security-auditor"}

    def test_launch_issue_isolation(self, session_id):
        record_agent_launch(session_id, "reviewer", issue_number=1)
        record_agent_launch(session_id, "implementer", issue_number=2)

        issue1 = get_launched_agents(session_id, issue_number=1)
        issue2 = get_launched_agents(session_id, issue_number=2)

        assert issue1 == {"reviewer"}
        assert issue2 == {"implementer"}

    def test_missing_file_returns_empty_set(self, session_id):
        launched = get_launched_agents(session_id)
        assert launched == set()

    def test_launches_independent_of_completions(self, session_id):
        """Launches and completions are tracked separately."""
        record_agent_launch(session_id, "reviewer")
        record_agent_completion(session_id, "implementer")

        launched = get_launched_agents(session_id)
        completed = get_completed_agents(session_id)

        assert launched == {"reviewer"}
        assert completed == {"implementer"}

    def test_launch_idempotent(self, session_id):
        """Recording same launch twice doesn't break anything."""
        record_agent_launch(session_id, "reviewer")
        record_agent_launch(session_id, "reviewer")
        launched = get_launched_agents(session_id)
        assert launched == {"reviewer"}


class TestCorruptedFile:
    """Tests for corrupted/stale file handling."""

    def test_corrupted_file_returns_empty_set(self, session_id):
        path = _state_file_path(session_id)
        path.write_text("not valid json {{{")
        completed = get_completed_agents(session_id)
        assert completed == set()

    def test_stale_file_returns_empty_set(self, session_id):
        record_agent_completion(session_id, "planner")
        path = _state_file_path(session_id)
        # Set mtime to 3 hours ago
        old_time = time.time() - 3 * 3600
        os.utime(path, (old_time, old_time))
        completed = get_completed_agents(session_id)
        assert completed == set()
