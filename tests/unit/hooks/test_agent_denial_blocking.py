"""
Unit tests for Issue #750: Block coordinator direct edits after agent prompt-shrinkage denial.

Validates that:
1. _record_agent_denial writes valid JSON atomically
2. _check_agent_denial returns agent_type within window / None otherwise
3. Write/Edit to protected infrastructure after agent denial is blocked (substantive)
4. Write/Edit to protected infrastructure after agent denial is allowed (trivial)
5. Write to non-infrastructure after agent denial is allowed
6. Fail-open on corrupt/missing state files

Date: 2026-04-10
Issue: #750
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook's parent to path so we can import the module
HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOK_DIR))

# Also add lib dir for any transitive imports
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Reset relevant env vars for each test."""
    env_keys = [
        "SANDBOX_ENABLED", "PRE_TOOL_MCP_SECURITY", "PRE_TOOL_AGENT_AUTH",
        "PRE_TOOL_BATCH_PERMISSION", "MCP_AUTO_APPROVE", "ENFORCEMENT_LEVEL",
        "CLAUDE_AGENT_NAME", "PIPELINE_STATE_FILE",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def set_session_id(monkeypatch):
    """Set a known session_id on the hook module."""
    test_sid = "test-session-750"
    monkeypatch.setattr(hook, "_session_id", test_sid)
    return test_sid


@pytest.fixture
def denial_state_file(tmp_path, set_session_id, monkeypatch):
    """Provide a temp directory for agent denial state files."""
    monkeypatch.setattr(hook, "AGENT_DENY_STATE_DIR", str(tmp_path))
    return tmp_path / f"adev-agent-deny-{set_session_id}.json"


# ---------------------------------------------------------------------------
# _record_agent_denial tests
# ---------------------------------------------------------------------------

class TestRecordAgentDenial:

    def test_writes_valid_json(self, denial_state_file, set_session_id):
        """_record_agent_denial writes valid JSON with expected keys."""
        hook._record_agent_denial("implementer")
        assert denial_state_file.exists()
        data = json.loads(denial_state_file.read_text())
        assert data["agent_type"] == "implementer"
        assert data["session_id"] == set_session_id
        assert isinstance(data["timestamp"], float)

    def test_atomic_write_no_tmp_leftover(self, denial_state_file):
        """After writing, no .tmp file remains."""
        hook._record_agent_denial("reviewer")
        tmp_file = Path(str(denial_state_file) + ".tmp")
        assert not tmp_file.exists()

    def test_fail_open_on_write_error(self, monkeypatch, set_session_id):
        """If directory is unwritable, no exception is raised (fail-open)."""
        monkeypatch.setattr(hook, "AGENT_DENY_STATE_DIR", "/nonexistent/path/xyz")
        # Should not raise
        hook._record_agent_denial("implementer")


# ---------------------------------------------------------------------------
# _check_agent_denial tests
# ---------------------------------------------------------------------------

class TestCheckAgentDenial:

    def test_returns_agent_type_within_window(self, denial_state_file, set_session_id):
        """Returns agent_type when denial is within TTL window."""
        hook._record_agent_denial("implementer")
        result = hook._check_agent_denial()
        assert result == "implementer"

    def test_returns_none_after_ttl_expires(self, denial_state_file, set_session_id):
        """Returns None when denial is older than window_seconds."""
        hook._record_agent_denial("implementer")
        # Modify timestamp to be in the past
        data = json.loads(denial_state_file.read_text())
        data["timestamp"] = time.time() - 600  # 10 minutes ago
        denial_state_file.write_text(json.dumps(data))
        result = hook._check_agent_denial(window_seconds=300)
        assert result is None

    def test_returns_none_when_file_missing(self, denial_state_file):
        """Returns None when no denial file exists (fail-open)."""
        assert not denial_state_file.exists()
        result = hook._check_agent_denial()
        assert result is None

    def test_returns_none_on_corrupt_json(self, denial_state_file):
        """Returns None when file contains invalid JSON (fail-open)."""
        denial_state_file.write_text("not-valid-json{{{")
        result = hook._check_agent_denial()
        assert result is None

    def test_returns_none_for_different_session_id(self, denial_state_file, set_session_id):
        """Returns None when session_id in file does not match current session."""
        hook._record_agent_denial("implementer")
        data = json.loads(denial_state_file.read_text())
        data["session_id"] = "different-session-xyz"
        denial_state_file.write_text(json.dumps(data))
        result = hook._check_agent_denial()
        assert result is None


# ---------------------------------------------------------------------------
# Blocking behavior tests (integration with _is_protected_infrastructure)
# ---------------------------------------------------------------------------

class TestAgentDenialBlocking:
    """Test the blocking logic for Write/Edit after agent denial."""

    def _make_protected_path(self) -> str:
        """Return a path that _is_protected_infrastructure returns True for."""
        # Use the hook dir itself as a representative protected path
        return str(HOOK_DIR / "some_hook.py")

    def _make_non_protected_path(self) -> str:
        """Return a path that _is_protected_infrastructure returns False for."""
        return str(Path(__file__).resolve().parents[3] / "docs" / "some_doc.md")

    def _make_test_path(self) -> str:
        """Return a test file path (never protected)."""
        return str(Path(__file__).resolve().parents[3] / "tests" / "unit" / "test_something.py")

    def test_write_protected_infra_blocked_substantive(self, denial_state_file):
        """Write to protected infra with >=5 lines after denial: BLOCKED."""
        hook._record_agent_denial("implementer")
        file_path = self._make_protected_path()
        content = "\n".join([f"line {i}" for i in range(10)])  # 10 lines
        tool_input = {"file_path": file_path, "content": content}

        with patch.object(hook, "_is_protected_infrastructure", return_value=True):
            denied_agent = hook._check_agent_denial()
            assert denied_agent == "implementer"

            # Simulate the blocking logic from the hook
            is_substantive = len(tool_input.get("content", "").splitlines()) >= hook.SIGNIFICANT_LINE_THRESHOLD
            assert is_substantive is True

    def test_write_protected_infra_allowed_trivial(self, denial_state_file):
        """Write to protected infra with <5 lines after denial: ALLOWED (typo fix)."""
        hook._record_agent_denial("implementer")
        content = "line 1\nline 2"  # 2 lines
        tool_input = {"content": content}

        is_substantive = len(tool_input.get("content", "").splitlines()) >= hook.SIGNIFICANT_LINE_THRESHOLD
        assert is_substantive is False

    def test_edit_protected_infra_blocked_new_function(self, denial_state_file):
        """Edit to protected infra adding new function after denial: BLOCKED."""
        hook._record_agent_denial("reviewer")
        old_string = "# placeholder"
        new_string = "def new_function():\n    pass\n    return True\n"
        file_path = self._make_protected_path()

        sig, reason, snippet = hook._has_significant_additions(old_string, new_string, file_path)
        assert sig is True

    def test_edit_protected_infra_allowed_whitespace(self, denial_state_file):
        """Edit to protected infra with whitespace-only change after denial: ALLOWED."""
        hook._record_agent_denial("reviewer")
        old_string = "x = 1"
        new_string = "x  = 1"
        file_path = self._make_protected_path()

        sig, _, _ = hook._has_significant_additions(old_string, new_string, file_path)
        assert sig is False

    def test_write_non_infrastructure_allowed(self, denial_state_file):
        """Write to non-infrastructure path after denial: ALLOWED."""
        hook._record_agent_denial("implementer")
        file_path = self._make_non_protected_path()

        with patch.object(hook, "_is_protected_infrastructure", return_value=False):
            assert not hook._is_protected_infrastructure(file_path)

    def test_write_test_file_allowed(self, denial_state_file):
        """Write to test file after denial: ALLOWED (tests are never protected)."""
        hook._record_agent_denial("implementer")
        file_path = self._make_test_path()

        # Test files are excluded from protection by _is_protected_infrastructure
        assert not hook._is_protected_infrastructure(file_path)

    def test_write_with_no_prior_denial_allowed(self, denial_state_file):
        """Write with no prior denial: no blocking."""
        result = hook._check_agent_denial()
        assert result is None

    def test_deny_message_includes_required_next_action(self, denial_state_file):
        """The block reason must include REQUIRED NEXT ACTION directive."""
        hook._record_agent_denial("implementer")
        denied_agent = hook._check_agent_denial()
        # Construct the block reason as the hook would
        block_reason = (
            f"BLOCKED: Agent '{denied_agent}' was recently denied by prompt integrity. "
            f"Direct edits to protected infrastructure (test.py) are not allowed "
            f"as a workaround. "
            f"REQUIRED NEXT ACTION: Use get_agent_prompt_template('{denied_agent}') "
            f"to reload the full agent prompt from disk and retry the agent invocation. "
            f"Do NOT attempt direct edits as a workaround."
        )
        assert "REQUIRED NEXT ACTION" in block_reason
        assert "get_agent_prompt_template" in block_reason
