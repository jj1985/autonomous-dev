#!/usr/bin/env python3
"""
Unit tests for Retrospective Analyzer Library (Issue #598).

Tests session log loading, drift detection (repeated corrections, config drift,
memory rot), and unified diff formatting.

Date: 2026-03-29
Issue: #598 (Add /retrospective command and scheduled drift detection)
Agent: implementer
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add lib directory to path for imports
lib_dir = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(lib_dir))

from retrospective_analyzer import (
    DriftCategory,
    DriftFinding,
    DriftSeverity,
    ProposedEdit,
    RetrospectiveConfig,
    SessionSummary,
    detect_config_drift,
    detect_memory_rot,
    detect_repeated_corrections,
    format_as_unified_diff,
    load_session_summaries,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_logs_dir(tmp_path):
    """Create a temporary logs directory with sample JSONL files."""
    logs_dir = tmp_path / "activity"
    logs_dir.mkdir()
    return logs_dir


@pytest.fixture
def sample_events():
    """Sample JSONL events for testing."""
    return [
        {
            "timestamp": "2026-03-28T10:00:00+00:00",
            "hook": "UserPromptSubmit",
            "session_id": "session-1",
            "prompt": "no, that's wrong, revert that change",
        },
        {
            "timestamp": "2026-03-28T10:01:00+00:00",
            "hook": "PreToolUse",
            "session_id": "session-1",
            "tool": "Bash",
            "decision": "allow",
        },
        {
            "timestamp": "2026-03-28T10:02:00+00:00",
            "hook": "Stop",
            "session_id": "session-1",
            "message_preview": "Implemented the feature successfully",
        },
        {
            "timestamp": "2026-03-28T10:05:00+00:00",
            "hook": "UserPromptSubmit",
            "session_id": "session-2",
            "prompt": "implement JWT authentication",
        },
        {
            "timestamp": "2026-03-28T10:06:00+00:00",
            "hook": "Stop",
            "session_id": "session-2",
            "message_preview": "JWT auth is ready",
        },
    ]


def _write_jsonl(logs_dir: Path, filename: str, events: list) -> Path:
    """Write events to a JSONL file."""
    filepath = logs_dir / filename
    with open(filepath, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    return filepath


# =============================================================================
# Test: load_session_summaries
# =============================================================================


class TestLoadSessionSummaries:
    """Tests for loading and parsing session activity logs."""

    def test_empty_directory(self, temp_logs_dir):
        """Empty logs directory returns empty list."""
        result = load_session_summaries(temp_logs_dir)
        assert result == []

    def test_groups_by_session_id(self, temp_logs_dir, sample_events):
        """Events are correctly grouped by session_id."""
        _write_jsonl(temp_logs_dir, "2026-03-28.jsonl", sample_events)
        result = load_session_summaries(temp_logs_dir)
        session_ids = {s.session_id for s in result}
        assert "session-1" in session_ids
        assert "session-2" in session_ids

    def test_max_sessions_cap(self, temp_logs_dir):
        """max_sessions parameter limits returned sessions."""
        # Create events for 5 different sessions
        events = []
        for i in range(5):
            events.append(
                {
                    "timestamp": f"2026-03-28T10:{i:02d}:00+00:00",
                    "hook": "Stop",
                    "session_id": f"session-{i}",
                    "message_preview": f"Message {i}",
                }
            )
        _write_jsonl(temp_logs_dir, "2026-03-28.jsonl", events)
        result = load_session_summaries(temp_logs_dir, max_sessions=3)
        assert len(result) <= 3

    def test_stop_message_extraction(self, temp_logs_dir, sample_events):
        """Stop hook message_preview fields are extracted."""
        _write_jsonl(temp_logs_dir, "2026-03-28.jsonl", sample_events)
        result = load_session_summaries(temp_logs_dir)
        session_1 = next(s for s in result if s.session_id == "session-1")
        assert "Implemented the feature successfully" in session_1.stop_messages

    def test_correction_detection(self, temp_logs_dir, sample_events):
        """UserPromptSubmit events with correction patterns are detected."""
        _write_jsonl(temp_logs_dir, "2026-03-28.jsonl", sample_events)
        result = load_session_summaries(temp_logs_dir)
        session_1 = next(s for s in result if s.session_id == "session-1")
        # "no, that's wrong, revert that change" should match multiple patterns
        assert len(session_1.corrections) > 0

    def test_invalid_directory_raises(self, tmp_path):
        """Non-existent directory raises ValueError."""
        bad_dir = tmp_path / "nonexistent"
        with pytest.raises(ValueError, match="does not exist"):
            load_session_summaries(bad_dir)

    def test_malformed_json_skipped(self, temp_logs_dir):
        """Lines with invalid JSON are silently skipped."""
        filepath = temp_logs_dir / "2026-03-28.jsonl"
        with open(filepath, "w") as f:
            f.write("not valid json\n")
            f.write(json.dumps({
                "hook": "Stop",
                "session_id": "s1",
                "message_preview": "valid",
            }) + "\n")
        result = load_session_summaries(temp_logs_dir)
        assert len(result) == 1

    def test_commands_used_extracted(self, temp_logs_dir, sample_events):
        """Tool names are extracted into commands_used."""
        _write_jsonl(temp_logs_dir, "2026-03-28.jsonl", sample_events)
        result = load_session_summaries(temp_logs_dir)
        session_1 = next(s for s in result if s.session_id == "session-1")
        assert "Bash" in session_1.commands_used


# =============================================================================
# Test: detect_repeated_corrections
# =============================================================================


class TestDetectRepeatedCorrections:
    """Tests for cross-session correction pattern detection."""

    def test_below_threshold_returns_empty(self):
        """Fewer sessions than threshold produces no findings."""
        summaries = [
            SessionSummary(
                session_id="s1",
                date="2026-03-28",
                corrections=["no, that's wrong"],
            ),
            SessionSummary(
                session_id="s2",
                date="2026-03-27",
                corrections=["no, revert that"],
            ),
        ]
        result = detect_repeated_corrections(summaries, min_threshold=3)
        assert result == []

    def test_at_threshold_produces_finding(self):
        """Exactly threshold sessions with same pattern produces finding."""
        summaries = [
            SessionSummary(
                session_id=f"s{i}",
                date=f"2026-03-{28-i:02d}",
                corrections=["no, that's wrong"],
            )
            for i in range(3)
        ]
        result = detect_repeated_corrections(summaries, min_threshold=3)
        assert len(result) > 0
        assert result[0].category == DriftCategory.REPEATED_CORRECTION

    def test_cross_session_required(self):
        """Multiple corrections in a single session do not meet threshold."""
        summaries = [
            SessionSummary(
                session_id="s1",
                date="2026-03-28",
                corrections=["no", "no", "no", "no"],
            ),
        ]
        result = detect_repeated_corrections(summaries, min_threshold=3)
        assert result == []

    def test_empty_summaries(self):
        """Empty summaries list returns empty findings."""
        result = detect_repeated_corrections([])
        assert result == []

    def test_severity_escalation(self):
        """More sessions than 2x threshold escalates to IMMEDIATE."""
        summaries = [
            SessionSummary(
                session_id=f"s{i}",
                date=f"2026-03-{28-i:02d}",
                corrections=["no, revert"],
            )
            for i in range(6)
        ]
        result = detect_repeated_corrections(summaries, min_threshold=3)
        assert len(result) > 0
        immediate_findings = [f for f in result if f.severity == DriftSeverity.IMMEDIATE]
        assert len(immediate_findings) > 0


# =============================================================================
# Test: detect_config_drift
# =============================================================================


class TestDetectConfigDrift:
    """Tests for git-based config drift detection."""

    @patch("retrospective_analyzer.subprocess.run")
    def test_no_changes_returns_empty(self, mock_run, tmp_path):
        """No git diff output means no drift findings."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = detect_config_drift(tmp_path)
        assert result == []

    @patch("retrospective_analyzer.subprocess.run")
    def test_project_md_changed(self, mock_run, tmp_path):
        """Changes to PROJECT.md produce a finding."""
        def side_effect(*args, **kwargs):
            cmd = args[0]
            if ".claude/PROJECT.md" in cmd:
                return MagicMock(
                    stdout="--- a/.claude/PROJECT.md\n+++ b/.claude/PROJECT.md\n+new goal line\n+another line",
                    returncode=0,
                )
            return MagicMock(stdout="", returncode=0)

        mock_run.side_effect = side_effect
        result = detect_config_drift(tmp_path)
        assert len(result) == 1
        assert result[0].category == DriftCategory.CONFIG_DRIFT
        assert "PROJECT.md" in result[0].description

    @patch("retrospective_analyzer.subprocess.run")
    def test_claude_md_changed(self, mock_run, tmp_path):
        """Changes to CLAUDE.md produce a finding."""
        def side_effect(*args, **kwargs):
            cmd = args[0]
            if "CLAUDE.md" in cmd and ".claude" not in cmd[cmd.index("CLAUDE.md") - 1]:
                return MagicMock(
                    stdout="--- a/CLAUDE.md\n+++ b/CLAUDE.md\n+new rule",
                    returncode=0,
                )
            return MagicMock(stdout="", returncode=0)

        mock_run.side_effect = side_effect
        result = detect_config_drift(tmp_path)
        # At least one finding for CLAUDE.md changes
        claude_findings = [f for f in result if "CLAUDE.md" in f.description]
        assert len(claude_findings) >= 1

    @patch("retrospective_analyzer.subprocess.run")
    def test_git_error_handled_gracefully(self, mock_run, tmp_path):
        """Git command failures are handled without raising."""
        mock_run.side_effect = subprocess.SubprocessError("git not found")
        result = detect_config_drift(tmp_path)
        assert result == []


