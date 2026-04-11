#!/usr/bin/env python3
"""
Batch Agent Verifier - Issue #362 / #363

Reads JSONL activity logs and verifies that all required pipeline agents
were invoked for a given issue during batch processing. Used as a HARD GATE
to prevent progressive agent shortcutting in later batch issues.

Usage:
    from batch_agent_verifier import verify_issue_agents
    passed, present, missing = verify_issue_agents(log_path, "issue-123")

See Also:
    - plugins/autonomous-dev/lib/pipeline_intent_validator.py (log parsing)
    - plugins/autonomous-dev/commands/implement-batch.md (HARD GATE)
    - GitHub Issues #362, #363
"""

import json
from pathlib import Path
from typing import List, Optional, Tuple

# Tool names for agent invocations — Claude Code renamed "Task" to "Agent"
# but old logs still use "Task". Accept both for backward compatibility.
AGENT_TOOL_NAMES = {"Task", "Agent"}

# Default required agents for the acceptance-first pipeline
# NOTE: continuous-improvement-analyst is explicitly included here (Issue #505).
# The CI analyst MUST run for EVERY issue including the LAST one in the batch.
DEFAULT_REQUIRED_AGENTS = [
    "researcher-local",
    "researcher",
    "planner",
    "implementer",
    "spec-validator",
    "reviewer",
    "security-auditor",
    "doc-master",
    "continuous-improvement-analyst",
]


def verify_issue_agents(
    log_file: Path,
    issue_id: str,
    *,
    required_agents: Optional[List[str]] = None,
) -> Tuple[bool, List[str], List[str]]:
    """Verify that all required agents were invoked for a specific issue.

    Reads the JSONL activity log, filters entries matching the issue's session
    context, and checks that every required agent was invoked at least once.

    Args:
        log_file: Path to JSONL activity log file.
        issue_id: Issue identifier to filter log entries (matched against
            session_context, issue_id, or run_id fields).
        required_agents: List of agent subagent_type values that must be
            present. Defaults to the 8 acceptance-first pipeline agents
            (including continuous-improvement-analyst, Issue #505).

    Returns:
        Tuple of (all_present, present_agents, missing_agents) where:
            - all_present: True if every required agent was found
            - present_agents: List of required agents that were found
            - missing_agents: List of required agents that were NOT found

    Raises:
        No exceptions raised; returns (False, [], required_agents) on errors.

    Example:
        >>> passed, present, missing = verify_issue_agents(
        ...     Path("logs/activity.jsonl"), "issue-42"
        ... )
        >>> if not passed:
        ...     print(f"Missing agents: {missing}")
    """
    if required_agents is None:
        required_agents = list(DEFAULT_REQUIRED_AGENTS)

    # Parse log and collect agent types invoked for this issue
    invoked_agents = _extract_agents_for_issue(log_file, issue_id)

    present = [a for a in required_agents if a in invoked_agents]
    missing = [a for a in required_agents if a not in invoked_agents]

    return (len(missing) == 0, present, missing)


def _extract_agents_for_issue(log_file: Path, issue_id: str) -> set:
    """Extract the set of agent subagent_type values invoked for a given issue.

    Parses each JSONL line looking for agent invocations that match
    the issue_id in any of these fields:
        - session_context
        - issue_id
        - run_id
        - batch_issue_id
        - input_summary.issue_id

    Args:
        log_file: Path to JSONL log file.
        issue_id: Issue identifier to match.

    Returns:
        Set of subagent_type strings found for the issue.
    """
    agents: set = set()

    if not log_file.exists():
        return agents

    try:
        text = log_file.read_text().strip()
    except (OSError, PermissionError):
        return agents

    if not text:
        return agents

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Check if this entry relates to the issue
        if not _entry_matches_issue(entry, issue_id):
            continue

        # Check if this is an agent invocation
        tool = entry.get("tool", "")
        if tool not in AGENT_TOOL_NAMES:
            continue

        input_summary = entry.get("input_summary", {})
        pipeline_action = input_summary.get("pipeline_action", "")

        # Accept entries with agent_invocation action OR subagent_type set
        subagent_type = input_summary.get("subagent_type", "")
        if not subagent_type:
            subagent_type = entry.get("subagent_type", "")

        if subagent_type:
            agents.add(subagent_type)

    return agents


def _entry_matches_issue(entry: dict, issue_id: str) -> bool:
    """Check if a log entry belongs to the given issue.

    Args:
        entry: Parsed JSON log entry.
        issue_id: Issue identifier to match.

    Returns:
        True if the entry matches the issue.
    """
    # Direct field matches
    for field in ("session_context", "issue_id", "run_id", "batch_issue_id"):
        value = entry.get(field, "")
        if isinstance(value, str) and issue_id in value:
            return True

    # Nested in input_summary
    input_summary = entry.get("input_summary", {})
    if isinstance(input_summary, dict):
        for field in ("issue_id", "session_context", "batch_issue_id"):
            value = input_summary.get(field, "")
            if isinstance(value, str) and issue_id in value:
                return True

    return False
