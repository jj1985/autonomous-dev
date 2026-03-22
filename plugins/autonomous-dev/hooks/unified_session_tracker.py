#!/usr/bin/env -S uv run --script --quiet --no-project
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Unified Session Tracker Hook - Dispatcher for SubagentStop Session Tracking

Consolidates SubagentStop session tracking hooks:
- session_tracker.py (basic session logging)
- log_agent_completion.py (structured pipeline tracking)
- auto_update_project_progress.py (PROJECT.md progress updates)

Hook: SubagentStop (runs when a subagent completes)

Input: JSON via stdin (provided by Claude Code SubagentStop hook).
Fields: agent_type, agent_id, agent_transcript_path, last_assistant_message,
        session_id, hook_event_name, stop_hook_active.

Environment Variables (opt-in/opt-out):
    TRACK_SESSIONS=true/false (default: true)
    TRACK_PIPELINE=true/false (default: true)
    AUTO_UPDATE_PROGRESS=true/false (default: false)

Exit codes:
    0: Always (non-blocking hook)

Usage:
    # As SubagentStop hook (automatic via stdin)
    echo '{"agent_type":"researcher",...}' | python unified_session_tracker.py
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


# ============================================================================
# Dynamic Library Discovery
# ============================================================================

def is_running_under_uv() -> bool:
    """Detect if script is running under UV."""
    return "UV_PROJECT_ENVIRONMENT" in os.environ

