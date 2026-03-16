"""Tests for Issue #362/#363: batch_agent_verifier.py

Validates that verify_issue_agents correctly parses JSONL logs and
detects missing agents for a given issue in batch processing.
"""

import json
from pathlib import Path

import pytest

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LIB_DIR = PROJECT_ROOT / "plugins/autonomous-dev/lib"
sys.path.insert(0, str(LIB_DIR))

from batch_agent_verifier import (
    DEFAULT_REQUIRED_AGENTS,
    verify_issue_agents,
    _extract_agents_for_issue,
    _entry_matches_issue,
)


def _make_agent_entry(subagent_type: str, issue_id: str) -> str:
    """Create a JSONL line for an agent invocation."""
    entry = {
        "timestamp": "2026-03-17T10:00:00",
        "tool": "Agent",
        "issue_id": issue_id,
        "input_summary": {
            "pipeline_action": "agent_invocation",
            "subagent_type": subagent_type,
        },
        "output_summary": {"success": True},
    }
    return json.dumps(entry)


class TestVerifyIssueAgents:
    """Test verify_issue_agents function."""

    def test_all_agents_present(self, tmp_path: Path):
        """When all required agents are in the log, returns (True, all, [])."""
        log_file = tmp_path / "activity.jsonl"
        lines = [_make_agent_entry(agent, "issue-42") for agent in DEFAULT_REQUIRED_AGENTS]
        log_file.write_text("\n".join(lines))

        passed, present, missing = verify_issue_agents(log_file, "issue-42")

        assert passed is True
        assert set(present) == set(DEFAULT_REQUIRED_AGENTS)
        assert missing == []

    def test_missing_agents_detected(self, tmp_path: Path):
        """When some agents are missing, returns (False, partial, missing)."""
        log_file = tmp_path / "activity.jsonl"
        # Only include 3 of 7 required agents
        partial_agents = ["researcher-local", "planner", "implementer"]
        lines = [_make_agent_entry(agent, "issue-42") for agent in partial_agents]
        log_file.write_text("\n".join(lines))

        passed, present, missing = verify_issue_agents(log_file, "issue-42")

        assert passed is False
        assert set(present) == set(partial_agents)
        expected_missing = {"researcher", "reviewer", "security-auditor", "doc-master"}
        assert set(missing) == expected_missing

    def test_empty_log_file(self, tmp_path: Path):
        """Empty log file returns all agents as missing."""
        log_file = tmp_path / "activity.jsonl"
        log_file.write_text("")

        passed, present, missing = verify_issue_agents(log_file, "issue-42")

        assert passed is False
        assert present == []
        assert set(missing) == set(DEFAULT_REQUIRED_AGENTS)

    def test_nonexistent_log_file(self, tmp_path: Path):
        """Non-existent log file returns all agents as missing."""
        log_file = tmp_path / "nonexistent.jsonl"

        passed, present, missing = verify_issue_agents(log_file, "issue-42")

        assert passed is False
        assert present == []
        assert set(missing) == set(DEFAULT_REQUIRED_AGENTS)

    def test_custom_required_agents(self, tmp_path: Path):
        """Custom required_agents list is respected."""
        log_file = tmp_path / "activity.jsonl"
        custom_agents = ["implementer", "reviewer"]
        lines = [_make_agent_entry(agent, "issue-1") for agent in custom_agents]
        log_file.write_text("\n".join(lines))

        passed, present, missing = verify_issue_agents(
            log_file, "issue-1", required_agents=custom_agents
        )

        assert passed is True
        assert set(present) == set(custom_agents)
        assert missing == []

    def test_filters_by_issue_id(self, tmp_path: Path):
        """Only agents for the specified issue are counted."""
        log_file = tmp_path / "activity.jsonl"
        # Agents for issue-42
        lines_42 = [_make_agent_entry(agent, "issue-42") for agent in DEFAULT_REQUIRED_AGENTS]
        # Agents for a different issue
        lines_99 = [_make_agent_entry("implementer", "issue-99")]
        log_file.write_text("\n".join(lines_42 + lines_99))

        # Check issue-42 - should pass
        passed_42, _, _ = verify_issue_agents(log_file, "issue-42")
        assert passed_42 is True

        # Check issue-99 - should fail (only has implementer)
        passed_99, present_99, missing_99 = verify_issue_agents(log_file, "issue-99")
        assert passed_99 is False
        assert present_99 == ["implementer"]


class TestEntryMatchesIssue:
    """Test _entry_matches_issue helper."""

    def test_matches_issue_id_field(self):
        entry = {"issue_id": "issue-42", "tool": "Agent"}
        assert _entry_matches_issue(entry, "issue-42") is True

    def test_matches_session_context_field(self):
        entry = {"session_context": "batch-issue-42-run", "tool": "Agent"}
        assert _entry_matches_issue(entry, "issue-42") is True

    def test_matches_nested_input_summary(self):
        entry = {
            "tool": "Agent",
            "input_summary": {"issue_id": "issue-42"},
        }
        assert _entry_matches_issue(entry, "issue-42") is True

    def test_no_match_different_issue(self):
        entry = {"issue_id": "issue-99", "tool": "Agent"}
        assert _entry_matches_issue(entry, "issue-42") is False

    def test_no_match_empty_entry(self):
        assert _entry_matches_issue({}, "issue-42") is False


class TestBackwardCompatibility:
    """Verify old 'Task' tool name is accepted alongside 'Agent'."""

    def test_task_tool_name_accepted(self, tmp_path: Path):
        """Entries with tool='Task' should be recognized as agent invocations."""
        log_file = tmp_path / "activity.jsonl"
        entry = {
            "timestamp": "2026-03-17T10:00:00",
            "tool": "Task",
            "issue_id": "issue-1",
            "input_summary": {
                "pipeline_action": "agent_invocation",
                "subagent_type": "implementer",
            },
            "output_summary": {"success": True},
        }
        log_file.write_text(json.dumps(entry))

        agents = _extract_agents_for_issue(log_file, "issue-1")
        assert "implementer" in agents
