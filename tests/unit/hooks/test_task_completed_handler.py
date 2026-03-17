#!/usr/bin/env python3
"""
Unit tests for task_completed_handler.py hook.

Tests payload parsing, log entry creation, error handling, and exit behavior.

Date: 2026-03-17
Issue: #463
Agent: implementer
"""

import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO
from datetime import datetime, timezone

# Add hooks directory to path
sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "hooks"
    ),
)

import task_completed_handler as tch


class TestBuildLogEntry:
    """Test log entry construction from TaskCompleted payloads."""

    def test_valid_payload_all_fields(self):
        """Full payload produces complete log entry."""
        payload = {
            "task_id": "task-123",
            "task_subject": "Implement feature X",
            "task_description": "Full description of the task",
            "teammate_name": "implementer",
            "team_name": "dev-team",
            "session_id": "sess-abc",
        }
        entry = tch._build_log_entry(payload)

        assert entry["hook"] == "TaskCompleted"
        assert entry["task_id"] == "task-123"
        assert entry["task_subject"] == "Implement feature X"
        assert entry["task_description"] == "Full description of the task"
        assert entry["teammate_name"] == "implementer"
        assert entry["team_name"] == "dev-team"
        assert "timestamp" in entry

    def test_missing_fields_use_defaults(self):
        """Missing fields gracefully default to empty string or 'unknown'."""
        payload = {}
        entry = tch._build_log_entry(payload)

        assert entry["hook"] == "TaskCompleted"
        assert entry["task_id"] == "unknown"
        assert entry["task_subject"] == ""
        assert entry["task_description"] == ""
        assert entry["teammate_name"] == ""
        assert entry["team_name"] == ""

    def test_partial_payload(self):
        """Partial payload fills available fields, defaults the rest."""
        payload = {"task_id": "t-42", "teammate_name": "researcher"}
        entry = tch._build_log_entry(payload)

        assert entry["task_id"] == "t-42"
        assert entry["teammate_name"] == "researcher"
        assert entry["task_subject"] == ""

    def test_session_id_from_env(self):
        """Session ID prefers CLAUDE_SESSION_ID environment variable."""
        payload = {"session_id": "payload-session"}
        with patch.dict(os.environ, {"CLAUDE_SESSION_ID": "env-session"}):
            entry = tch._build_log_entry(payload)
        assert entry["session_id"] == "env-session"

    def test_session_id_from_payload(self):
        """Session ID falls back to payload when env var not set."""
        payload = {"session_id": "payload-session"}
        with patch.dict(os.environ, {}, clear=True):
            # Remove CLAUDE_SESSION_ID if it exists
            os.environ.pop("CLAUDE_SESSION_ID", None)
            entry = tch._build_log_entry(payload)
        assert entry["session_id"] == "payload-session"

    def test_timestamp_is_utc_iso(self):
        """Timestamp is in UTC ISO format."""
        entry = tch._build_log_entry({})
        # Should be parseable as ISO datetime
        parsed = datetime.fromisoformat(entry["timestamp"])
        assert parsed.tzinfo is not None


class TestWriteLogEntry:
    """Test JSONL log file writing."""

    def test_writes_jsonl_line(self, tmp_path):
        """Log entry is written as a single JSONL line."""
        entry = {"hook": "TaskCompleted", "task_id": "t-1", "timestamp": "2026-03-17T00:00:00+00:00"}

        with patch.object(tch, "_get_log_dir", return_value=tmp_path):
            tch._write_log_entry(entry)

        # Find the written file
        log_files = list(tmp_path.glob("*.jsonl"))
        assert len(log_files) == 1

        lines = log_files[0].read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["task_id"] == "t-1"

    def test_appends_to_existing_file(self, tmp_path):
        """Multiple entries append to the same daily file."""
        entry1 = {"hook": "TaskCompleted", "task_id": "t-1"}
        entry2 = {"hook": "TaskCompleted", "task_id": "t-2"}

        with patch.object(tch, "_get_log_dir", return_value=tmp_path):
            tch._write_log_entry(entry1)
            tch._write_log_entry(entry2)

        log_files = list(tmp_path.glob("*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text().strip().split("\n")
        assert len(lines) == 2


class TestMainFunction:
    """Test the main() entry point behavior."""

    def test_empty_stdin_exits_0(self):
        """Empty stdin causes clean exit 0."""
        with patch("sys.stdin", StringIO("")):
            with pytest.raises(SystemExit) as exc_info:
                tch.main()
            assert exc_info.value.code == 0

    def test_malformed_json_exits_0(self):
        """Malformed JSON causes clean exit 0 (non-blocking)."""
        with patch("sys.stdin", StringIO("not json at all")):
            with pytest.raises(SystemExit) as exc_info:
                tch.main()
            assert exc_info.value.code == 0

    def test_valid_payload_exits_0(self, tmp_path):
        """Valid payload is processed and exits 0."""
        payload = json.dumps({
            "task_id": "task-99",
            "task_subject": "Test task",
            "teammate_name": "test-agent",
        })
        with patch("sys.stdin", StringIO(payload)):
            with patch.object(tch, "_get_log_dir", return_value=tmp_path):
                with pytest.raises(SystemExit) as exc_info:
                    tch.main()
                assert exc_info.value.code == 0

        # Verify log was written
        log_files = list(tmp_path.glob("*.jsonl"))
        assert len(log_files) == 1
        line = json.loads(log_files[0].read_text().strip())
        assert line["task_id"] == "task-99"

    def test_write_error_still_exits_0(self):
        """Even if log writing fails, hook exits 0 (non-blocking)."""
        payload = json.dumps({"task_id": "task-err"})
        with patch("sys.stdin", StringIO(payload)):
            with patch.object(tch, "_write_log_entry", side_effect=PermissionError("denied")):
                with pytest.raises(SystemExit) as exc_info:
                    tch.main()
                assert exc_info.value.code == 0
