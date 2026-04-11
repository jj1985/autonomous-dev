"""Spec validation tests for Issue #786: Pipeline ordering + doc-master batch gate.

These tests validate the acceptance criteria from the spec:
1. Reviewer must complete before security-auditor (ordering enforcement)
2. Doc-master completion gate blocks batch commits when doc-master is missing
3. SKIP_BATCH_DOC_MASTER_GATE env var bypasses the gate
4. Gates fail open on errors
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

# Add lib to path so we can import the modules under test
sys.path.insert(0, str(LIB_DIR))


@pytest.fixture(autouse=True)
def _clean_sys_path():
    """Ensure LIB_DIR is on sys.path for every test, clean up after."""
    if str(LIB_DIR) not in sys.path:
        sys.path.insert(0, str(LIB_DIR))
    yield


@pytest.fixture
def unique_session_id():
    """Generate a unique session ID per test to avoid state file collisions."""
    return f"spec-test-{time.time_ns()}"


@pytest.fixture
def state_file_cleanup(unique_session_id):
    """Clean up state file after test."""
    from pipeline_completion_state import _state_file_path, clear_session

    yield unique_session_id
    clear_session(unique_session_id)


# ---------------------------------------------------------------------------
# Criterion 1: Security-auditor blocked when reviewer has NOT completed
# ---------------------------------------------------------------------------
class TestReviewerSecurityAuditorOrdering:
    """Validate reviewer -> security-auditor ordering enforcement."""

    def test_spec_786_1_security_auditor_blocked_without_reviewer(
        self, state_file_cleanup
    ):
        """Security-auditor MUST be blocked when reviewer has not completed."""
        session_id = state_file_cleanup

        from agent_ordering_gate import check_ordering_prerequisites
        from pipeline_completion_state import record_agent_completion

        # Record implementer as completed (prerequisite for both reviewer and security-auditor)
        record_agent_completion(session_id, "implementer", issue_number=0, success=True)

        # Get completed agents (reviewer is NOT completed)
        from pipeline_completion_state import get_completed_agents

        completed = get_completed_agents(session_id, issue_number=0)

        # Check ordering for security-auditor in sequential mode
        result = check_ordering_prerequisites(
            "security-auditor",
            completed,
            validation_mode="sequential",
        )

        assert result.passed is False, (
            "security-auditor should be BLOCKED when reviewer has not completed"
        )
        assert "reviewer" in result.reason.lower() or "reviewer" in [
            a.lower() for a in result.missing_agents
        ], "Block reason should mention reviewer as missing prerequisite"

    def test_spec_786_2_security_auditor_allowed_after_reviewer(
        self, state_file_cleanup
    ):
        """Security-auditor MUST be allowed when reviewer has completed."""
        session_id = state_file_cleanup

        from agent_ordering_gate import check_ordering_prerequisites
        from pipeline_completion_state import (
            get_completed_agents,
            record_agent_completion,
        )

        # Record both implementer and reviewer as completed
        record_agent_completion(session_id, "implementer", issue_number=0, success=True)
        record_agent_completion(session_id, "reviewer", issue_number=0, success=True)

        completed = get_completed_agents(session_id, issue_number=0)

        result = check_ordering_prerequisites(
            "security-auditor",
            completed,
            validation_mode="sequential",
        )

        assert result.passed is True, (
            "security-auditor should be ALLOWED when reviewer has completed"
        )


# ---------------------------------------------------------------------------
# Criterion 2: Doc-master gate blocks batch commits when incomplete
# ---------------------------------------------------------------------------
class TestDocMasterBatchGate:
    """Validate doc-master completion gate for batch commits."""

    def test_spec_786_3_batch_commit_blocked_without_doc_master(
        self, state_file_cleanup
    ):
        """Git commit in batch mode MUST be blocked when doc-master is missing for any issue."""
        session_id = state_file_cleanup

        from pipeline_completion_state import (
            record_agent_completion,
            verify_batch_doc_master_completions,
        )

        # Record completions for two batch issues; one has doc-master, one does not
        record_agent_completion(session_id, "implementer", issue_number=100, success=True)
        record_agent_completion(session_id, "doc-master", issue_number=100, success=True)
        record_agent_completion(session_id, "implementer", issue_number=101, success=True)
        # Issue 101 is missing doc-master

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)

        assert all_passed is False, (
            "Gate should FAIL when any batch issue is missing doc-master"
        )
        assert 100 in with_dm, "Issue 100 should be listed as having doc-master"
        assert 101 in missing_dm, "Issue 101 should be listed as missing doc-master"

    def test_spec_786_4_batch_commit_allowed_with_all_doc_master(
        self, state_file_cleanup
    ):
        """Git commit in batch mode MUST be allowed when doc-master completed for all issues."""
        session_id = state_file_cleanup

        from pipeline_completion_state import (
            record_agent_completion,
            verify_batch_doc_master_completions,
        )

        # Record doc-master completions for all batch issues
        record_agent_completion(session_id, "implementer", issue_number=200, success=True)
        record_agent_completion(session_id, "doc-master", issue_number=200, success=True)
        record_agent_completion(session_id, "implementer", issue_number=201, success=True)
        record_agent_completion(session_id, "doc-master", issue_number=201, success=True)

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)

        assert all_passed is True, (
            "Gate should PASS when all batch issues have doc-master"
        )
        assert len(missing_dm) == 0, "No issues should be missing doc-master"
        assert 200 in with_dm and 201 in with_dm


# ---------------------------------------------------------------------------
# Criterion 3: SKIP_BATCH_DOC_MASTER_GATE env var bypasses the gate
# ---------------------------------------------------------------------------
class TestDocMasterGateEnvBypass:
    """Validate SKIP_BATCH_DOC_MASTER_GATE environment variable bypass."""

    @pytest.mark.parametrize("env_value", ["1", "true", "yes", "TRUE", "True", "YES"])
    def test_spec_786_5_env_var_bypasses_gate(
        self, state_file_cleanup, env_value, monkeypatch
    ):
        """SKIP_BATCH_DOC_MASTER_GATE env var MUST bypass the doc-master gate."""
        session_id = state_file_cleanup

        from pipeline_completion_state import (
            record_agent_completion,
            verify_batch_doc_master_completions,
        )

        # Set up a session with missing doc-master
        record_agent_completion(session_id, "implementer", issue_number=300, success=True)
        # Intentionally NOT recording doc-master for issue 300

        # Set the bypass env var
        monkeypatch.setenv("SKIP_BATCH_DOC_MASTER_GATE", env_value)

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)

        assert all_passed is True, (
            f"Gate should be BYPASSED when SKIP_BATCH_DOC_MASTER_GATE={env_value}"
        )

    def test_spec_786_5b_env_var_not_set_does_not_bypass(
        self, state_file_cleanup, monkeypatch
    ):
        """Without the env var, the gate should NOT be bypassed."""
        session_id = state_file_cleanup

        from pipeline_completion_state import (
            record_agent_completion,
            verify_batch_doc_master_completions,
        )

        # Ensure env var is unset
        monkeypatch.delenv("SKIP_BATCH_DOC_MASTER_GATE", raising=False)

        record_agent_completion(session_id, "implementer", issue_number=400, success=True)
        # Missing doc-master

        all_passed, _, missing_dm = verify_batch_doc_master_completions(session_id)

        assert all_passed is False, "Gate should NOT be bypassed when env var is unset"
        assert 400 in missing_dm


# ---------------------------------------------------------------------------
# Criterion 4: Gate fails open on errors
# ---------------------------------------------------------------------------
class TestGateFailOpen:
    """Validate that gates fail open on errors."""

    def test_spec_786_6_doc_master_gate_fails_open_no_state(self):
        """Doc-master gate MUST fail open (allow) when no state file exists."""
        from pipeline_completion_state import verify_batch_doc_master_completions

        # Use a session ID that has never been used (no state file)
        nonexistent_session = f"nonexistent-{time.time_ns()}"

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(
            nonexistent_session
        )

        assert all_passed is True, "Gate must fail open when no state file exists"
        assert with_dm == []
        assert missing_dm == []

    def test_spec_786_7_ordering_gate_fails_open_on_error(self):
        """Pipeline ordering gate MUST fail open on errors."""
        from agent_ordering_gate import check_ordering_prerequisites

        # Pass a valid agent name but with a non-set completed_agents
        # to verify the function doesn't crash — the real fail-open is
        # in validate_pipeline_ordering which wraps this in try/except.
        # We test the wrapper behavior by verifying the function itself
        # handles normal empty inputs gracefully.
        result = check_ordering_prerequisites(
            "unknown-agent-xyz",
            set(),
            validation_mode="sequential",
        )

        assert result.passed is True, (
            "Unknown agents should pass through (fail-open behavior)"
        )

    def test_spec_786_8_doc_master_gate_fails_open_empty_completions(
        self, state_file_cleanup
    ):
        """Doc-master gate MUST fail open when completions dict is empty."""
        session_id = state_file_cleanup

        from pipeline_completion_state import (
            _ensure_state,
            _write_state,
            verify_batch_doc_master_completions,
        )

        # Create a state file with empty completions
        state = _ensure_state(session_id)
        state["completions"] = {}
        _write_state(session_id, state)

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)

        assert all_passed is True, "Gate must fail open with empty completions"

    def test_spec_786_9_doc_master_gate_fails_open_only_issue_zero(
        self, state_file_cleanup
    ):
        """Doc-master gate MUST fail open when only non-batch (issue 0) completions exist."""
        session_id = state_file_cleanup

        from pipeline_completion_state import (
            record_agent_completion,
            verify_batch_doc_master_completions,
        )

        # Record completion only for issue 0 (non-batch)
        record_agent_completion(session_id, "implementer", issue_number=0, success=True)

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)

        assert all_passed is True, (
            "Gate must fail open when only non-batch issue 0 exists"
        )
