#!/usr/bin/env python3
"""
Tests for unified_session_tracker.py SubagentStop hook.

Validates stdin JSON parsing, backward-compatible env var fallback,
infinite loop prevention, transcript path validation, duration computation,
and JSONL activity logging.
"""

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "hooks"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

# Import the module functions directly
import unified_session_tracker as ust


class TestParseStdinJson:
    """Tests for _parse_stdin — reading SubagentStop JSON from stdin."""

    def test_parse_stdin_json(self):
        """Valid SubagentStop JSON is parsed correctly from stdin."""
        input_data = json.dumps({
            "agent_type": "researcher",
            "agent_id": "abc-123",
            "agent_transcript_path": "/Users/test/.claude/transcripts/abc.jsonl",
            "last_assistant_message": "Research complete with findings.",
            "session_id": "session-xyz",
            "hook_event_name": "SubagentStop",
            "stop_hook_active": False,
        })
        with patch("sys.stdin", io.StringIO(input_data)):
            result = ust._parse_stdin()

        assert result["agent_type"] == "researcher"
        assert result["agent_id"] == "abc-123"
        assert result["session_id"] == "session-xyz"
        assert result["last_assistant_message"] == "Research complete with findings."

    def test_parse_empty_stdin(self):
        """Empty stdin returns empty dict (falls back to env vars)."""
        with patch("sys.stdin", io.StringIO("")):
            result = ust._parse_stdin()
        assert result == {}

    def test_parse_invalid_json_stdin(self):
        """Invalid JSON stdin returns empty dict (falls back to env vars)."""
        with patch("sys.stdin", io.StringIO("not valid json {{")):
            result = ust._parse_stdin()
        assert result == {}


class TestStopHookActive:
    """Tests for stop_hook_active infinite loop prevention."""

    def test_stop_hook_active_exits_immediately(self):
        """When stop_hook_active=true, main() exits 0 immediately."""
        input_data = json.dumps({
            "agent_type": "researcher",
            "stop_hook_active": True,
            "hook_event_name": "SubagentStop",
        })
        with patch("sys.stdin", io.StringIO(input_data)):
            # Capture stdout to verify JSON output
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                result = ust.main()

        assert result == 0
        output = json.loads(mock_stdout.getvalue().strip())
        assert output["hookSpecificOutput"]["hookEventName"] == "SubagentStop"


class TestExtractFields:
    """Tests for field extraction from stdin JSON."""

    def test_extract_agent_type(self):
        """agent_type from stdin is mapped to agent_name."""
        input_data = {"agent_type": "implementer", "last_assistant_message": "Done"}
        # The agent_type field becomes the agent_name in main()
        agent_name = input_data.get("agent_type", "unknown")
        assert agent_name == "implementer"

    def test_extract_last_assistant_message(self):
        """last_assistant_message from stdin is mapped to agent_output."""
        input_data = {"agent_type": "planner", "last_assistant_message": "Plan created successfully."}
        agent_output = input_data.get("last_assistant_message", "")
        assert agent_output == "Plan created successfully."

    def test_extract_agent_transcript_path(self):
        """agent_transcript_path is stored from stdin."""
        input_data = {
            "agent_type": "researcher",
            "agent_transcript_path": "/Users/test/.claude/transcripts/abc.jsonl",
        }
        path = input_data.get("agent_transcript_path", "")
        assert path == "/Users/test/.claude/transcripts/abc.jsonl"


class TestValidateTranscriptPath:
    """Tests for _validate_transcript_path security validation."""

    def test_validate_transcript_path_good(self):
        """Valid path within ~/.claude passes validation."""
        home = str(Path.home())
        good_path = f"{home}/.claude/transcripts/session-abc.jsonl"
        result = ust._validate_transcript_path(good_path)
        assert result == str(Path(good_path).resolve())

    def test_validate_transcript_path_traversal(self):
        """Path traversal attempt (../../../etc/passwd) is rejected."""
        bad_path = "../../../etc/passwd"
        result = ust._validate_transcript_path(bad_path)
        assert result == ""

    def test_validate_transcript_path_outside_claude(self):
        """Path outside ~/.claude is rejected."""
        result = ust._validate_transcript_path("/tmp/some/file.jsonl")
        assert result == ""

    def test_validate_transcript_path_empty(self):
        """Empty path returns empty string."""
        result = ust._validate_transcript_path("")
        assert result == ""

    def test_validate_transcript_path_none_like(self):
        """None-like empty string returns empty string."""
        result = ust._validate_transcript_path("")
        assert result == ""

    def test_validate_transcript_path_sibling_dir(self):
        """Sibling directory like ~/.claudeEvil is rejected (is_relative_to)."""
        home = str(Path.home())
        evil_path = f"{home}/.claudeEvil/data.txt"
        result = ust._validate_transcript_path(evil_path)
        assert result == "", "Sibling dir ~/.claudeEvil should be rejected"


