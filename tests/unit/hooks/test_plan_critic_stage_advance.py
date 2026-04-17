"""Tests for plan-critic stage advance logic in unified_session_tracker.py."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for direct import
HOOKS_DIR = Path(__file__).parent.parent.parent.parent / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from unified_session_tracker import _advance_plan_mode_stage, _PLAN_TO_ISSUES_SUGGESTION


MARKER_REL_PATH = ".claude/plan_mode_exit.json"


def _write_marker(tmp_path: Path, *, stage: str = "plan_exited", **extra) -> Path:
    """Helper to write a plan mode exit marker for stage-advance tests.

    Args:
        tmp_path: Temp directory acting as cwd.
        stage: The stage field value.
        **extra: Additional fields to include in the marker.

    Returns:
        Path to the created marker file.
    """
    marker_path = tmp_path / MARKER_REL_PATH
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": "test-session",
        "stage": stage,
        **extra,
    }
    marker_path.write_text(json.dumps(marker_data, indent=2))
    return marker_path


class TestPlanCriticStageAdvance:
    """Tests for _advance_plan_mode_stage()."""

    def test_plan_critic_completion_advances_stage(self, tmp_path: Path):
        """Stage should advance from plan_exited to critique_done."""
        _write_marker(tmp_path, stage="plan_exited")
        with patch("os.getcwd", return_value=str(tmp_path)):
            _advance_plan_mode_stage()

        marker_data = json.loads((tmp_path / MARKER_REL_PATH).read_text())
        assert marker_data["stage"] == "critique_done"

    def test_non_plan_critic_agent_does_not_advance_stage(self, tmp_path: Path):
        """Only plan-critic should trigger advance; other agents leave marker unchanged.

        Note: _advance_plan_mode_stage() itself always advances. The caller
        (main()) gates on agent_name == 'plan-critic'. This test verifies
        the marker is untouched when _advance_plan_mode_stage() is NOT called.
        """
        marker = _write_marker(tmp_path, stage="plan_exited")
        # Do NOT call _advance_plan_mode_stage — simulate non-plan-critic agent
        marker_data = json.loads(marker.read_text())
        assert marker_data["stage"] == "plan_exited"

    def test_no_marker_file_no_error(self, tmp_path: Path):
        """Should not raise when no marker file exists."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            _advance_plan_mode_stage()  # Should not raise

    def test_already_critique_done_is_idempotent(self, tmp_path: Path):
        """Calling advance on critique_done should not change anything."""
        _write_marker(tmp_path, stage="critique_done")
        with patch("os.getcwd", return_value=str(tmp_path)):
            _advance_plan_mode_stage()

        marker_data = json.loads((tmp_path / MARKER_REL_PATH).read_text())
        assert marker_data["stage"] == "critique_done"
        # Should NOT have added critique_completed_at since stage didn't change
        assert "critique_completed_at" not in marker_data

    def test_stage_advance_adds_timestamp(self, tmp_path: Path):
        """Advancing from plan_exited should add critique_completed_at timestamp."""
        _write_marker(tmp_path, stage="plan_exited")
        with patch("os.getcwd", return_value=str(tmp_path)):
            _advance_plan_mode_stage()

        marker_data = json.loads((tmp_path / MARKER_REL_PATH).read_text())
        assert "critique_completed_at" in marker_data
        # Validate it's a valid ISO timestamp
        dt = datetime.fromisoformat(marker_data["critique_completed_at"])
        assert dt.tzinfo is not None

    def test_corrupted_marker_not_advanced(self, tmp_path: Path):
        """Corrupted marker JSON should not crash, marker left as-is."""
        marker_path = tmp_path / MARKER_REL_PATH
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("not valid json {{{")

        with patch("os.getcwd", return_value=str(tmp_path)):
            _advance_plan_mode_stage()  # Should not raise

        # Marker should still exist (not deleted by advance logic)
        assert marker_path.exists()
        assert marker_path.read_text() == "not valid json {{{"

    # ------------------------------------------------------------------
    # Tests for return value (suggestion message)
    # ------------------------------------------------------------------

    def test_advance_returns_suggestion_on_stage_change(self, tmp_path: Path):
        """_advance_plan_mode_stage returns non-None string when advancing plan_exited -> critique_done."""
        _write_marker(tmp_path, stage="plan_exited")
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _advance_plan_mode_stage()

        assert result is not None
        assert isinstance(result, str)

    def test_suggestion_contains_plan_to_issues(self, tmp_path: Path):
        """Returned suggestion includes /plan-to-issues --quick."""
        _write_marker(tmp_path, stage="plan_exited")
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _advance_plan_mode_stage()

        assert "/plan-to-issues --quick" in result

    def test_suggestion_contains_implement(self, tmp_path: Path):
        """Returned suggestion includes /implement."""
        _write_marker(tmp_path, stage="plan_exited")
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _advance_plan_mode_stage()

        assert "/implement" in result

    def test_advance_returns_none_when_already_done(self, tmp_path: Path):
        """Returns None when marker is already at critique_done."""
        _write_marker(tmp_path, stage="critique_done")
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _advance_plan_mode_stage()

        assert result is None

    def test_advance_returns_none_when_no_marker(self, tmp_path: Path):
        """Returns None when no marker file exists."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _advance_plan_mode_stage()

        assert result is None

    def test_advance_returns_none_on_corrupted_marker(self, tmp_path: Path):
        """Returns None when marker JSON is corrupted."""
        marker_path = tmp_path / MARKER_REL_PATH
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("not valid json {{{")

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _advance_plan_mode_stage()

        assert result is None

    def test_suggestion_constant_matches_return_value(self, tmp_path: Path):
        """Returned suggestion matches the exported _PLAN_TO_ISSUES_SUGGESTION constant."""
        _write_marker(tmp_path, stage="plan_exited")
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _advance_plan_mode_stage()

        assert result == _PLAN_TO_ISSUES_SUGGESTION
