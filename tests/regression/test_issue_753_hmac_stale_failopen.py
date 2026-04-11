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
    LEGACY_SENTINEL_PATH,
    _compute_state_hmac,
    get_state_path,
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


class TestIssue761SentinelPathPinning:
    """Verify that the legacy sentinel path is documented, pinned, and distinct
    from the HMAC state path (Issue #761).

    These tests prevent silent breakage if a future refactor changes the
    sentinel path without updating the constant or the stale fail-open logic.
    """

    def test_legacy_sentinel_path_constant_exists(self):
        """LEGACY_SENTINEL_PATH constant must equal the known sentinel path.

        This pins the value so any change is caught automatically by the
        test suite, preventing silent divergence from unified_pre_tool.py.
        """
        assert LEGACY_SENTINEL_PATH == Path("/tmp/implement_pipeline_state.json"), (
            f"LEGACY_SENTINEL_PATH changed unexpectedly: {LEGACY_SENTINEL_PATH}. "
            "If intentional, update unified_pre_tool.py PIPELINE_STATE_FILE and "
            "pre_compact_batch_saver.sh to match."
        )

    def test_legacy_sentinel_path_is_not_hmac_state_path(self):
        """LEGACY_SENTINEL_PATH must be distinct from per-run HMAC state paths.

        The sentinel and the HMAC state file serve different purposes:
        - Sentinel: activity indicator, touched on every hook call
        - HMAC state: signed pipeline state with nonce and HMAC fields

        If they ever collide, the stale fail-open logic would check the
        wrong file's mtime, breaking security guarantees.
        """
        # Test against several representative run_id values
        for run_id in ["test-run", "batch-20260412-015602", "issue-761-fix", "abc123"]:
            hmac_path = get_state_path(run_id)
            assert LEGACY_SENTINEL_PATH != hmac_path, (
                f"LEGACY_SENTINEL_PATH collides with HMAC state path for "
                f"run_id={run_id!r}: {hmac_path}"
            )

    @patch("pipeline_state._read_pipeline_secret", return_value=None)
    def test_verify_state_hmac_checks_legacy_sentinel_path(self, mock_secret):
        """verify_state_hmac() must check LEGACY_SENTINEL_PATH for stale detection.

        This test patches Path() construction to track which path strings are
        used, then verifies that the stale fail-open section references the
        sentinel path (not the HMAC state path or an arbitrary path).
        """
        state = _make_state(session_start="")

        # Track which paths have exists() called on them
        original_exists = Path.exists
        checked_paths: list[str] = []

        def tracking_exists(self):
            checked_paths.append(str(self))
            # Return True only for the sentinel path so stale check proceeds
            if str(self) == str(LEGACY_SENTINEL_PATH):
                return True
            return False

        # Make the sentinel appear stale so the function returns True via fail-open
        old_mtime = time.time() - 7200  # 2 hours ago
        mock_stat = MagicMock()
        mock_stat.st_mtime = old_mtime

        with patch.object(Path, "exists", tracking_exists), \
             patch.object(Path, "stat", return_value=mock_stat):
            result = verify_state_hmac(state, "different-session")

        assert str(LEGACY_SENTINEL_PATH) in checked_paths, (
            f"verify_state_hmac() did not check LEGACY_SENTINEL_PATH "
            f"({LEGACY_SENTINEL_PATH}). Paths checked: {checked_paths}"
        )
        assert result is True, (
            "Stale sentinel should trigger fail-open (confirms the sentinel "
            "path is actually used for stale detection, not just constructed)"
        )
