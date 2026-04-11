"""Spec-validation tests for Issue #779.

Feature: PIPELINE_ISSUE_NUMBER env var does not persist across Bash calls.
Fix: _get_current_issue_number() helper falls back to reading issue_number
from the pipeline state file when the env var is not set.

Acceptance criteria:
1. When env var is set, it takes precedence over file
2. When env var is not set, falls back to pipeline state file
3. When neither available, returns 0 (fail-open)
4. Both hooks (unified_pre_tool.py and unified_session_tracker.py) use the helper
"""

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_WORKTREE = Path(__file__).resolve().parents[2]
_HOOKS = _WORKTREE / "plugins" / "autonomous-dev" / "hooks"


def _import_hook_module(module_name: str):
    """Import a hook module by name, handling sys.path and import issues."""
    if str(_HOOKS) not in sys.path:
        sys.path.insert(0, str(_HOOKS))
    # Force re-import to get fresh module
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name, _HOOKS / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        # Some hooks have import-time side effects; we only need the function
        pass
    return module


# ---------------------------------------------------------------------------
# Load both helper functions
# ---------------------------------------------------------------------------

def _get_pre_tool_helper():
    """Get _get_current_issue_number from unified_pre_tool."""
    mod = _import_hook_module("unified_pre_tool")
    return mod._get_current_issue_number


def _get_session_tracker_helper():
    """Get _get_current_issue_number from unified_session_tracker."""
    mod = _import_hook_module("unified_session_tracker")
    return mod._get_current_issue_number


# ---------------------------------------------------------------------------
# Criterion 1: Env var takes precedence over file
# ---------------------------------------------------------------------------

class TestEnvVarPrecedence:
    """When PIPELINE_ISSUE_NUMBER env var is set, it takes precedence."""

    def test_spec_issue779_1a_env_var_precedence_pre_tool(self, tmp_path):
        """Env var value is returned even when state file also has a value."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 999}))

        fn = _get_pre_tool_helper()
        env = {
            "PIPELINE_ISSUE_NUMBER": "42",
            "PIPELINE_STATE_FILE": str(state_file),
        }
        with patch.dict(os.environ, env, clear=False):
            result = fn()

        assert result == 42, f"Expected 42 from env var, got {result}"

    def test_spec_issue779_1b_env_var_precedence_session_tracker(self, tmp_path):
        """Same test for unified_session_tracker."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 999}))

        fn = _get_session_tracker_helper()
        env = {
            "PIPELINE_ISSUE_NUMBER": "42",
            "PIPELINE_STATE_FILE": str(state_file),
        }
        with patch.dict(os.environ, env, clear=False):
            result = fn()

        assert result == 42, f"Expected 42 from env var, got {result}"


# ---------------------------------------------------------------------------
# Criterion 2: Falls back to pipeline state file when env var not set
# ---------------------------------------------------------------------------

