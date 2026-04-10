"""Security regression tests for Issue #752: session_id path traversal prevention.

CWE-22: Improper Limitation of a Pathname to a Restricted Directory
OWASP A01:2021: Broken Access Control

These tests verify that crafted session_id values with '../' sequences cannot
write denial-state files to arbitrary filesystem paths.

Date: 2026-04-10
Issue: #752
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Add hook dir to path
REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOK_DIR))

import unified_pre_tool as hook


class TestSessionIdTraversalPrevention:
    """End-to-end tests verifying session_id cannot escape the base directory."""

    @pytest.mark.parametrize("malicious_id", [
        "../../etc/passwd",
        "../../../evil",
        "valid/../../../evil",
        "..%2f..%2f",          # URL-encoded (NFKC normalization handles these)
        "../etc/shadow",
        "/etc/cron.d/evil",
        "../../tmp/evil",
    ])
    def test_session_id_traversal_cannot_escape_base_dir(self, tmp_path, monkeypatch, malicious_id):
        """End-to-end: crafted session_id values do not escape the base directory.

        This is the primary regression test for CWE-22 (Issue #752).
        """
        monkeypatch.setattr(hook, "AGENT_DENY_STATE_DIR", str(tmp_path))
        monkeypatch.setattr(hook, "_session_id", malicious_id)

        # Should not raise and must not write outside tmp_path
        hook._record_agent_denial("implementer")

        # Verify nothing escaped to parent directories
        parent = tmp_path.parent
        # Check the parent for unexpected new files (allow the tmp_path dir itself)
        for item in parent.iterdir():
            if item == tmp_path:
                continue
            assert not item.name.startswith("adev-agent-deny-"), (
                f"Denial state file escaped to parent directory: {item}"
            )
            assert not item.name.startswith("evil"), (
                f"Traversal payload escaped to: {item}"
            )

    def test_session_id_null_byte_injection_prevented(self):
        """Null bytes in session_id are stripped before any path construction."""
        # Test with null byte embedded in what looks like a valid session_id
        result = hook._sanitize_session_id("valid\x00../../evil")
        assert "\x00" not in result
        assert ".." not in result
        assert "/" not in result

    def test_session_id_sanitized_at_main_assignment(self, tmp_path, monkeypatch):
        """After sanitization, _session_id contains only safe characters.

        This verifies the defense-in-depth at the point of assignment.
        The actual main() assignment uses _sanitize_session_id(), but we verify
        the function contract here since we cannot easily invoke main() in tests.
        """
        malicious = "../../etc/passwd"
        safe = hook._sanitize_session_id(malicious)
        # Must only contain safe chars
        import re
        assert re.match(r'^[a-zA-Z0-9_-]+$', safe), (
            f"Sanitized session_id contains unsafe characters: {safe!r}"
        )

    def test_denial_state_file_atomic_creation(self, tmp_path, monkeypatch):
        """Denial state files are created atomically; no predictable .tmp file remains."""
        test_sid = "atomic-test-752"
        monkeypatch.setattr(hook, "AGENT_DENY_STATE_DIR", str(tmp_path))
        monkeypatch.setattr(hook, "_session_id", test_sid)

        hook._record_agent_denial("implementer")

        # The predictable .tmp file must not remain after write
        predictable_tmp = tmp_path / f"adev-agent-deny-{test_sid}.json.tmp"
        assert not predictable_tmp.exists(), (
            "Predictable .tmp file must not remain (use mkstemp for atomic creation)"
        )
        # Verify the actual file was created correctly
        state_file = tmp_path / f"adev-agent-deny-{test_sid}.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["agent_type"] == "implementer"
        assert data["session_id"] == test_sid

    def test_path_confinement_catches_bypass(self, tmp_path, monkeypatch):
        """Double-defense: even with a traversal session_id the confinement check rejects it.

        This tests the second layer of defense — even if sanitization somehow failed,
        os.path.realpath confinement would catch any escape attempt.
        """
        monkeypatch.setattr(hook, "AGENT_DENY_STATE_DIR", str(tmp_path))
        # Simulate a somehow-unsanitized traversal reaching path construction
        # by setting _session_id directly to a traversal value
        monkeypatch.setattr(hook, "_session_id", "../../evil_bypass")

        # _check_agent_denial with traversal session_id must return None, not read/raise
        result = hook._check_agent_denial()
        assert result is None, (
            "_check_agent_denial must return None for traversal session_id (confinement check)"
        )

        # _record_agent_denial must not write outside tmp_path
        hook._record_agent_denial("implementer")
        for item in tmp_path.parent.iterdir():
            if item == tmp_path:
                continue
            assert "evil" not in item.name.lower(), (
                f"Traversal bypass succeeded — file escaped to: {item}"
            )
