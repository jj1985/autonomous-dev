"""Regression tests for Issue #779: PIPELINE_ISSUE_NUMBER env var not persisting.

Problem: Claude Code's Bash tool does NOT persist shell environment variables
across separate Bash tool calls. When the coordinator runs
``export PIPELINE_ISSUE_NUMBER=771`` in one Bash call, that env var is gone in
the next Bash call. The hook reads ``os.getenv("PIPELINE_ISSUE_NUMBER", "0")``
but gets "0", causing ordering gate mismatches.

Fix: ``_get_current_issue_number()`` falls back to reading ``issue_number``
from ``/tmp/implement_pipeline_state.json`` when the env var is absent or "0".
"""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Path setup — add lib and hooks directories for imports
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

sys.path.insert(0, str(HOOKS_DIR))
sys.path.insert(0, str(LIB_DIR))


def _load_get_current_issue_number():
    """Import _get_current_issue_number from unified_pre_tool.

    We import the function fresh to avoid module-level side effects.
    """
    # Use importlib to get a clean import
    import importlib
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "unified_pre_tool",
        HOOKS_DIR / "unified_pre_tool.py",
    )
    module = importlib.util.module_from_spec(spec)

    # The module reads stdin at import time in some paths — suppress that
    with mock.patch("sys.stdin", new_callable=lambda: __import__("io").StringIO):
        try:
            spec.loader.exec_module(module)
        except (SystemExit, Exception):
            pass

    return module._get_current_issue_number


def _load_session_tracker_get_current_issue_number():
    """Import _get_current_issue_number from unified_session_tracker."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "unified_session_tracker",
        HOOKS_DIR / "unified_session_tracker.py",
    )
    module = importlib.util.module_from_spec(spec)

    with mock.patch("sys.stdin", new_callable=lambda: __import__("io").StringIO):
        try:
            spec.loader.exec_module(module)
        except (SystemExit, Exception):
            pass

    return module._get_current_issue_number


class TestGetCurrentIssueNumber:
    """Tests for _get_current_issue_number() in unified_pre_tool.py."""

    def test_env_var_takes_precedence(self, tmp_path, monkeypatch):
        """When PIPELINE_ISSUE_NUMBER env var is set, it takes precedence over file."""
        # Set up state file with different issue number
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 999}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.setenv("PIPELINE_ISSUE_NUMBER", "771")

        fn = _load_get_current_issue_number()
        assert fn() == 771

    def test_file_fallback_when_env_not_set(self, tmp_path, monkeypatch):
        """When env var is absent, reads issue_number from pipeline state file."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 771, "mode": "batch"}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 771

    def test_file_fallback_when_env_is_zero(self, tmp_path, monkeypatch):
        """When env var is '0' (default), falls back to file."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 42}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.setenv("PIPELINE_ISSUE_NUMBER", "0")

        fn = _load_get_current_issue_number()
        assert fn() == 42

    def test_returns_zero_when_neither_available(self, tmp_path, monkeypatch):
        """When neither env var nor file is available, returns 0."""
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(tmp_path / "nonexistent.json"))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 0

    def test_corrupt_state_file_returns_zero(self, tmp_path, monkeypatch):
        """Corrupt/invalid JSON in state file should fall open to 0."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text("not valid json {{{")
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 0

    def test_state_file_missing_issue_number_key(self, tmp_path, monkeypatch):
        """State file exists but lacks issue_number key — returns 0."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"mode": "full", "step": 5}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 0

    def test_state_file_issue_number_zero(self, tmp_path, monkeypatch):
        """State file has issue_number=0 — returns 0 (no issue context)."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 0}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 0

    def test_state_file_string_issue_number(self, tmp_path, monkeypatch):
        """State file has issue_number as string — handles gracefully."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": "771"}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 771

    def test_invalid_env_var_falls_to_file(self, tmp_path, monkeypatch):
        """Non-numeric env var falls back to file."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 555}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.setenv("PIPELINE_ISSUE_NUMBER", "not_a_number")

        fn = _load_get_current_issue_number()
        assert fn() == 555


class TestSessionTrackerIssueNumber:
    """Tests for _get_current_issue_number() in unified_session_tracker.py."""

    def test_env_var_takes_precedence(self, tmp_path, monkeypatch):
        """Session tracker also respects env var first."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 999}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.setenv("PIPELINE_ISSUE_NUMBER", "123")

        fn = _load_session_tracker_get_current_issue_number()
        assert fn() == 123

    def test_file_fallback_when_env_not_set(self, tmp_path, monkeypatch):
        """Session tracker falls back to file when env var absent."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 456}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_session_tracker_get_current_issue_number()
        assert fn() == 456

    def test_returns_zero_when_neither_available(self, tmp_path, monkeypatch):
        """Session tracker returns 0 when no source available."""
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(tmp_path / "nope.json"))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_session_tracker_get_current_issue_number()
        assert fn() == 0
