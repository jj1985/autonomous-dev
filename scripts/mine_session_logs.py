#!/usr/bin/env python3
"""Mine session logs for reviewer benchmark samples.

Parses Claude Code session activity logs to identify reviewer-related
events and potential missed defects for benchmark expansion.

Usage:
    python scripts/mine_session_logs.py \
        --logs-dir .claude/logs/activity \
        --output session_candidates.json \
        --max-samples 50

GitHub Issue: #573
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_session_logs(logs_dir: Path) -> List[Dict[str, Any]]:
    """Parse JSONL session activity log files.

    Reads all .jsonl files in the logs directory and returns
    parsed event entries.

    Args:
        logs_dir: Path to the directory containing JSONL log files

    Returns:
        List of parsed event dicts from all log files.
    """
    events: List[Dict[str, Any]] = []

    if not logs_dir.exists():
        return events

    for log_file in sorted(logs_dir.glob("*.jsonl")):
        try:
            for line in log_file.read_text().strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError:
                    continue
        except (OSError, UnicodeDecodeError):
            continue

    return events


def extract_reviewer_sessions(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter events for reviewer-related sessions.

    Looks for events from the reviewer agent, PostToolUse hooks
    related to reviewing, and Stop events with reviewer context.

    Args:
        events: All parsed session events

    Returns:
        Filtered list of reviewer-related events.
    """
    reviewer_events: List[Dict[str, Any]] = []

    for event in events:
        # Check for reviewer agent events
        agent = event.get("agent", "")
        hook = event.get("hook", "")
        tool_name = event.get("tool_name", "")

        is_reviewer = (
            agent == "reviewer"
            or (hook in ("PostToolUse", "Stop") and "reviewer" in str(event))
            or tool_name == "Agent" and "reviewer" in event.get("agent", "")
        )

        if is_reviewer:
            reviewer_events.append(event)

    return reviewer_events


def identify_misses(sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Identify potential reviewer misses from session data.

    Heuristic: look for sessions where the reviewer approved but
    a subsequent fix commit was needed, or where duration was very short.

    Args:
        sessions: Reviewer-related session events

    Returns:
        List of events flagged as potential misses.
    """
    misses: List[Dict[str, Any]] = []

    for event in sessions:
        # Short duration reviewer sessions may indicate rushed review
        duration_ms = event.get("duration_ms", 0)
        if duration_ms and duration_ms < 5000:
            misses.append({
                **event,
                "miss_reason": "Very short review duration (<5s)",
            })
            continue

        # Sessions with no findings but tool errors
        if event.get("error"):
            misses.append({
                **event,
                "miss_reason": "Review session had errors",
            })

    return misses


def build_sample_from_session(session_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build a benchmark sample from session log data.

    Constructs a sample dict compatible with the benchmark dataset format
    from a reviewer session event.

    Args:
        session_data: A single reviewer session event dict

    Returns:
        Sample dict compatible with dataset.json format.
    """
    session_id = session_data.get("session_id", "unknown")
    timestamp = session_data.get("timestamp", "")
    agent = session_data.get("agent", "reviewer")
    miss_reason = session_data.get("miss_reason", "")

    sample_id = f"session-{session_id}-{timestamp[:10] if timestamp else 'unknown'}"

    return {
        "sample_id": sample_id,
        "source_repo": "autonomous-dev",
        "issue_ref": "",
        "commit_sha": "",
        "diff_text": session_data.get("diff_text", "# No diff available from session log"),
        "expected_verdict": "REQUEST_CHANGES",
        "expected_categories": [],
        "category_tags": ["session-log"],
        "description": miss_reason or f"Reviewer session {session_id}",
        "difficulty": "medium",
        "defect_category": "",
    }


def main() -> None:
    """Run the session log mining CLI."""
    parser = argparse.ArgumentParser(
        description="Mine session logs for reviewer benchmark samples"
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=Path(".claude/logs/activity"),
        help="Path to session activity logs directory (default: .claude/logs/activity)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=50,
        help="Maximum number of samples to output (default: 50)",
    )

    args = parser.parse_args()

    print(f"Parsing session logs from {args.logs_dir}...", file=sys.stderr)
    events = parse_session_logs(args.logs_dir)
    print(f"Found {len(events)} total events", file=sys.stderr)

    reviewer_sessions = extract_reviewer_sessions(events)
    print(f"Found {len(reviewer_sessions)} reviewer-related events", file=sys.stderr)

    misses = identify_misses(reviewer_sessions)
    print(f"Identified {len(misses)} potential misses", file=sys.stderr)

    candidates: List[Dict[str, Any]] = []
    for miss in misses[: args.max_samples]:
        sample = build_sample_from_session(miss)
        candidates.append(sample)

    output = json.dumps(candidates, indent=2)
    if args.output:
        args.output.write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
