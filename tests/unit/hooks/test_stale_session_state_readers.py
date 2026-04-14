"""Regression tests for Issue #862: pipeline state contamination.

Validates that _get_current_issue_number() and _get_pipeline_mode_from_state()
correctly ignore stale state files from other sessions, preventing false ordering
blocks caused by a stale issue_number leaking across session boundaries.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add hook directory to path
HOOK_DIR = str(
    Path(__file__).resolve().parents[3]
    / "plugins"
    / "autonomous-dev"
    / "hooks"
)
if HOOK_DIR not in sys.path:
    sys.path.insert(0, HOOK_DIR)

import unified_pre_tool


def _write_state_file(path: Path, state: dict) -> None:
    """Write pipeline state JSON file."""
    path.write_text(json.dumps(state))


def _make_state(
    session_id: str = "session-A",
    issue_number: int = 0,
    mode: str = "full",
) -> dict:
    """Create a pipeline state dict with the given fields."""
    state: dict = {
        "session_start": datetime.now().isoformat(),
        "mode": mode,
        "run_id": "test-run",
        "explicitly_invoked": True,
        "session_id": session_id,
    }
    if issue_number:
        state["issue_number"] = issue_number
    return state


class TestGetCurrentIssueNumberStaleness:
    """Regression tests for _get_current_issue_number() staleness guard (Issue #862)."""

    def test_get_current_issue_number_returns_0_for_stale_session(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """State file has session-A, current is session-B -> returns 0 (stale)."""
        state_path = tmp_path / "state.json"
        state = _make_state(session_id="session-A", issue_number=42)
        _write_state_file(state_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "session-B")
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        result = unified_pre_tool._get_current_issue_number()

        assert result == 0, (
            f"Expected 0 (stale session default) but got {result!r}. "
            "Stale state file from session-A should not contaminate session-B."
        )

    def test_get_current_issue_number_returns_value_for_current_session(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """State file has session-A, issue_number=42, current is session-A -> returns 42."""
        state_path = tmp_path / "state.json"
        state = _make_state(session_id="session-A", issue_number=42)
        _write_state_file(state_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "session-A")
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        result = unified_pre_tool._get_current_issue_number()

        assert result == 42

    def test_get_current_issue_number_unknown_session_reads_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """State file has session_id='unknown' -> accepted gap, reads issue_number from state."""
        state_path = tmp_path / "state.json"
        state = _make_state(session_id="unknown", issue_number=99)
        _write_state_file(state_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "session-B")
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        result = unified_pre_tool._get_current_issue_number()

        # When stored session_id is "unknown", _is_stale_session returns False
        # (indeterminate), so the function falls through and reads the state value.
        assert result == 99, (
            "When stored session_id is 'unknown', the function should read from "
            "state (accepted gap — TTL guard is the secondary protection)."
        )

    def test_env_var_takes_precedence_over_stale_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PIPELINE_ISSUE_NUMBER env var wins even when stale state file is present."""
        state_path = tmp_path / "state.json"
        # Stale state with a different issue number
        state = _make_state(session_id="session-A", issue_number=999)
        _write_state_file(state_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "session-B")
        monkeypatch.setenv("PIPELINE_ISSUE_NUMBER", "123")

        result = unified_pre_tool._get_current_issue_number()

        assert result == 123, (
            "PIPELINE_ISSUE_NUMBER env var must take precedence over the state file "
            "(stale or not)."
        )


class TestGetPipelineModeFromStateStaleness:
    """Regression tests for _get_pipeline_mode_from_state() staleness guard (Issue #862)."""

    def test_get_pipeline_mode_returns_full_for_stale_session(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """State file has session-A with mode='fix', current is session-B -> returns 'full'."""
        state_path = tmp_path / "state.json"
        state = _make_state(session_id="session-A", mode="fix")
        _write_state_file(state_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "session-B")

        result = unified_pre_tool._get_pipeline_mode_from_state()

        assert result == "full", (
            f"Expected 'full' (stale session default) but got {result!r}. "
            "Stale state file from session-A should not contaminate session-B."
        )

    def test_get_pipeline_mode_returns_mode_for_current_session(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """State file has session-A with mode='fix', current is session-A -> returns 'fix'."""
        state_path = tmp_path / "state.json"
        state = _make_state(session_id="session-A", mode="fix")
        _write_state_file(state_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "session-A")

        result = unified_pre_tool._get_pipeline_mode_from_state()

        assert result == "fix"

    def test_get_pipeline_mode_unknown_session_reads_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """State file has session_id='unknown' with mode='fix' -> reads mode from state."""
        state_path = tmp_path / "state.json"
        state = _make_state(session_id="unknown", mode="fix")
        _write_state_file(state_path, state)

        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "session-B")

        result = unified_pre_tool._get_pipeline_mode_from_state()

        # When stored session_id is "unknown", _is_stale_session returns False
        # (indeterminate), so the function falls through and reads the state value.
        assert result == "fix", (
            "When stored session_id is 'unknown', the function should read from "
            "state (accepted gap — TTL guard is the secondary protection)."
        )