def find_lib_dir() -> Optional[Path]:
    """
    Find the lib directory dynamically.

    Searches:
    1. Relative to this file: ../lib
    2. In project root: plugins/autonomous-dev/lib
    3. In global install: ~/.autonomous-dev/lib

    Returns:
        Path to lib directory or None if not found
    """
    candidates = [
        Path(__file__).parent.parent / "lib",  # Relative to hooks/
        Path.cwd() / "plugins" / "autonomous-dev" / "lib",  # Project root
        Path.home() / ".autonomous-dev" / "lib",  # Global install
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


# Add lib to path
LIB_DIR = find_lib_dir()
if LIB_DIR:
    if not is_running_under_uv():
        sys.path.insert(0, str(LIB_DIR))

# Optional imports with graceful fallback
try:
    from agent_tracker import AgentTracker
    HAS_AGENT_TRACKER = True
except ImportError:
    HAS_AGENT_TRACKER = False

try:
    from project_md_updater import ProjectMdUpdater
    HAS_PROJECT_UPDATER = True
except ImportError:
    HAS_PROJECT_UPDATER = False


# ============================================================================
# Configuration
# ============================================================================

# Check configuration from environment
TRACK_SESSIONS = os.environ.get("TRACK_SESSIONS", "true").lower() == "true"
TRACK_PIPELINE = os.environ.get("TRACK_PIPELINE", "true").lower() == "true"
AUTO_UPDATE_PROGRESS = os.environ.get("AUTO_UPDATE_PROGRESS", "false").lower() == "true"


# ============================================================================
# Log Directory Discovery
# ============================================================================

# In-process cache for session date
_SESSION_DATE_CACHE: dict = {}


def _find_log_dir() -> Path:
    """Find the .claude/logs/activity directory.

    Walks up from cwd to find an existing .claude directory, then uses
    its logs/activity subdirectory. Falls back to cwd/.claude/logs/activity.

    Returns:
        Path to the activity log directory.
    """
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        claude_dir = parent / ".claude"
        if claude_dir.exists():
            return claude_dir / "logs" / "activity"

    # Fallback to cwd
    return cwd / ".claude" / "logs" / "activity"


def _get_session_date(session_id: str) -> str:
    """Get the pinned date for a session, preventing cross-midnight mislabeling.

    Each session gets a date pinned on first activity. If the session spans
    midnight, all entries still use the original date so they land in the
    same log file.

    Args:
        session_id: The Claude session identifier.

    Returns:
        Date string in YYYY-MM-DD format.
    """
    # Check in-process cache first
    if session_id in _SESSION_DATE_CACHE:
        return _SESSION_DATE_CACHE[session_id]

    # Check for session date file
    log_dir = _find_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_session_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", session_id)
    date_file = log_dir / f".session_date_{safe_session_id}"

    try:
        if date_file.exists():
            stored_date = date_file.read_text().strip()
            # Validate freshness: if file is older than 24 hours, start fresh
            file_age_seconds = time.time() - date_file.stat().st_mtime
            if file_age_seconds < 86400 and stored_date:
                _SESSION_DATE_CACHE[session_id] = stored_date
                return stored_date
    except Exception:
        pass

    # Fall back to current date and persist it
    date_str = datetime.now().strftime("%Y-%m-%d")
    try:
        date_file.write_text(date_str)
    except Exception:
        pass
    _SESSION_DATE_CACHE[session_id] = date_str
    return date_str


# ============================================================================
# Stdin Parsing
# ============================================================================

def _parse_stdin() -> Dict:
    """Read and parse JSON from stdin (SubagentStop hook input).

    Returns:
        Parsed dict from stdin, or empty dict if stdin is empty/unparseable.
    """
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return {}


def _validate_transcript_path(path_str: str) -> str:
    """Validate agent_transcript_path is within ~/.claude.

    Args:
        path_str: Raw transcript path string.

    Returns:
        Validated path string, or empty string if invalid/unsafe.
    """
    if not path_str:
        return ""

    try:
        resolved = Path(path_str).resolve()
        claude_home = (Path.home() / ".claude").resolve()
        if resolved.is_relative_to(claude_home):
            return str(resolved)
        return ""
    except Exception:
        return ""


def _compute_duration_ms() -> int:
    """Compute duration_ms by diffing against agent_tracker started_at.

    Returns:
        Duration in milliseconds, or 0 if not available.
    """
    if not HAS_AGENT_TRACKER:
        return 0

    try:
        tracker = AgentTracker()
        session_data = tracker.get_current_session()
        if session_data and "started_at" in session_data:
            started_at_str = session_data["started_at"]
            # Parse ISO format timestamp
            started_at = datetime.fromisoformat(started_at_str)
            now = datetime.now(timezone.utc)
            # Handle naive datetime
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            delta = now - started_at
            return max(0, int(delta.total_seconds() * 1000))
    except Exception:
        pass

    return 0


def _determine_success(output: str) -> bool:
    """Determine success from last_assistant_message content.

    Uses contextual pattern matching to distinguish actual failures from
    benign mentions of error-related words (e.g. "error handling", "no error").

    Args:
        output: The last assistant message text.

    Returns:
        True if no actual failure indicators found in output.
    """
    if not output:
        return True

    # Benign contexts that should NOT be treated as failures
    benign_patterns = [
        r"\berror[\s-]?handling\b",
        r"\bno\s+errors?\b",
        r"\berror[\s-]?free\b",
        r"\bfixed\s+(?:the\s+)?error\b",
        r"\bimproved?\s+error\b",
        r"\berror\s+message\b",
        r"\bwithout\s+errors?\b",
    ]

    # Actual failure patterns that indicate a real problem
    failure_line_prefixes = re.compile(
        r"^(Error|ERROR|Fatal|FATAL|Exception)\s*:"
        r"|^Traceback\s*\(",  # Handles "Traceback (most recent call last):"
        re.MULTILINE,
    )
    failure_phrases = re.compile(
        r"\b(failed\s+to|could\s+not|unable\s+to|crashed|unhandled\s+exception)\b",
        re.IGNORECASE,
    )

    # Build a version of the output with benign matches removed so that
    # benign mentions don't trigger the failure checks below
    scrubbed = output
    for pattern in benign_patterns:
        scrubbed = re.sub(pattern, "", scrubbed, flags=re.IGNORECASE)

    # Check for actual failures in the scrubbed text
    if failure_line_prefixes.search(scrubbed):
        return False
    if failure_phrases.search(scrubbed):
        return False

    return True


# ============================================================================
# Session Logging (Basic)
# ============================================================================

class SessionTracker:
    """Basic session logging to docs/sessions/."""

    def __init__(self):
        """Initialize session tracker."""
        self.session_dir = Path("docs/sessions")
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Find or create session file for today
        today = datetime.now().strftime("%Y%m%d")
        session_files = list(self.session_dir.glob(f"{today}-*.md"))

        if session_files:
            # Use most recent session file from today
            self.session_file = sorted(session_files)[-1]
        else:
            # Create new session file
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.session_file = self.session_dir / f"{timestamp}-session.md"

            # Initialize with header
            self.session_file.write_text(
                f"# Session {timestamp}\n\n"
                f"**Started**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"---\n\n"
            )

    def log(self, agent_name: str, message: str) -> None:
        """
        Log agent action to session file.

        Args:
            agent_name: Name of agent
            message: Message to log
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"**{timestamp} - {agent_name}**: {message}\n\n"

        # Append to session file
        with open(self.session_file, "a") as f:
            f.write(entry)


def track_basic_session(agent_name: str, message: str) -> bool:
    """
    Track agent completion in basic session log.

    Args:
        agent_name: Name of agent
        message: Completion message

    Returns:
        True if logged successfully, False otherwise
    """
    if not TRACK_SESSIONS:
        return False

    try:
        tracker = SessionTracker()
        tracker.log(agent_name, message)
        return True
    except Exception:
        return False


# ============================================================================
# Pipeline Tracking (Structured)
# ============================================================================

def extract_tools_from_output(output: str) -> Optional[List[str]]:
    """
    Best-effort extraction of tools used from agent output.

    Args:
        output: Agent output text

    Returns:
        List of tool names or None if no tools detected
    """
    tools = []

    # Common tool mentions in output
    if "Read tool" in output or "reading file" in output.lower():
        tools.append("Read")
    if "Write tool" in output or "writing file" in output.lower():
        tools.append("Write")
    if "Edit tool" in output or "editing file" in output.lower():
        tools.append("Edit")
    if "Bash tool" in output or "running command" in output.lower():
        tools.append("Bash")
    if "Grep tool" in output or "searching" in output.lower():
        tools.append("Grep")
    if "WebSearch" in output or "web search" in output.lower():
        tools.append("WebSearch")
    if "WebFetch" in output or "fetching URL" in output.lower():
        tools.append("WebFetch")
    if "Task tool" in output or "invoking agent" in output.lower():
        tools.append("Task")

    return tools if tools else None


def track_pipeline_completion(agent_name: str, agent_output: str, agent_status: str) -> bool:
    """
    Track agent completion in structured pipeline.

    Args:
        agent_name: Name of agent
        agent_output: Agent output text
        agent_status: "success" or "error"

    Returns:
        True if tracked successfully, False otherwise
    """
    if not TRACK_PIPELINE or not HAS_AGENT_TRACKER:
        return False

    try:
        tracker = AgentTracker()

        # Read feature_ref from environment (batch mode)
        feature_ref = os.environ.get("PIPELINE_FEATURE_REF", "")

        if agent_status == "success":
            # Extract tools used
            tools = extract_tools_from_output(agent_output)

            # Create summary (first 100 chars)
            summary = agent_output[:100].replace("\n", " ") if agent_output else "Completed"
            if feature_ref:
                summary = f"[{feature_ref}] {summary}"

            # Auto-track agent first (idempotent)
            tracker.auto_track_from_environment(message=summary)

            # Complete the agent
            tracker.complete_agent(agent_name, summary, tools)
        else:
            # Extract error message
            error_msg = agent_output[:100].replace("\n", " ") if agent_output else "Failed"
            if feature_ref:
                error_msg = f"[{feature_ref}] {error_msg}"

            # Auto-track even for failures
            tracker.auto_track_from_environment(message=error_msg)

            # Fail the agent
            tracker.fail_agent(agent_name, error_msg)

        return True
    except Exception:
        return False


# ============================================================================
# PROJECT.md Progress Updates
# ============================================================================

def should_trigger_progress_update(agent_name: str) -> bool:
    """
    Check if PROJECT.md progress update should trigger.

    Only triggers for doc-master (last agent in pipeline).

    Args:
        agent_name: Name of agent that completed

    Returns:
        True if should trigger, False otherwise
    """
    return agent_name == "doc-master"


def check_pipeline_complete() -> bool:
    """
    Check if all 7 agents in pipeline completed.

    Returns:
        True if pipeline complete, False otherwise
    """
    if not HAS_AGENT_TRACKER:
        return False

    try:
        # Check latest session file
        session_dir = Path("docs/sessions")
        session_files = list(session_dir.glob("*-pipeline.json"))

        if not session_files:
            return False

        # Read latest session
        latest_session = sorted(session_files)[-1]
        session_data = json.loads(latest_session.read_text())

        # Check if all expected agents completed
        # Issue #147: Consolidated to only active agents in /implement pipeline
        expected_agents = [
            "researcher-local",
            "planner",
            "test-master",
            "implementer",
            "reviewer",
            "security-auditor",
            "doc-master"
        ]

        completed_agents = {
            entry["agent"] for entry in session_data.get("agents", [])
            if entry.get("status") == "completed"
        }

        return set(expected_agents).issubset(completed_agents)
    except Exception:
        return False


def update_project_progress() -> bool:
    """
    Update PROJECT.md with goal progress.

    Returns:
        True if updated successfully, False otherwise
    """
    if not AUTO_UPDATE_PROGRESS or not HAS_PROJECT_UPDATER:
        return False

    try:
        # Note: Progress tracking feature deprioritized (Issue #147: Agent consolidation)
        # Would update PROJECT.md via ProjectMdUpdater if implemented.
        return False
    except Exception:
        return False


# ============================================================================
# JSONL Activity Logging
# ============================================================================

def _write_jsonl_entry(
    *,
    subagent_type: str,
    duration_ms: int,
    result_word_count: int,
    agent_transcript_path: str,
    session_id: str,
    success: bool,
) -> bool:
    """Write a structured JSONL entry for the SubagentStop event.

    Args:
        subagent_type: The agent type that completed.
        duration_ms: Computed duration in milliseconds.
        result_word_count: Word count of last_assistant_message.
        agent_transcript_path: Validated transcript path or empty string.
        session_id: Session identifier.
        success: Whether the agent completed successfully.

    Returns:
        True if written successfully, False otherwise.
    """
    try:
        log_dir = _find_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)

        date_str = _get_session_date(session_id)
        log_file = log_dir / f"{date_str}.jsonl"

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hook": "SubagentStop",
            "subagent_type": subagent_type,
            "duration_ms": duration_ms,
            "result_word_count": result_word_count,
            "agent_transcript_path": agent_transcript_path,
            "session_id": session_id,
            "success": success,
        }

        # Include feature_ref from environment when in batch mode
        feature_ref = os.environ.get("PIPELINE_FEATURE_REF", "")
        if feature_ref:
            entry["feature_ref"] = feature_ref

        with open(log_file, "a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")

        return True
    except Exception:
        return False


# ============================================================================
# Main Hook Entry Point
# ============================================================================

def main() -> int:
    """
    Main hook entry point.

    Reads agent info from stdin JSON (SubagentStop hook input), with
    fallback to environment variables for backward compatibility.

    Returns:
        Always 0 (non-blocking hook)
    """
    try:
        # Parse stdin JSON (SubagentStop provides input via stdin)
        hook_input = _parse_stdin()

        # Extract fields from stdin, fall back to env vars
        if hook_input:
            agent_name = hook_input.get("agent_type", "unknown")
            agent_output = hook_input.get("last_assistant_message", "")
            session_id = hook_input.get("session_id", os.environ.get("CLAUDE_SESSION_ID", "unknown"))
            agent_transcript_path_raw = hook_input.get("agent_transcript_path", "")
        else:
            # Backward compatibility: fall back to environment variables
            agent_name = os.environ.get("CLAUDE_AGENT_NAME", "unknown")
            agent_output = os.environ.get("CLAUDE_AGENT_OUTPUT", "")
            session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")
            agent_transcript_path_raw = ""

        # Determine status with correct priority (Issue #541):
        # 1. CLAUDE_AGENT_STATUS env var (structural signal) — authoritative
        # 2. _determine_success() text scan — fallback only when env var absent
        # Previously, the text scan always ran and could override a "success" env var
        # when the output happened to contain benign failure-pattern words.
        env_status = os.environ.get("CLAUDE_AGENT_STATUS")
        if env_status:
            agent_status = env_status
        elif agent_output and not _determine_success(agent_output):
            agent_status = "error"
        else:
            agent_status = "success"

        # Validate transcript path
        agent_transcript_path = _validate_transcript_path(agent_transcript_path_raw)

        # Compute duration
        duration_ms = _compute_duration_ms()

        # Compute word count
        result_word_count = len(agent_output.split()) if agent_output else 0

        # Determine success
        success = _determine_success(agent_output)

        # Create summary message
        summary = agent_output[:100].replace("\n", " ") if agent_output else "Completed"

        # Dispatch tracking (all are non-blocking)
        # Basic session logging
        track_basic_session(agent_name, summary)

        # Structured pipeline tracking
        track_pipeline_completion(agent_name, agent_output, agent_status)

        # JSONL activity logging for CI agent visibility
        _write_jsonl_entry(
            subagent_type=agent_name,
            duration_ms=duration_ms,
            result_word_count=result_word_count,
            agent_transcript_path=agent_transcript_path,
            session_id=session_id,
            success=success,
        )

        # PROJECT.md progress updates (only for doc-master)
        if should_trigger_progress_update(agent_name) and check_pipeline_complete():
            update_project_progress()

    except Exception:
        # Graceful degradation - never block workflow
        pass

    # Always succeed (non-blocking hook)
    return 0


if __name__ == "__main__":
    sys.exit(main())