# =============================================================================
# Test: detect_memory_rot
# =============================================================================


class TestDetectMemoryRot:
    """Tests for stale memory entry detection."""

    def test_recent_entry_not_flagged(self, tmp_path):
        """Entries within decay period are not flagged."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        (memory_dir / "MEMORY.md").write_text(
            f"# Recent Learning ({today})\nThis is very recent content\n"
        )
        result = detect_memory_rot(memory_dir, [], decay_days=90)
        assert result == []

    def test_stale_entry_flagged(self, tmp_path):
        """Entries older than decay period with no corroboration are flagged."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        old_date = (datetime.now(timezone.utc) - timedelta(days=120)).strftime("%Y-%m-%d")
        (memory_dir / "MEMORY.md").write_text(
            f"# Old Learning ({old_date})\nSome obscure unique content xyz123\n"
        )
        result = detect_memory_rot(memory_dir, [], decay_days=90)
        assert len(result) == 1
        assert result[0].category == DriftCategory.MEMORY_ROT
        assert result[0].severity == DriftSeverity.ARCHIVE

    def test_corroborated_entry_not_flagged(self, tmp_path):
        """Stale entries corroborated by recent sessions are not flagged."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        old_date = (datetime.now(timezone.utc) - timedelta(days=120)).strftime("%Y-%m-%d")
        (memory_dir / "MEMORY.md").write_text(
            f"# Training Pipeline ({old_date})\n"
            f"Training pipeline learned important patterns about models\n"
        )
        # Create summaries that reference the same content
        summaries = [
            SessionSummary(
                session_id="s1",
                date="2026-03-28",
                stop_messages=["Discussed training pipeline and learned important patterns about models"],
            ),
        ]
        result = detect_memory_rot(memory_dir, summaries, decay_days=90)
        assert result == []

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        """Non-existent memory directory returns empty list."""
        result = detect_memory_rot(tmp_path / "nonexistent", [])
        assert result == []

    def test_proposed_edit_included(self, tmp_path):
        """Stale findings include a proposed REMOVE edit."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        old_date = (datetime.now(timezone.utc) - timedelta(days=120)).strftime("%Y-%m-%d")
        (memory_dir / "MEMORY.md").write_text(
            f"# Obsolete Thing ({old_date})\nUnique content qwerty789\n"
        )
        result = detect_memory_rot(memory_dir, [], decay_days=90)
        assert len(result) == 1
        assert result[0].proposed_edit is not None
        assert result[0].proposed_edit.edit_type == "REMOVE"


