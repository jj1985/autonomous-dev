"""Spec validation tests for Issue #862: Pipeline state contamination.

Bug: _get_current_issue_number() and _get_pipeline_mode_from_state() read from a
shared state file without checking session_id, causing stale data from other
sessions to contaminate ordering enforcement.

Acceptance criteria:
1. _get_current_issue_number() returns 0 when state file belongs to a different session
2. _get_pipeline_mode_from_state() returns "full" when state file belongs to a different session
3. Both functions return correct values when state file belongs to current session (no regression)
4. The "unknown" session_id gap is documented in _is_stale_session() docstring
5. All existing tests in tests/unit/hooks/test_stale_pipeline_state.py continue to pass
6. PIPELINE_ISSUE_NUMBER env var still takes precedence over file-based lookup
"""

from __future__ import annotations

import inspect
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool


def _write_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state))


def _make_state(session_id: str, issue_number: int = 42, mode: str = "fix") -> dict:
    return {
        "session_start": datetime.now().isoformat(),
        "mode": mode,
        "run_id": "test-run",
        "session_id": session_id,
        "issue_number": issue_number,
        "step": "implement",
    }


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)
    monkeypatch.delenv("PIPELINE_STATE_FILE", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    sf = tmp_path / "implement_pipeline_state.json"
    monkeypatch.setenv("PIPELINE_STATE_FILE", str(sf))
    return sf


def test_spec_862_1_issue_number_returns_0_for_different_session(state_file, monkeypatch):
    _write_state(state_file, _make_state("session-old", issue_number=99))
    monkeypatch.setattr(unified_pre_tool, "_session_id", "session-new")
    result = unified_pre_tool._get_current_issue_number()
    assert result == 0, f"Expected 0 for stale session, got {result}"


def test_spec_862_2_pipeline_mode_returns_full_for_different_session(state_file, monkeypatch):
    _write_state(state_file, _make_state("session-old", mode="fix"))
    monkeypatch.setattr(unified_pre_tool, "_session_id", "session-new")
    result = unified_pre_tool._get_pipeline_mode_from_state()
    assert result == "full", f"Expected full for stale session, got {result!r}"


def test_spec_862_3a_issue_number_correct_for_current_session(state_file, monkeypatch):
    monkeypatch.setattr(unified_pre_tool, "_session_id", "session-current")
    _write_state(state_file, _make_state("session-current", issue_number=123))
    result = unified_pre_tool._get_current_issue_number()
    assert result == 123, f"Expected 123 for current session, got {result}"


def test_spec_862_3b_pipeline_mode_correct_for_current_session(state_file, monkeypatch):
    monkeypatch.setattr(unified_pre_tool, "_session_id", "session-current")
    _write_state(state_file, _make_state("session-current", mode="light"))
    result = unified_pre_tool._get_pipeline_mode_from_state()
    assert result == "light", f"Expected light for current session, got {result!r}"


def test_spec_862_4_unknown_session_id_documented():
    docstring = inspect.getdoc(unified_pre_tool._is_stale_session)
    assert docstring is not None, "_is_stale_session() has no docstring"
    assert "unknown" in docstring.lower(), "Docstring does not document the unknown session_id gap"


def test_spec_862_5_existing_stale_tests_exist():
    test_file = REPO_ROOT / "tests" / "unit" / "hooks" / "test_stale_pipeline_state.py"
    assert test_file.exists(), f"Expected existing test file at {test_file}"


def test_spec_862_6_env_var_takes_precedence_over_stale_file(state_file, monkeypatch):
    _write_state(state_file, _make_state("session-old", issue_number=99))
    monkeypatch.setattr(unified_pre_tool, "_session_id", "session-new")
    monkeypatch.setenv("PIPELINE_ISSUE_NUMBER", "555")
    result = unified_pre_tool._get_current_issue_number()
    assert result == 555, f"Expected env var value 555 to take precedence, got {result}"
