"""Regression tests for AgentTracker handling session files without 'agents' key.

Issue #576: Checkpoint fails with KeyError 'agents' when pipeline session file
uses the new schema that omits the 'agents' key.

These tests verify that AgentTracker gracefully handles session files in both
the old schema (with 'agents' key) and the new pipeline schema (without it).
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracker(tmp_path: Path, session_data: dict) -> "AgentTracker":
    """Create an AgentTracker backed by a session file with the given data."""
    import sys

    lib_path = Path(__file__).parent.parent.parent / "plugins" / "autonomous-dev" / "lib"
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))

    from agent_tracker import AgentTracker

    session_file = tmp_path / "test-pipeline.json"
    session_file.write_text(json.dumps(session_data))

    with patch("path_utils.get_project_root", return_value=tmp_path):
        tracker = AgentTracker(session_file=str(session_file))

    return tracker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pipeline_schema_file(tmp_path: Path) -> Path:
    """A session file using the new pipeline schema — NO 'agents' key."""
    data = {
        "session_id": "20260329-080000",
        "started": datetime.now().isoformat(),
        "github_issue": None,
        "step": 5,
        "agent": "implementer",
        "explicitly_invoked": True,
    }
    p = tmp_path / "20260329-080000-pipeline.json"
    p.write_text(json.dumps(data))
    return p


@pytest.fixture()
def legacy_schema_file(tmp_path: Path) -> Path:
    """A session file with the original schema that includes 'agents' key."""
    data = {
        "session_id": "20260329-070000",
        "started": datetime.now().isoformat(),
        "github_issue": None,
        "agents": [],
    }
    p = tmp_path / "20260329-070000-pipeline.json"
    p.write_text(json.dumps(data))
    return p


# ---------------------------------------------------------------------------
# Tests: explicit session_file path (loading path 1)
# ---------------------------------------------------------------------------

class TestExplicitSessionFilePath:
    """AgentTracker(session_file=...) with pipeline-schema file (no 'agents' key)."""

    def test_no_key_error_on_load(self, tmp_path: Path, pipeline_schema_file: Path) -> None:
        """Loading a pipeline-schema file must not raise KeyError."""
        import sys
        lib_path = Path(__file__).parent.parent.parent / "plugins" / "autonomous-dev" / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))

        from agent_tracker import AgentTracker

        # Should not raise KeyError('agents')
        tracker = AgentTracker(session_file=str(pipeline_schema_file))
        assert tracker is not None

    def test_agents_key_defaults_to_empty_list(self, tmp_path: Path, pipeline_schema_file: Path) -> None:
        """After loading a pipeline-schema file, session_data['agents'] is []."""
        import sys
        lib_path = Path(__file__).parent.parent.parent / "plugins" / "autonomous-dev" / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))

        from agent_tracker import AgentTracker

        tracker = AgentTracker(session_file=str(pipeline_schema_file))
        assert tracker.session_data["agents"] == []

    def test_start_agent_works_after_pipeline_schema_load(
        self, tmp_path: Path, pipeline_schema_file: Path
    ) -> None:
        """start_agent() must succeed after loading a pipeline-schema file."""
        import sys
        lib_path = Path(__file__).parent.parent.parent / "plugins" / "autonomous-dev" / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))

        from agent_tracker import AgentTracker

        tracker = AgentTracker(session_file=str(pipeline_schema_file))

        # Must not raise
        tracker.start_agent("implementer", "Starting implementation")

        # Agent entry should now be present
        agents = tracker.session_data["agents"]
        assert len(agents) == 1
        assert agents[0]["agent"] == "implementer"
        assert agents[0]["status"] == "started"

    def test_legacy_schema_unaffected(self, tmp_path: Path, legacy_schema_file: Path) -> None:
        """Loading a legacy session file (with 'agents' key) still works correctly."""
        import sys
        lib_path = Path(__file__).parent.parent.parent / "plugins" / "autonomous-dev" / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))

        from agent_tracker import AgentTracker

        tracker = AgentTracker(session_file=str(legacy_schema_file))
        # The existing empty list must be preserved (not overwritten)
        assert tracker.session_data["agents"] == []


# ---------------------------------------------------------------------------
# Tests: auto-detect path — fallback latest file (loading path 3)
# ---------------------------------------------------------------------------

class TestAutoDetectFallbackPath:
    """AgentTracker() auto-detect with no CLAUDE_SESSION_ID set (loading path 3)."""

    def test_no_key_error_fallback_latest(self, tmp_path: Path) -> None:
        """Fallback to latest file in auto-detect mode must not raise KeyError."""
        import sys
        import os
        lib_path = Path(__file__).parent.parent.parent / "plugins" / "autonomous-dev" / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))

        from agent_tracker import AgentTracker

        # Create session dir and a pipeline-schema file for today
        session_dir = tmp_path / "docs" / "sessions"
        session_dir.mkdir(parents=True)
        today = datetime.now().strftime("%Y%m%d")
        session_file = session_dir / f"{today}-080000-pipeline.json"
        session_file.write_text(json.dumps({
            "session_id": f"{today}-080000",
            "started": datetime.now().isoformat(),
            "step": 3,
        }))

        # Patch get_project_root in the tracker module's namespace and remove CLAUDE_SESSION_ID
        with patch("agent_tracker.tracker.get_project_root", return_value=tmp_path), \
             patch.dict(os.environ, {}, clear=False):
            # Ensure CLAUDE_SESSION_ID is not set
            os.environ.pop("CLAUDE_SESSION_ID", None)
            tracker = AgentTracker()

        assert tracker is not None
        assert tracker.session_data["agents"] == []

    def test_agents_from_new_schema_is_empty_list_fallback(self, tmp_path: Path) -> None:
        """session_data['agents'] defaults to [] when loaded via fallback path."""
        import sys
        import os
        lib_path = Path(__file__).parent.parent.parent / "plugins" / "autonomous-dev" / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))

        from agent_tracker import AgentTracker

        session_dir = tmp_path / "docs" / "sessions"
        session_dir.mkdir(parents=True)
        today = datetime.now().strftime("%Y%m%d")
        session_file = session_dir / f"{today}-090000-pipeline.json"
        session_file.write_text(json.dumps({
            "session_id": f"{today}-090000",
            "started": datetime.now().isoformat(),
            "explicitly_invoked": True,
        }))

        with patch("agent_tracker.tracker.get_project_root", return_value=tmp_path), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_SESSION_ID", None)
            tracker = AgentTracker()

        assert isinstance(tracker.session_data["agents"], list)
        assert tracker.session_data["agents"] == []


# ---------------------------------------------------------------------------
# Tests: auto-detect path — CLAUDE_SESSION_ID matched (loading path 2)
# ---------------------------------------------------------------------------

class TestAutoDetectSessionMatchedPath:
    """AgentTracker() auto-detect with matching CLAUDE_SESSION_ID (loading path 2)."""

    def test_no_key_error_session_matched(self, tmp_path: Path) -> None:
        """Session-ID-matched file load must not raise KeyError."""
        import sys
        import os
        lib_path = Path(__file__).parent.parent.parent / "plugins" / "autonomous-dev" / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))

        from agent_tracker import AgentTracker

        session_dir = tmp_path / "docs" / "sessions"
        session_dir.mkdir(parents=True)
        today = datetime.now().strftime("%Y%m%d")
        test_session_id = "test-session-abc123"
        session_file = session_dir / f"{today}-100000-pipeline.json"
        session_file.write_text(json.dumps({
            "session_id": f"{today}-100000",
            "claude_session_id": test_session_id,
            "started": datetime.now().isoformat(),
            "step": 7,
        }))

        with patch("agent_tracker.tracker.get_project_root", return_value=tmp_path), \
             patch.dict(os.environ, {"CLAUDE_SESSION_ID": test_session_id}):
            tracker = AgentTracker()

        assert tracker is not None
        assert tracker.session_data["agents"] == []

    def test_start_agent_after_session_matched_load(self, tmp_path: Path) -> None:
        """start_agent() must work after session-matched load of pipeline-schema file."""
        import sys
        import os
        lib_path = Path(__file__).parent.parent.parent / "plugins" / "autonomous-dev" / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))

        from agent_tracker import AgentTracker

        session_dir = tmp_path / "docs" / "sessions"
        session_dir.mkdir(parents=True)
        today = datetime.now().strftime("%Y%m%d")
        test_session_id = "test-session-def456"
        session_file = session_dir / f"{today}-110000-pipeline.json"
        session_file.write_text(json.dumps({
            "session_id": f"{today}-110000",
            "claude_session_id": test_session_id,
            "started": datetime.now().isoformat(),
        }))

        with patch("agent_tracker.tracker.get_project_root", return_value=tmp_path), \
             patch.dict(os.environ, {"CLAUDE_SESSION_ID": test_session_id}):
            tracker = AgentTracker()
            tracker.start_agent("researcher", "Starting research")

        agents = tracker.session_data["agents"]
        assert len(agents) == 1
        assert agents[0]["agent"] == "researcher"