# =============================================================================
# Test: format_as_unified_diff
# =============================================================================


class TestFormatAsUnifiedDiff:
    """Tests for unified diff formatting."""

    def test_remove_format(self):
        """REMOVE edits show deleted lines with - prefix."""
        edit = ProposedEdit(
            file_path="MEMORY.md",
            edit_type="REMOVE",
            section="Old Section",
            current_content="line1\nline2",
            proposed_content="",
            rationale="Entry is stale",
        )
        diff = format_as_unified_diff(edit)
        assert "--- a/MEMORY.md" in diff
        assert "+++ b/MEMORY.md" in diff
        assert "-line1" in diff
        assert "-line2" in diff

    def test_add_format(self):
        """ADD edits show added lines with + prefix."""
        edit = ProposedEdit(
            file_path="PROJECT.md",
            edit_type="ADD",
            section="New Section",
            current_content="",
            proposed_content="new rule\nanother rule",
            rationale="Learned from corrections",
        )
        diff = format_as_unified_diff(edit)
        assert "+new rule" in diff
        assert "+another rule" in diff

    def test_modify_format(self):
        """MODIFY edits show both removed and added lines."""
        edit = ProposedEdit(
            file_path="CLAUDE.md",
            edit_type="MODIFY",
            section="Rules",
            current_content="old rule",
            proposed_content="new rule",
            rationale="Rule updated",
        )
        diff = format_as_unified_diff(edit)
        assert "-old rule" in diff
        assert "+new rule" in diff

    def test_rationale_included(self):
        """Rationale is included as a comment."""
        edit = ProposedEdit(
            file_path="test.md",
            edit_type="ADD",
            section="Test",
            current_content="",
            proposed_content="content",
            rationale="test reason",
        )
        diff = format_as_unified_diff(edit)
        assert "# Rationale: test reason" in diff


