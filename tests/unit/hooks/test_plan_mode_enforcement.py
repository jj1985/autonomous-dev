"""Tests for plan mode enforcement logic in unified_prompt_validator.py."""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for direct import
HOOKS_DIR = Path(__file__).parent.parent.parent.parent / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from unified_prompt_validator import (
    _check_plan_mode_enforcement,
    PLAN_MODE_EXIT_MARKER,
    PLAN_MODE_STALE_MINUTES,
)


def _write_marker(tmp_path: Path, *, age_minutes: float = 0) -> Path:
    """Helper to write a plan mode exit marker file.

    Args:
        tmp_path: Temp directory acting as cwd
        age_minutes: How many minutes old the marker should be

    Returns:
        Path to the created marker file
    """
    marker_path = tmp_path / PLAN_MODE_EXIT_MARKER
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    marker_data = {
        "timestamp": ts.isoformat(),
        "session_id": "test-session",
    }
    marker_path.write_text(json.dumps(marker_data))
    return marker_path


class TestPlanModeEnforcementNoMarker:
    """Tests when no plan mode exit marker exists."""

    def test_no_marker_returns_none(self, tmp_path: Path):
        """No marker file means no enforcement."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("implement auth feature")
        assert result is None

    def test_no_marker_allows_any_prompt(self, tmp_path: Path):
        """Any prompt passes when no marker exists."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            assert _check_plan_mode_enforcement("edit some files") is None
            assert _check_plan_mode_enforcement("/implement auth") is None
            assert _check_plan_mode_enforcement("what is this?") is None


class TestPlanModeEnforcementWithMarker:
    """Tests when plan mode exit marker exists."""

    def test_implement_command_passes_and_consumes_marker(self, tmp_path: Path):
        """'/implement' should pass and delete the marker."""
        marker = _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("/implement add auth feature")
        assert result == 0
        assert not marker.exists()

    def test_create_issue_command_passes_and_consumes_marker(self, tmp_path: Path):
        """'/create-issue' should pass and delete the marker."""
        marker = _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("/create-issue auth feature needed")
        assert result == 0
        assert not marker.exists()

    def test_raw_edit_blocked(self, tmp_path: Path):
        """Raw editing prompt should be blocked when marker exists."""
        marker = _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("edit the auth module directly")
        assert result == 2
        # Marker should still exist (not consumed on block)
        assert marker.exists()

    def test_question_allowed_through(self, tmp_path: Path):
        """Questions (ending with ?) should pass even with marker."""
        marker = _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("What should I do next?")
        assert result is None
        # Marker should still exist
        assert marker.exists()

    def test_implement_with_args_passes(self, tmp_path: Path):
        """'/implement --fix' and similar variants should pass."""
        marker = _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("/implement --fix #123")
        assert result == 0
        assert not marker.exists()

    def test_create_issue_with_args_passes(self, tmp_path: Path):
        """'/create-issue --quick' should pass."""
        marker = _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("/create-issue --quick fix login")
        assert result == 0

    def test_plan_to_issues_command_passes_and_consumes_marker(self, tmp_path: Path):
        """'/plan-to-issues' should pass and delete the marker."""
        marker = _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("/plan-to-issues")
        assert result == 0
        assert not marker.exists()

    def test_plan_to_issues_with_quick_flag_passes(self, tmp_path: Path):
        """'/plan-to-issues --quick' should pass and delete the marker."""
        marker = _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("/plan-to-issues --quick")
        assert result == 0
        assert not marker.exists()

    def test_other_commands_blocked(self, tmp_path: Path):
        """Other slash commands like /audit should be blocked."""
        _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("/audit --quick")
        assert result == 2

    def test_plain_text_blocked(self, tmp_path: Path):
        """Plain text prompts blocked when marker exists."""
        _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("go ahead and make the changes")
        assert result == 2


class TestPlanModeEnforcementStaleness:
    """Tests for stale marker auto-deletion."""

    def test_stale_marker_auto_deleted(self, tmp_path: Path):
        """Markers older than PLAN_MODE_STALE_MINUTES should be auto-deleted."""
        marker = _write_marker(tmp_path, age_minutes=PLAN_MODE_STALE_MINUTES + 1)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("edit stuff directly")
        assert result is None
        assert not marker.exists()

    def test_fresh_marker_not_deleted(self, tmp_path: Path):
        """Markers within PLAN_MODE_STALE_MINUTES should remain active."""
        marker = _write_marker(tmp_path, age_minutes=5)
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("edit stuff directly")
        assert result == 2
        assert marker.exists()


class TestPlanModeEnforcementEdgeCases:
    """Tests for edge cases and error handling."""

    def test_corrupted_marker_deleted(self, tmp_path: Path):
        """Corrupted marker JSON should be deleted and prompt allowed."""
        marker_path = tmp_path / PLAN_MODE_EXIT_MARKER
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("not valid json {{{")
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("edit stuff")
        assert result is None
        assert not marker_path.exists()

    def test_marker_missing_timestamp_deleted(self, tmp_path: Path):
        """Marker without timestamp should be treated as corrupted."""
        marker_path = tmp_path / PLAN_MODE_EXIT_MARKER
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(json.dumps({"session_id": "test"}))
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _check_plan_mode_enforcement("edit stuff")
        assert result is None
        assert not marker_path.exists()

    def test_block_outputs_error_message(self, tmp_path: Path, capsys):
        """Blocked prompts should output error message with guidance."""
        _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            _check_plan_mode_enforcement("make the changes now")
        captured = capsys.readouterr()
        assert "PLAN MODE EXIT DETECTED" in captured.err
        assert "/implement" in captured.err
        assert "/create-issue" in captured.err
        # Should also output JSON to stdout
        output = json.loads(captured.out)
        assert "error" in output["hookSpecificOutput"]

    def test_block_message_includes_plan_to_issues(self, tmp_path: Path, capsys):
        """Block message should mention /plan-to-issues as an option."""
        _write_marker(tmp_path)
        with patch("os.getcwd", return_value=str(tmp_path)):
            _check_plan_mode_enforcement("make the changes now")
        captured = capsys.readouterr()
        assert "/plan-to-issues" in captured.err
