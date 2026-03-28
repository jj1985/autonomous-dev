#!/usr/bin/env python3
"""
Tests for AgentTracker session isolation via CLAUDE_SESSION_ID (Issue #594).

Validates that AgentTracker selects the correct pipeline.json file based on
the CLAUDE_SESSION_ID environment variable, preventing cross-session pollution
when multiple /implement pipelines run concurrently (e.g., batch worktrees).

Date: 2026-03-29
Issue: GitHub #594 - pipeline.json session mixing
Agent: implementer
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# Portable project root detection
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

from agent_tracker import AgentTracker


def _write_pipeline_json(session_dir: Path, filename: str, claude_session_id: str | None) -> Path:
    """Helper: write a minimal pipeline JSON file with optional claude_session_id."""
    f = session_dir / filename
    data: dict = {
        "session_id": filename.replace("-pipeline.json", ""),
        "started": datetime.now().isoformat(),
        "github_issue": None,
        "agents": [],
    }
    if claude_session_id is not None:
        data["claude_session_id"] = claude_session_id
    f.write_text(json.dumps(data))
    return f


def _make_tracker(tmp_path: Path, env: dict | None = None) -> AgentTracker:
    """Create an AgentTracker in auto-detect mode using tmp_path as project root."""
    env = env or {}
    with (
        patch("agent_tracker.tracker.get_project_root", return_value=tmp_path),
        patch.dict(os.environ, env, clear=False),
    ):
        return AgentTracker()


class TestAgentTrackerSessionIsolation:
    """Tests for CLAUDE_SESSION_ID-based session file isolation (Issue #594)."""

    def test_selects_matching_session_file(self, tmp_path):
        """Two pipeline files exist today; tracker picks the one matching CLAUDE_SESSION_ID.

        Without the fix, the tracker always picks the latest file regardless of
        session ID, causing session-A data to be written into session-B's file.
        """
        today = datetime.now().strftime("%Y%m%d")
        session_dir = tmp_path / "docs" / "sessions"
        session_dir.mkdir(parents=True)

        # Session A file (older)
        _write_pipeline_json(
            session_dir, f"{today}-060000-pipeline.json", claude_session_id="session-aaa"
        )
        # Session B file (newer — would be picked without the fix)
        _write_pipeline_json(
            session_dir, f"{today}-070000-pipeline.json", claude_session_id="session-bbb"
        )

        tracker = _make_tracker(tmp_path, {"CLAUDE_SESSION_ID": "session-aaa"})

        assert "060000" in tracker.session_file.name, (
            f"Expected session-aaa file (060000), got: {tracker.session_file.name}"
        )
        assert tracker.session_data.get("claude_session_id") == "session-aaa"

    def test_creates_new_file_when_no_match(self, tmp_path):
        """Existing files don't match CLAUDE_SESSION_ID; a new file is created.

        This covers the first pipeline run in a new session when older sessions'
        files are still present from the same day.
        """
        today = datetime.now().strftime("%Y%m%d")
        session_dir = tmp_path / "docs" / "sessions"
        session_dir.mkdir(parents=True)

        # Pre-existing file from a different session
        _write_pipeline_json(
            session_dir, f"{today}-060000-pipeline.json", claude_session_id="session-other"
        )

        tracker = _make_tracker(tmp_path, {"CLAUDE_SESSION_ID": "session-new"})

        # Should have created a NEW file, not reused the existing one
        assert "060000" not in tracker.session_file.name, (
            "Tracker must not reuse a file belonging to a different session"
        )
        existing_files = list(session_dir.glob(f"{today}-*-pipeline.json"))
        assert len(existing_files) == 2, (
            f"Expected 2 files (old + new), found: {[f.name for f in existing_files]}"
        )

    def test_new_file_stores_claude_session_id(self, tmp_path):
        """Newly created session file contains the correct claude_session_id field."""
        session_dir = tmp_path / "docs" / "sessions"
        session_dir.mkdir(parents=True)

        tracker = _make_tracker(tmp_path, {"CLAUDE_SESSION_ID": "session-xyz"})

        assert tracker.session_data.get("claude_session_id") == "session-xyz", (
            f"New file should store claude_session_id, got: {tracker.session_data}"
        )
        # Verify persisted to disk
        on_disk = json.loads(tracker.session_file.read_text())
        assert on_disk.get("claude_session_id") == "session-xyz"

    def test_fallback_when_no_env_var(self, tmp_path):
        """Without CLAUDE_SESSION_ID, uses the latest file (backward compatibility)."""
        today = datetime.now().strftime("%Y%m%d")
        session_dir = tmp_path / "docs" / "sessions"
        session_dir.mkdir(parents=True)

        # Two files with different session IDs; without env var, pick the latest
        _write_pipeline_json(
            session_dir, f"{today}-060000-pipeline.json", claude_session_id="session-old"
        )
        _write_pipeline_json(
            session_dir, f"{today}-080000-pipeline.json", claude_session_id="session-new"
        )

        # Ensure CLAUDE_SESSION_ID is absent
        env_without = {k: v for k, v in os.environ.items() if k != "CLAUDE_SESSION_ID"}
        with (
            patch("agent_tracker.tracker.get_project_root", return_value=tmp_path),
            patch.dict(os.environ, env_without, clear=True),
        ):
            tracker = AgentTracker()

        # Should use the LATEST file (sorted alphabetically / by timestamp)
        assert "080000" in tracker.session_file.name, (
            f"Expected latest file (080000) with no env var, got: {tracker.session_file.name}"
        )

    def test_no_cross_session_pollution(self, tmp_path):
        """Session B does not write to session A's file.

        This is the core regression test for Issue #594. When two pipelines run
        on the same day, each should write only to their own session file.
        """
        today = datetime.now().strftime("%Y%m%d")
        session_dir = tmp_path / "docs" / "sessions"
        session_dir.mkdir(parents=True)

        # Session A already has a file
        file_a = _write_pipeline_json(
            session_dir, f"{today}-060000-pipeline.json", claude_session_id="session-aaa"
        )
        original_content_a = json.loads(file_a.read_text())

        # Session B creates its tracker — should NOT touch session A's file
        tracker_b = _make_tracker(tmp_path, {"CLAUDE_SESSION_ID": "session-bbb"})
        tracker_b.start_agent("implementer", "Session B started")

        # Session A's file must be unchanged
        content_a_after = json.loads(file_a.read_text())
        assert content_a_after == original_content_a, (
            "Session B must not modify session A's file"
        )

        # Session B's writes should be in B's file (different from A's)
        assert tracker_b.session_file != file_a, (
            "Session B must write to its own file, not session A's"
        )
        content_b = json.loads(tracker_b.session_file.read_text())
        assert content_b.get("claude_session_id") == "session-bbb"
        assert any(a["agent"] == "implementer" for a in content_b.get("agents", []))

    def test_corrupt_files_skipped_gracefully(self, tmp_path):
        """Corrupt JSON files are skipped; tracker falls through to create new file."""
        today = datetime.now().strftime("%Y%m%d")
        session_dir = tmp_path / "docs" / "sessions"
        session_dir.mkdir(parents=True)

        # Write a corrupt file
        corrupt = session_dir / f"{today}-060000-pipeline.json"
        corrupt.write_text("{ not valid json !!!")

        # Should not raise; should create a new file
        tracker = _make_tracker(tmp_path, {"CLAUDE_SESSION_ID": "session-xyz"})

        assert tracker.session_file != corrupt
        assert tracker.session_data.get("claude_session_id") == "session-xyz"
