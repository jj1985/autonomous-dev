"""Unit tests for mine_session_logs.py script.

Tests JSONL parsing, reviewer session filtering, miss identification,
and sample building from session data. Uses fixture data, not real logs.

GitHub Issue: #573
"""

import json
import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[3] / "scripts"),
)

from mine_session_logs import (
    build_sample_from_session,
    extract_reviewer_sessions,
    identify_misses,
    parse_session_logs,
)


class TestParseSessionLogs:
    """Test parse_session_logs JSONL parsing."""

    def test_parse_valid_jsonl(self, tmp_path: Path) -> None:
        log_file = tmp_path / "2026-03-28.jsonl"
        entries = [
            {"timestamp": "2026-03-28T08:00:00Z", "hook": "PostToolUse", "tool_name": "Agent"},
            {"timestamp": "2026-03-28T08:01:00Z", "hook": "Stop", "agent": "reviewer"},
        ]
        log_file.write_text("\n".join(json.dumps(e) for e in entries))

        events = parse_session_logs(tmp_path)
        assert len(events) == 2
        assert events[0]["hook"] == "PostToolUse"

    def test_parse_empty_directory(self, tmp_path: Path) -> None:
        events = parse_session_logs(tmp_path)
        assert events == []

    def test_parse_nonexistent_directory(self, tmp_path: Path) -> None:
        events = parse_session_logs(tmp_path / "nonexistent")
        assert events == []

    def test_parse_skips_invalid_json_lines(self, tmp_path: Path) -> None:
        log_file = tmp_path / "2026-03-28.jsonl"
        log_file.write_text(
            '{"valid": true}\n'
            'not json\n'
            '{"also_valid": true}\n'
        )
        events = parse_session_logs(tmp_path)
        assert len(events) == 2

    def test_parse_skips_empty_lines(self, tmp_path: Path) -> None:
        log_file = tmp_path / "2026-03-28.jsonl"
        log_file.write_text('{"a": 1}\n\n\n{"b": 2}\n')
        events = parse_session_logs(tmp_path)
        assert len(events) == 2

    def test_parse_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "2026-03-27.jsonl").write_text('{"day": 27}\n')
        (tmp_path / "2026-03-28.jsonl").write_text('{"day": 28}\n')
        events = parse_session_logs(tmp_path)
        assert len(events) == 2


class TestExtractReviewerSessions:
    """Test extract_reviewer_sessions filtering."""

    def test_filter_reviewer_agent_events(self) -> None:
        events = [
            {"agent": "reviewer", "hook": "PostToolUse"},
            {"agent": "implementer", "hook": "PostToolUse"},
            {"agent": "reviewer", "hook": "Stop"},
        ]
        result = extract_reviewer_sessions(events)
        assert len(result) == 2

    def test_filter_by_hook_context(self) -> None:
        events = [
            {"hook": "PostToolUse", "tool_name": "Agent", "agent": "reviewer"},
            {"hook": "PostToolUse", "tool_name": "Bash", "agent": ""},
        ]
        result = extract_reviewer_sessions(events)
        assert len(result) == 1

    def test_empty_events_returns_empty(self) -> None:
        result = extract_reviewer_sessions([])
        assert result == []

    def test_no_reviewer_events(self) -> None:
        events = [
            {"agent": "implementer", "hook": "PostToolUse"},
            {"agent": "planner", "hook": "Stop"},
        ]
        result = extract_reviewer_sessions(events)
        assert result == []

    def test_reviewer_in_string_context(self) -> None:
        events = [
            {"hook": "Stop", "message": "reviewer finished analysis"},
        ]
        result = extract_reviewer_sessions(events)
        assert len(result) == 1


class TestIdentifyMisses:
    """Test identify_misses heuristic."""

    def test_short_duration_flagged(self) -> None:
        sessions = [
            {"session_id": "s1", "duration_ms": 2000, "agent": "reviewer"},
            {"session_id": "s2", "duration_ms": 60000, "agent": "reviewer"},
        ]
        misses = identify_misses(sessions)
        assert len(misses) == 1
        assert misses[0]["session_id"] == "s1"
        assert "short" in misses[0]["miss_reason"].lower()

    def test_error_session_flagged(self) -> None:
        sessions = [
            {"session_id": "s1", "duration_ms": 30000, "error": "timeout"},
        ]
        misses = identify_misses(sessions)
        assert len(misses) == 1
        assert "error" in misses[0]["miss_reason"].lower()

    def test_normal_session_not_flagged(self) -> None:
        sessions = [
            {"session_id": "s1", "duration_ms": 30000, "agent": "reviewer"},
        ]
        misses = identify_misses(sessions)
        assert misses == []

    def test_empty_sessions(self) -> None:
        misses = identify_misses([])
        assert misses == []

    def test_no_duration_not_flagged(self) -> None:
        sessions = [
            {"session_id": "s1", "agent": "reviewer"},
        ]
        misses = identify_misses(sessions)
        assert misses == []


class TestBuildSampleFromSession:
    """Test build_sample_from_session output schema."""

    def test_basic_session_sample(self) -> None:
        session_data = {
            "session_id": "abc123",
            "timestamp": "2026-03-28T08:00:00Z",
            "agent": "reviewer",
            "miss_reason": "Very short review duration (<5s)",
        }
        sample = build_sample_from_session(session_data)

        assert "abc123" in sample["sample_id"]
        assert sample["source_repo"] == "autonomous-dev"
        assert sample["expected_verdict"] == "REQUEST_CHANGES"
        assert sample["difficulty"] == "medium"
        assert "session-log" in sample["category_tags"]

    def test_sample_has_all_required_fields(self) -> None:
        session_data = {"session_id": "xyz", "timestamp": "2026-01-01"}
        sample = build_sample_from_session(session_data)

        required_keys = {
            "sample_id", "source_repo", "issue_ref", "commit_sha",
            "diff_text", "expected_verdict", "expected_categories",
            "category_tags", "description", "difficulty", "defect_category",
        }
        assert required_keys.issubset(set(sample.keys()))

    def test_missing_session_id_uses_unknown(self) -> None:
        sample = build_sample_from_session({})
        assert "unknown" in sample["sample_id"]

    def test_miss_reason_in_description(self) -> None:
        session_data = {
            "session_id": "s1",
            "miss_reason": "Review had errors",
        }
        sample = build_sample_from_session(session_data)
        assert sample["description"] == "Review had errors"
