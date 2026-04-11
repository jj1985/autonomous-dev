"""
Tests for verify_batch_doc_master_completions() in pipeline_completion_state.py.

Issue: #786
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
    record_agent_completion,
    verify_batch_doc_master_completions,
)


@pytest.fixture()
def session_id():
    """Unique session ID for test isolation."""
    return f"test_dm_session_{os.getpid()}_{time.time_ns()}"


@pytest.fixture(autouse=True)
def cleanup_state(session_id):
    """Clean up state file after each test."""
    clear_session("unknown")
    yield
    clear_session(session_id)
    clear_session("unknown")


class TestVerifyBatchDocMasterCompletions:
    """Tests for verify_batch_doc_master_completions()."""

    def test_no_state_file_fails_open(self, session_id):
        """When there is no state file, fail-open (all passed)."""
        # session_id has no state file; should return True with empty lists
        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True
        assert with_dm == []
        assert missing_dm == []

    def test_all_batch_issues_have_doc_master(self, session_id):
        """When all batch issues have doc-master, returns True."""
        record_agent_completion(session_id, "doc-master", issue_number=10)
        record_agent_completion(session_id, "doc-master", issue_number=20)

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True
        assert sorted(with_dm) == [10, 20]
        assert missing_dm == []

    def test_some_batch_issues_missing_doc_master(self, session_id):
        """When some batch issues are missing doc-master, returns False with missing list."""
        record_agent_completion(session_id, "doc-master", issue_number=10)
        # issue 20 has implementer but not doc-master
        record_agent_completion(session_id, "implementer", issue_number=20)

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is False
        assert 10 in with_dm
        assert 20 in missing_dm

    def test_all_batch_issues_missing_doc_master(self, session_id):
        """When no batch issues have doc-master, returns False."""
        record_agent_completion(session_id, "implementer", issue_number=5)
        record_agent_completion(session_id, "implementer", issue_number=6)

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is False
        assert 5 in missing_dm
        assert 6 in missing_dm
        assert with_dm == []

    def test_skip_env_var_bypasses_gate(self, session_id, monkeypatch):
        """SKIP_BATCH_DOC_MASTER_GATE=1 bypasses the gate and returns True."""
        record_agent_completion(session_id, "implementer", issue_number=99)
        monkeypatch.setenv("SKIP_BATCH_DOC_MASTER_GATE", "1")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True
        assert with_dm == []
        assert missing_dm == []

    def test_skip_env_var_true_string(self, session_id, monkeypatch):
        """SKIP_BATCH_DOC_MASTER_GATE=true also bypasses the gate."""
        record_agent_completion(session_id, "implementer", issue_number=99)
        monkeypatch.setenv("SKIP_BATCH_DOC_MASTER_GATE", "true")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True

    def test_zero_key_issue_skipped(self, session_id):
        """Issue key '0' (non-batch pipeline) is skipped."""
        record_agent_completion(session_id, "implementer", issue_number=0)
        # Only "0" key present — fail-open
        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True
        assert with_dm == []
        assert missing_dm == []

    def test_fail_open_on_corrupt_state(self, session_id, tmp_path, monkeypatch):
        """Corrupt state file causes fail-open (True returned)."""
        state_path = _state_file_path(session_id)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("NOT VALID JSON")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True
