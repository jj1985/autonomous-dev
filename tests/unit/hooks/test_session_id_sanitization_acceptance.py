"""Acceptance tests for Issue #752: Sanitize session_id in agent denial state file path construction.

These tests verify the acceptance criteria from the implementation plan.
They are static inspection tests (no LLM calls) and belong in tests/unit/.
"""

import importlib
import inspect
import os
import re
import sys
import textwrap

import pytest

# Import the hook module
WORKTREE = os.environ.get(
    "WORKTREE_PATH",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
)
HOOK_PATH = os.path.join(WORKTREE, "plugins", "autonomous-dev", "hooks")
sys.path.insert(0, HOOK_PATH)


def _read_hook_source() -> str:
    """Read the unified_pre_tool.py source code."""
    path = os.path.join(HOOK_PATH, "unified_pre_tool.py")
    with open(path) as f:
        return f.read()


class TestAcceptanceCriteria752:
    """Acceptance criteria from Issue #752 implementation plan."""

    def test_ac1_sanitize_function_exists(self):
        """AC1: _sanitize_session_id() function exists in unified_pre_tool.py."""
        source = _read_hook_source()
        assert "def _sanitize_session_id" in source, (
            "_sanitize_session_id() function must exist in unified_pre_tool.py"
        )

    def test_ac1_sanitize_strips_null_bytes(self):
        """AC1: _sanitize_session_id() strips null bytes."""
        source = _read_hook_source()
        # Check for null byte handling (replace or strip)
        assert r"\x00" in source or "\\x00" in source or "null" in source.lower(), (
            "_sanitize_session_id must handle null bytes"
        )

    def test_ac1_sanitize_has_allowlist_regex(self):
        """AC1: _sanitize_session_id() uses allowlist regex."""
        source = _read_hook_source()
        # Must have an allowlist pattern that replaces non-safe chars
        assert re.search(r"re\.sub\(r'\[\^a-zA-Z0-9", source), (
            "_sanitize_session_id must use allowlist regex via re.sub"
        )

    def test_ac1_sanitize_caps_length(self):
        """AC1: _sanitize_session_id() caps length at 128 characters."""
        source = _read_hook_source()
        assert "128" in source, (
            "_sanitize_session_id must cap session_id length (128 expected)"
        )

    def test_ac2_session_id_sanitized_at_assignment(self):
        """AC2: _session_id is sanitized at point of assignment in main()."""
        source = _read_hook_source()
        # The assignment should call _sanitize_session_id
        assert re.search(r"_session_id\s*=\s*_sanitize_session_id\(", source), (
            "_session_id must be assigned via _sanitize_session_id() call"
        )

    def test_ac3_record_denial_has_path_confinement(self):
        """AC3: _record_agent_denial() includes path confinement verification."""
        source = _read_hook_source()
        # Find the _record_agent_denial function and check for realpath/confinement
        match = re.search(r"def _record_agent_denial\(.*?\n(?:.*?\n)*?(?=\ndef |\Z)", source)
        assert match, "_record_agent_denial function must exist"
        func_body = match.group(0)
        assert "realpath" in func_body or "commonpath" in func_body, (
            "_record_agent_denial must include path confinement check (realpath or commonpath)"
        )

    def test_ac3_check_denial_has_path_confinement(self):
        """AC3: _check_agent_denial() includes path confinement verification."""
        source = _read_hook_source()
        match = re.search(r"def _check_agent_denial\(.*?\n(?:.*?\n)*?(?=\ndef |\Z)", source)
        assert match, "_check_agent_denial function must exist"
        func_body = match.group(0)
        assert "realpath" in func_body or "commonpath" in func_body, (
            "_check_agent_denial must include path confinement check (realpath or commonpath)"
        )

    def test_ac4_record_denial_uses_mkstemp(self):
        """AC4: _record_agent_denial() uses tempfile.mkstemp() for atomic file creation."""
        source = _read_hook_source()
        match = re.search(r"def _record_agent_denial\(.*?\n(?:.*?\n)*?(?=\ndef |\Z)", source)
        assert match, "_record_agent_denial function must exist"
        func_body = match.group(0)
        assert "mkstemp" in func_body, (
            "_record_agent_denial must use tempfile.mkstemp() instead of predictable .tmp suffix"
        )

    def test_ac9_fail_open_preserved(self):
        """AC9: Fail-open contract preserved — exceptions don't cause hook to block."""
        source = _read_hook_source()
        # Both functions should still have except Exception handling
        for func_name in ["_record_agent_denial", "_check_agent_denial"]:
            match = re.search(rf"def {func_name}\(.*?\n(?:.*?\n)*?(?=\ndef |\Z)", source)
            assert match, f"{func_name} function must exist"
            func_body = match.group(0)
            assert "except" in func_body, (
                f"{func_name} must preserve fail-open exception handling"
            )

    def test_ac5_no_predictable_tmp_path(self):
        """AC5: No predictable .tmp file path construction in _record_agent_denial."""
        source = _read_hook_source()
        match = re.search(r"def _record_agent_denial\(.*?\n(?:.*?\n)*?(?=\ndef |\Z)", source)
        assert match, "_record_agent_denial function must exist"
        func_body = match.group(0)
        # Should NOT have the old pattern: state_path + ".tmp"
        assert 'state_path + ".tmp"' not in func_body and "state_path + '.tmp'" not in func_body, (
            "_record_agent_denial must not use predictable state_path + '.tmp' pattern"
        )
