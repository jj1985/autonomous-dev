"""Regression tests for Issue #753: Pipeline state HMAC stale fail-open.

When a pipeline state file persists after /clear but the secret file has been
cleaned up, verify_state_hmac() should fail-open for stale states (>1 hour old)
instead of generating repeated HMAC failures.

The stale detection uses file mtime (not session_start from the state dict)
to prevent an attacker from forging session_start to trigger fail-open.
"""

import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import os
import sys

# Portable project root detection
_current = Path(__file__).resolve()
_project_root = _current.parents[2]
_lib_path = _project_root / "plugins" / "autonomous-dev" / "lib"
if str(_lib_path) not in sys.path:
    sys.path.insert(0, str(_lib_path))

from pipeline_state import (
    _compute_state_hmac,
    sign_state,
    verify_state_hmac,
)


def _make_state(
    session_start: str = "",
    *,
    run_id: str = "test-run-753",
    nonce: str = "abc123",
    hmac_value: str = "bogus_hmac_that_will_not_match",
) -> dict:
    """Build a minimal state dict for testing HMAC verification."""
    state = {
        "session_start": session_start,
        "run_id": run_id,
        "nonce": nonce,
        "mode": "full",
        "explicitly_invoked": True,
        "alignment_passed": True,
        "hmac": hmac_value,
    }
    return state


class TestStaleStateFailOpen:
    """Verify the stale-state fail-open behavior added in Issue #753."""

    @patch("pipeline_state._read_pipeline_secret", return_value=None)
    def test_stale_state_invalid_hmac_returns_true(self, mock_secret):
        """Stale state file (>1hr mtime) with unverifiable HMAC should fail-open."""
        state = _make_state(session_start="")

        # Mock the state file's mtime to be 2 hours ago
        old_mtime = time.time() - 7200  # 2 hours ago
        mock_stat = MagicMock()
        mock_stat.st_mtime = old_mtime

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "stat", return_value=mock_stat):
            result = verify_state_hmac(state, "different-session")

        assert result is True, (
            "Stale state file (>1hr mtime) with lost secret should fail-open"
        )

    @patch("pipeline_state._read_pipeline_secret", return_value=None)
    def test_fresh_state_invalid_hmac_returns_false(self, mock_secret):
        """Fresh state file (<1hr mtime) with unverifiable HMAC should still fail."""
        state = _make_state(session_start="")

        # Mock the state file's mtime to be 5 minutes ago
        recent_mtime = time.time() - 300  # 5 minutes ago
        mock_stat = MagicMock()
        mock_stat.st_mtime = recent_mtime

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "stat", return_value=mock_stat):
            result = verify_state_hmac(state, "different-session")

        assert result is False, (
            "Fresh state file (<1hr mtime) with invalid HMAC should NOT fail-open"
        )

    @patch("pipeline_state._read_pipeline_secret", return_value=None)
    def test_no_state_file_invalid_hmac_returns_false(self, mock_secret):
        """When state file does not exist, unverifiable HMAC should fail."""
        state = _make_state(session_start="")

        with patch.object(Path, "exists", return_value=False):
            result = verify_state_hmac(state, "different-session")

        assert result is False, (
            "Missing state file should not trigger fail-open"
        )

    @patch("pipeline_state._read_pipeline_secret")
    def test_valid_hmac_passes_regardless_of_age(self, mock_secret):
        """A properly signed state should verify even when old."""
        mock_secret.return_value = "the-real-secret"
        two_hours_ago = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()

        state = {
            "session_start": two_hours_ago,
            "run_id": "test-run-753",
            "nonce": "valid-nonce-123",
            "mode": "full",
            "explicitly_invoked": True,
            "alignment_passed": True,
        }
        # Sign with the real secret
        state["hmac"] = _compute_state_hmac(state, "the-real-secret")

        result = verify_state_hmac(state, "any-session")

        assert result is True, (
            "Valid HMAC should pass regardless of state age"
        )

    @patch("pipeline_state._read_pipeline_secret", return_value=None)
    def test_forged_session_start_with_fresh_mtime_returns_false(self, mock_secret):
        """Attack vector: forged session_start (2hr old) but fresh file mtime.

        An attacker who modifies session_start to a past timestamp to trigger
        fail-open should be blocked because the file's mtime reflects when the
        file was actually written, not what session_start claims.
        """
        two_hours_ago = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        state = _make_state(session_start=two_hours_ago)

        # File was just written (fresh mtime) despite session_start claiming 2hr ago
        fresh_mtime = time.time() - 60  # 1 minute ago
        mock_stat = MagicMock()
        mock_stat.st_mtime = fresh_mtime

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "stat", return_value=mock_stat):
            result = verify_state_hmac(state, "different-session")

        assert result is False, (
            "Forged session_start with fresh file mtime should NOT fail-open. "
            "The mtime-based check prevents this attack vector."
        )