class TestFileFallback:
    """When env var is not set, reads from pipeline state file."""

    def test_spec_issue779_2a_file_fallback_pre_tool(self, tmp_path):
        """Returns issue_number from state file when env var absent."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 779}))

        fn = _get_pre_tool_helper()
        env = {"PIPELINE_STATE_FILE": str(state_file)}
        remove_keys = ["PIPELINE_ISSUE_NUMBER"]
        with patch.dict(os.environ, env, clear=False):
            # Ensure env var is not set
            os.environ.pop("PIPELINE_ISSUE_NUMBER", None)
            result = fn()

        assert result == 779, f"Expected 779 from state file, got {result}"

    def test_spec_issue779_2b_file_fallback_session_tracker(self, tmp_path):
        """Returns issue_number from state file when env var absent."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": 779}))

        fn = _get_session_tracker_helper()
        env = {"PIPELINE_STATE_FILE": str(state_file)}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("PIPELINE_ISSUE_NUMBER", None)
            result = fn()

        assert result == 779, f"Expected 779 from state file, got {result}"

    def test_spec_issue779_2c_file_fallback_string_issue_number(self, tmp_path):
        """State file with string issue_number should also work."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"issue_number": "123"}))

        fn = _get_pre_tool_helper()
        env = {"PIPELINE_STATE_FILE": str(state_file)}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("PIPELINE_ISSUE_NUMBER", None)
            result = fn()

        assert result == 123, f"Expected 123 from string in state file, got {result}"


# ---------------------------------------------------------------------------
# Criterion 3: Returns 0 when neither is available (fail-open)
# ---------------------------------------------------------------------------

class TestFailOpen:
    """When neither env var nor file is available, returns 0."""

    def test_spec_issue779_3a_neither_available_pre_tool(self, tmp_path):
        """Returns 0 when no env var and no state file."""
        nonexistent = tmp_path / "does_not_exist.json"

        fn = _get_pre_tool_helper()
        env = {"PIPELINE_STATE_FILE": str(nonexistent)}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("PIPELINE_ISSUE_NUMBER", None)
            result = fn()

        assert result == 0, f"Expected 0 (fail-open), got {result}"

    def test_spec_issue779_3b_neither_available_session_tracker(self, tmp_path):
        """Returns 0 when no env var and no state file."""
        nonexistent = tmp_path / "does_not_exist.json"

        fn = _get_session_tracker_helper()
        env = {"PIPELINE_STATE_FILE": str(nonexistent)}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("PIPELINE_ISSUE_NUMBER", None)
            result = fn()

        assert result == 0, f"Expected 0 (fail-open), got {result}"

    def test_spec_issue779_3c_corrupt_state_file_pre_tool(self, tmp_path):
        """Returns 0 when state file exists but is corrupt JSON."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text("not valid json {{{")

        fn = _get_pre_tool_helper()
        env = {"PIPELINE_STATE_FILE": str(state_file)}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("PIPELINE_ISSUE_NUMBER", None)
            result = fn()

        assert result == 0, f"Expected 0 for corrupt file, got {result}"


# ---------------------------------------------------------------------------
# Criterion 4: Both hooks use the helper
# ---------------------------------------------------------------------------

class TestBothHooksUseHelper:
    """Both unified_pre_tool.py and unified_session_tracker.py define
    and use _get_current_issue_number."""

    def test_spec_issue779_4a_pre_tool_has_helper(self):
        """unified_pre_tool.py exposes _get_current_issue_number."""
        mod = _import_hook_module("unified_pre_tool")
        assert hasattr(mod, "_get_current_issue_number"), (
            "unified_pre_tool.py must define _get_current_issue_number"
        )
        assert callable(mod._get_current_issue_number)

    def test_spec_issue779_4b_session_tracker_has_helper(self):
        """unified_session_tracker.py exposes _get_current_issue_number."""
        mod = _import_hook_module("unified_session_tracker")
        assert hasattr(mod, "_get_current_issue_number"), (
            "unified_session_tracker.py must define _get_current_issue_number"
        )
        assert callable(mod._get_current_issue_number)

    def test_spec_issue779_4c_pre_tool_calls_helper(self):
        """unified_pre_tool.py references _get_current_issue_number in its code."""
        source = (_HOOKS / "unified_pre_tool.py").read_text()
        # Should be called somewhere beyond just its definition
        call_count = source.count("_get_current_issue_number()")
        # At least 1 definition + 1 call = 2 occurrences with parens
        assert call_count >= 2, (
            f"Expected _get_current_issue_number() to be called at least once "
            f"beyond its definition, found {call_count} total occurrences"
        )

    def test_spec_issue779_4d_session_tracker_calls_helper(self):
        """unified_session_tracker.py references _get_current_issue_number in its code."""
        source = (_HOOKS / "unified_session_tracker.py").read_text()
        call_count = source.count("_get_current_issue_number()")
        assert call_count >= 2, (
            f"Expected _get_current_issue_number() to be called at least once "
            f"beyond its definition, found {call_count} total occurrences"
        )
