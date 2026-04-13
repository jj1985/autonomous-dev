"""
Tests for record_doc_verdict() and verdict-aware verify_batch_doc_master_completions().

Verifies that doc-master verdicts are recorded, persisted, and enforced
at the batch doc-master gate. Issues where doc-master ran but produced
no valid verdict (MISSING/SHALLOW) are treated as incomplete.

Issue: #837
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
    _read_state,
    _state_file_path,
    clear_session,
    record_agent_completion,
    record_doc_verdict,
    verify_batch_doc_master_completions,
)


@pytest.fixture()
def session_id():
    """Unique session ID for test isolation."""
    return f"test_verdict_session_{os.getpid()}_{time.time_ns()}"


@pytest.fixture(autouse=True)
def cleanup_state(session_id):
    """Clean up state file after each test."""
    clear_session("unknown")
    yield
    clear_session(session_id)
    clear_session("unknown")


class TestRecordDocVerdict:
    """Tests for record_doc_verdict()."""

    def test_verdict_recorded_and_retrievable(self, session_id):
        """record_doc_verdict persists verdict to state file."""
        record_doc_verdict(session_id, 42, "PASS")

        state = _read_state(session_id)
        assert state["completions"]["42"]["doc-master-verdict"] == "PASS"

    def test_verdict_does_not_overwrite_completion(self, session_id):
        """Recording verdict does not affect doc-master completion flag."""
        record_agent_completion(session_id, "doc-master", issue_number=10)
        record_doc_verdict(session_id, 10, "FAIL")

        state = _read_state(session_id)
        assert state["completions"]["10"]["doc-master"] is True
        assert state["completions"]["10"]["doc-master-verdict"] == "FAIL"

    def test_multiple_issues_independent_verdicts(self, session_id):
        """Each issue can have its own verdict."""
        record_doc_verdict(session_id, 1, "PASS")
        record_doc_verdict(session_id, 2, "FAIL")
        record_doc_verdict(session_id, 3, "MISSING")

        state = _read_state(session_id)
        assert state["completions"]["1"]["doc-master-verdict"] == "PASS"
        assert state["completions"]["2"]["doc-master-verdict"] == "FAIL"
        assert state["completions"]["3"]["doc-master-verdict"] == "MISSING"


class TestVerifyWithVerdicts:
    """Tests for verdict-aware verify_batch_doc_master_completions()."""

    def test_passes_when_completion_and_valid_verdict_present(self, session_id):
        """All issues have doc-master completion AND valid verdict -> pass."""
        record_agent_completion(session_id, "doc-master", issue_number=10)
        record_doc_verdict(session_id, 10, "PASS")
        record_agent_completion(session_id, "doc-master", issue_number=20)
        record_doc_verdict(session_id, 20, "DOCS-UPDATED")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True
        assert sorted(with_dm) == [10, 20]
        assert missing_dm == []

    def test_fails_when_completion_exists_but_verdict_missing(self, session_id):
        """Doc-master completed but verdict is MISSING -> treated as incomplete."""
        record_agent_completion(session_id, "doc-master", issue_number=10)
        record_doc_verdict(session_id, 10, "PASS")
        record_agent_completion(session_id, "doc-master", issue_number=20)
        record_doc_verdict(session_id, 20, "MISSING")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is False
        assert 10 in with_dm
        assert 20 in missing_dm

    def test_fails_when_verdict_is_shallow(self, session_id):
        """SHALLOW verdict treated as invalid/incomplete."""
        record_agent_completion(session_id, "doc-master", issue_number=5)
        record_doc_verdict(session_id, 5, "SHALLOW")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is False
        assert 5 in missing_dm

    def test_backward_compat_no_verdict_field_passes(self, session_id):
        """Old state without verdict field passes through (fail-open)."""
        # Simulate old-style state: doc-master completed, no verdict recorded
        record_agent_completion(session_id, "doc-master", issue_number=10)
        record_agent_completion(session_id, "doc-master", issue_number=20)
        # No record_doc_verdict call — simulates old state

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True
        assert sorted(with_dm) == [10, 20]
        assert missing_dm == []

    def test_pass_verdict_treated_as_present(self, session_id):
        """PASS verdict is valid."""
        record_agent_completion(session_id, "doc-master", issue_number=1)
        record_doc_verdict(session_id, 1, "PASS")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True
        assert with_dm == [1]

    def test_fail_verdict_treated_as_present(self, session_id):
        """FAIL verdict is valid (doc-master ran and produced a real verdict)."""
        record_agent_completion(session_id, "doc-master", issue_number=1)
        record_doc_verdict(session_id, 1, "FAIL")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True
        assert with_dm == [1]

    def test_docs_updated_verdict_treated_as_present(self, session_id):
        """DOCS-UPDATED verdict is valid."""
        record_agent_completion(session_id, "doc-master", issue_number=1)
        record_doc_verdict(session_id, 1, "DOCS-UPDATED")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True

    def test_no_update_needed_verdict_treated_as_present(self, session_id):
        """NO-UPDATE-NEEDED verdict is valid."""
        record_agent_completion(session_id, "doc-master", issue_number=1)
        record_doc_verdict(session_id, 1, "NO-UPDATE-NEEDED")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True

    def test_docs_drift_found_verdict_treated_as_present(self, session_id):
        """DOCS-DRIFT-FOUND verdict is valid."""
        record_agent_completion(session_id, "doc-master", issue_number=1)
        record_doc_verdict(session_id, 1, "DOCS-DRIFT-FOUND")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True

    def test_skip_env_var_bypasses_verdict_check(self, session_id, monkeypatch):
        """SKIP_BATCH_DOC_MASTER_GATE=1 bypasses even with invalid verdict."""
        monkeypatch.setenv("SKIP_BATCH_DOC_MASTER_GATE", "1")
        record_agent_completion(session_id, "doc-master", issue_number=10)
        record_doc_verdict(session_id, 10, "SHALLOW")

        all_passed, with_dm, missing_dm = verify_batch_doc_master_completions(session_id)
        assert all_passed is True
        assert with_dm == []
        assert missing_dm == []