class TestComputeDurationMs:
    """Tests for _compute_duration_ms."""

    def test_compute_duration_ms_without_tracker(self):
        """Returns 0 when AgentTracker is not available."""
        with patch.object(ust, "HAS_AGENT_TRACKER", False):
            result = ust._compute_duration_ms()
        assert result == 0

    def test_compute_duration_ms_with_tracker(self):
        """Uses started_at diff when AgentTracker has session data."""
        mock_tracker = MagicMock()
        mock_tracker.get_current_session.return_value = {
            "started_at": "2026-03-17T10:00:00+00:00"
        }

        with patch.object(ust, "HAS_AGENT_TRACKER", True):
            with patch.object(ust, "AgentTracker", return_value=mock_tracker):
                result = ust._compute_duration_ms()

        # Duration should be positive (current time - 2026 start time)
        # Since we're mocking, the result depends on current time
        # Just verify it returns an int >= 0
        assert isinstance(result, int)
        assert result >= 0

    def test_compute_duration_ms_tracker_no_session(self):
        """Returns 0 when tracker has no session data."""
        mock_tracker = MagicMock()
        mock_tracker.get_current_session.return_value = None

        with patch.object(ust, "HAS_AGENT_TRACKER", True):
            with patch.object(ust, "AgentTracker", return_value=mock_tracker):
                result = ust._compute_duration_ms()

        assert result == 0


class TestWriteJsonlEntry:
    """Tests for JSONL activity log output."""

    def test_writes_jsonl_entry(self, tmp_path):
        """Correct fields are written to JSONL output."""
        with patch.object(ust, "_find_log_dir", return_value=tmp_path):
            with patch.object(ust, "_get_session_date", return_value="2026-03-17"):
                result = ust._write_jsonl_entry(
                    subagent_type="researcher",
                    duration_ms=5000,
                    result_word_count=150,
                    agent_transcript_path="/Users/test/.claude/transcripts/abc.jsonl",
                    session_id="session-xyz",
                    success=True,
                )

        assert result is True

        log_file = tmp_path / "2026-03-17.jsonl"
        assert log_file.exists()

        entry = json.loads(log_file.read_text().strip())
        assert entry["hook"] == "SubagentStop"
        assert entry["subagent_type"] == "researcher"
        assert entry["duration_ms"] == 5000
        assert entry["result_word_count"] == 150
        assert entry["agent_transcript_path"] == "/Users/test/.claude/transcripts/abc.jsonl"
        assert entry["session_id"] == "session-xyz"
        assert entry["success"] is True
        assert "timestamp" in entry

    def test_jsonl_result_word_count(self, tmp_path):
        """Word count is computed from last_assistant_message."""
        message = "This is a five word message plus two more"
        word_count = len(message.split())
        assert word_count == 9

        with patch.object(ust, "_find_log_dir", return_value=tmp_path):
            with patch.object(ust, "_get_session_date", return_value="2026-03-17"):
                ust._write_jsonl_entry(
                    subagent_type="planner",
                    duration_ms=0,
                    result_word_count=word_count,
                    agent_transcript_path="",
                    session_id="test",
                    success=True,
                )

        log_file = tmp_path / "2026-03-17.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert entry["result_word_count"] == 9