# =============================================================================
# Test: Resource Limits and Security
# =============================================================================


class TestResourceLimits:
    """Tests for resource limit enforcement."""

    def test_events_per_session_capped(self, temp_logs_dir):
        """Sessions with more than MAX_EVENTS_PER_SESSION events are capped."""
        # Create 250 events for one session (exceeds MAX_EVENTS_PER_SESSION=200)
        events = []
        for i in range(250):
            events.append({
                "timestamp": f"2026-03-28T10:{i // 60:02d}:{i % 60:02d}+00:00",
                "hook": "PreToolUse",
                "session_id": "flood-session",
                "tool": f"Tool{i}",
            })
        _write_jsonl(temp_logs_dir, "2026-03-28.jsonl", events)
        result = load_session_summaries(temp_logs_dir)
        assert len(result) == 1
        # Commands should be capped (not all 250 tools)
        assert len(result[0].commands_used) <= 200

    def test_max_sessions_absolute_cap(self, temp_logs_dir):
        """max_sessions cannot exceed MAX_SESSIONS constant (50)."""
        events = []
        for i in range(60):
            events.append({
                "timestamp": f"2026-03-28T10:00:{i:02d}+00:00",
                "hook": "Stop",
                "session_id": f"s-{i}",
                "message_preview": f"msg {i}",
            })
        _write_jsonl(temp_logs_dir, "2026-03-28.jsonl", events)
        # Request 100 sessions but should be capped at 50
        result = load_session_summaries(temp_logs_dir, max_sessions=100)
        assert len(result) <= 50


# =============================================================================
# Test: Dataclasses
# =============================================================================


class TestDataclasses:
    """Tests for dataclass defaults and construction."""

    def test_retrospective_config_defaults(self):
        """RetrospectiveConfig has correct defaults."""
        config = RetrospectiveConfig()
        assert config.max_sessions == 20
        assert config.decay_days == 90
        assert config.min_correction_threshold == 3
        assert config.dry_run is False

    def test_session_summary_defaults(self):
        """SessionSummary fields default to empty lists."""
        summary = SessionSummary(session_id="s1", date="2026-03-28")
        assert summary.stop_messages == []
        assert summary.commands_used == []
        assert summary.corrections == []
        assert summary.topics == []

    def test_drift_finding_construction(self):
        """DriftFinding can be constructed with all fields."""
        finding = DriftFinding(
            category=DriftCategory.REPEATED_CORRECTION,
            severity=DriftSeverity.IMMEDIATE,
            description="Test finding",
            evidence=["evidence1"],
        )
        assert finding.category == DriftCategory.REPEATED_CORRECTION
        assert finding.severity == DriftSeverity.IMMEDIATE
        assert finding.proposed_edit is None
