"""
Spec validation tests for Issue #847: Pipeline state file isolation in ordering gate tests.

Bug: Ordering gate tests (test_implementer_blocked_without_planner and
test_implementer_still_requires_planner) fail when stale
/tmp/implement_pipeline_state.json has mode=fix, because tests don't
isolate the pipeline state file reading.

Fix: autouse fixture sets PIPELINE_STATE_FILE to nonexistent temp path so
tests always get "full" mode fallback. Added 4 regression tests.

Acceptance criteria:
1. Tests isolate pipeline state file via PIPELINE_STATE_FILE env var
2. _get_pipeline_mode_from_state() falls back to "full" for nonexistent file
3. _get_pipeline_mode_from_state() reads mode from state file when present
4. In full mode, planner->implementer prerequisite is enforced (deny)
5. In fix mode, planner->implementer prerequisite is skipped (allow)
6. The two originally-failing tests now pass reliably
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook and lib dirs to path
HOOK_DIR = Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(HOOK_DIR))
sys.path.insert(0, str(LIB_DIR))

import unified_pre_tool as hook


@pytest.fixture(autouse=True)
def isolate_pipeline_state(monkeypatch, tmp_path):
    """Isolate pipeline state for all tests in this module."""
    env_keys = [
        "PRE_TOOL_PIPELINE_ORDERING", "SANDBOX_ENABLED",
        "PRE_TOOL_MCP_SECURITY", "PRE_TOOL_AGENT_AUTH",
        "PRE_TOOL_BATCH_PERMISSION", "ENFORCEMENT_LEVEL",
        "CLAUDE_AGENT_NAME", "PIPELINE_ISSUE_NUMBER",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PIPELINE_STATE_FILE", str(tmp_path / "nonexistent_pipeline_state.json"))


class TestSpec847PipelineModeFromState:
    """Spec criteria 2-3: _get_pipeline_mode_from_state behavior."""

    def test_spec_issue847_1_fallback_to_full_for_nonexistent_file(self, tmp_path, monkeypatch):
        """When PIPELINE_STATE_FILE points to nonexistent file, mode must be 'full'."""
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(tmp_path / "does_not_exist.json"))
        mode = hook._get_pipeline_mode_from_state()
        assert mode == "full"

    def test_spec_issue847_2_reads_mode_from_state_file(self, tmp_path, monkeypatch):
        """When PIPELINE_STATE_FILE points to valid file with mode=fix, returns 'fix'."""
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"mode": "fix"}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        mode = hook._get_pipeline_mode_from_state()
        assert mode == "fix"

    def test_spec_issue847_3_reads_full_mode_from_state_file(self, tmp_path, monkeypatch):
        """When PIPELINE_STATE_FILE has mode=full explicitly, returns 'full'."""
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"mode": "full"}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        mode = hook._get_pipeline_mode_from_state()
        assert mode == "full"


class TestSpec847ImplementerPlannerEnforcement:
    """Spec criteria 4-5: planner->implementer enforcement depends on pipeline mode."""

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_spec_issue847_4_full_mode_denies_implementer_without_planner(
        self, mock_mode, mock_completed, tmp_path, monkeypatch
    ):
        """In full mode, implementer MUST be denied when planner has not completed."""
        # Ensure full mode (nonexistent state file)
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(tmp_path / "nonexistent.json"))
        mock_completed.return_value = {"researcher"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"subagent_type": "implementer", "prompt": "Implement changes"}
            )
            assert decision == "deny", (
                f"Expected 'deny' in full mode without planner, got '{decision}'. "
                f"Reason: {reason}"
            )
            assert "planner" in reason.lower()

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_spec_issue847_5_fix_mode_allows_implementer_without_planner(
        self, mock_mode, mock_completed, tmp_path, monkeypatch
    ):
        """In fix mode, implementer is allowed without planner (fix skips planner)."""
        state_file = tmp_path / "fix_state.json"
        state_file.write_text(json.dumps({"mode": "fix", "explicitly_invoked": True}))
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        mock_completed.return_value = {"researcher"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"subagent_type": "implementer", "prompt": "Implement changes"}
            )
            assert decision == "allow", (
                f"Expected 'allow' in fix mode without planner, got '{decision}'. "
                f"Reason: {reason}"
            )


class TestSpec847TestIsolation:
    """Spec criterion 1,6: autouse fixture ensures test isolation."""

    @patch("pipeline_completion_state.get_completed_agents")
    @patch("pipeline_completion_state.get_validation_mode")
    def test_spec_issue847_6_default_isolation_enforces_full_mode(
        self, mock_mode, mock_completed
    ):
        """Without any monkeypatch override, the autouse fixture isolates state to full mode.

        This validates that the autouse fixture in the test file correctly
        sets PIPELINE_STATE_FILE to a nonexistent path, resulting in full mode.
        """
        # Do NOT override PIPELINE_STATE_FILE -- rely on autouse fixture
        mock_completed.return_value = {"researcher"}
        mock_mode.return_value = "sequential"

        with patch.object(hook, "_is_pipeline_active", return_value=True), \
             patch.object(hook, "_session_id", "test-session"):
            decision, reason = hook.validate_pipeline_ordering(
                "Agent", {"subagent_type": "implementer", "prompt": "Implement changes"}
            )
            assert decision == "deny", (
                "Autouse fixture should ensure full mode (nonexistent state file), "
                f"but implementer was allowed without planner. Reason: {reason}"
            )

    def test_spec_issue847_7_pipeline_state_file_env_is_set_by_fixture(self):
        """The PIPELINE_STATE_FILE env var must be set (by autouse fixture) and point
        to a nonexistent path."""
        state_file_path = os.environ.get("PIPELINE_STATE_FILE")
        assert state_file_path is not None, "PIPELINE_STATE_FILE should be set by autouse fixture"
        assert not Path(state_file_path).exists(), (
            f"PIPELINE_STATE_FILE should point to nonexistent path, but {state_file_path} exists"
        )