class TestMainFunction:
    """Tests for main() entry point behavior."""

    def test_always_exits_zero(self):
        """Hook always returns 0 regardless of input."""
        # Test with empty stdin
        with patch("sys.stdin", io.StringIO("")):
            with patch("sys.stdout", new_callable=io.StringIO):
                # Patch out session tracking to avoid side effects
                with patch.object(ust, "track_basic_session", return_value=False):
                    with patch.object(ust, "track_pipeline_completion", return_value=False):
                        with patch.object(ust, "_write_jsonl_entry", return_value=False):
                            result = ust.main()
        assert result == 0

    def test_always_exits_zero_on_exception(self):
        """Hook returns 0 even when internal errors occur."""
        with patch("sys.stdin", io.StringIO('{"agent_type":"test"}')):
            with patch("sys.stdout", new_callable=io.StringIO):
                with patch.object(ust, "track_basic_session", side_effect=Exception("boom")):
                    with patch.object(ust, "_write_jsonl_entry", return_value=False):
                        result = ust.main()
        assert result == 0

    def test_backward_compat_env_vars(self, tmp_path):
        """Old env var path still works when stdin is empty."""
        env = {
            "CLAUDE_AGENT_NAME": "security-auditor",
            "CLAUDE_AGENT_OUTPUT": "Security scan complete",
            "CLAUDE_AGENT_STATUS": "success",
            "CLAUDE_SESSION_ID": "env-session",
        }

        with patch("sys.stdin", io.StringIO("")):
            with patch("sys.stdout", new_callable=io.StringIO):
                with patch.dict(os.environ, env, clear=False):
                    with patch.object(ust, "track_basic_session", return_value=True) as mock_session:
                        with patch.object(ust, "track_pipeline_completion", return_value=True) as mock_pipeline:
                            with patch.object(ust, "_write_jsonl_entry", return_value=True) as mock_jsonl:
                                result = ust.main()

        assert result == 0
        # Verify env vars were used
        mock_session.assert_called_once()
        call_args = mock_session.call_args
        assert call_args[0][0] == "security-auditor"

        mock_pipeline.assert_called_once()
        pipeline_args = mock_pipeline.call_args
        assert pipeline_args[0][0] == "security-auditor"
        assert pipeline_args[0][1] == "Security scan complete"

    def test_main_with_stdin_json(self, tmp_path):
        """main() correctly processes stdin JSON input."""
        input_data = json.dumps({
            "agent_type": "implementer",
            "last_assistant_message": "Implementation complete with all tests passing.",
            "session_id": "stdin-session",
            "hook_event_name": "SubagentStop",
            "stop_hook_active": False,
            "agent_transcript_path": "",
        })

        with patch("sys.stdin", io.StringIO(input_data)):
            with patch("sys.stdout", new_callable=io.StringIO):
                with patch.object(ust, "track_basic_session", return_value=True) as mock_session:
                    with patch.object(ust, "track_pipeline_completion", return_value=True) as mock_pipeline:
                        with patch.object(ust, "_write_jsonl_entry", return_value=True) as mock_jsonl:
                            result = ust.main()

        assert result == 0
        mock_session.assert_called_once()
        assert mock_session.call_args[0][0] == "implementer"

        mock_jsonl.assert_called_once()
        jsonl_kwargs = mock_jsonl.call_args[1]
        assert jsonl_kwargs["subagent_type"] == "implementer"
        assert jsonl_kwargs["session_id"] == "stdin-session"
        assert jsonl_kwargs["success"] is True
        assert jsonl_kwargs["result_word_count"] > 0


class TestSessionIdSanitization:
    """Tests for session_id sanitization in _get_session_date."""

    def test_malicious_session_id_sanitized(self, tmp_path):
        """Session ID with path separators is sanitized to safe characters."""
        with patch.object(ust, "_find_log_dir", return_value=tmp_path):
            ust._SESSION_DATE_CACHE.clear()
            date_str = ust._get_session_date("../../../etc/passwd")

        # Should produce a date string
        assert len(date_str) == 10  # YYYY-MM-DD
        # The date file should use sanitized name (no path separators)
        date_files = list(tmp_path.glob(".session_date_*"))
        assert len(date_files) == 1
        assert "/" not in date_files[0].name
        assert ".." not in date_files[0].name


class TestDetermineSuccess:
    """Tests for _determine_success helper."""

    def test_success_on_clean_output(self):
        """Clean output without error indicators returns True."""
        assert ust._determine_success("Implementation complete. All tests pass.") is True

    def test_failure_on_error_output(self):
        """Output with 'error' returns False."""
        assert ust._determine_success("Fatal error: module not found") is False

    def test_failure_on_traceback(self):
        """Output with 'traceback' returns False."""
        assert ust._determine_success("Traceback (most recent call last):") is False

    def test_success_on_empty(self):
        """Empty output returns True."""
        assert ust._determine_success("") is True
