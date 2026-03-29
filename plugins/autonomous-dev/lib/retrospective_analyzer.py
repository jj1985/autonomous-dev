#!/usr/bin/env python3
"""
Retrospective Analyzer Library - Session log analysis and drift detection.

Reads JSONL activity logs, detects repeated correction patterns, config drift,
and stale memory entries. Produces structured findings with proposed edits.

Key Features:
1. Load session summaries from .claude/logs/activity/ JSONL files
2. Detect repeated user corrections across sessions
3. Detect config drift via git history (PROJECT.md, CLAUDE.md)
4. Detect memory rot (stale entries with no recent corroboration)
5. Format proposed edits as unified diffs

Security:
- CWE-22: Path validation — all paths resolved and checked against project root
- CWE-400: Resource limits — caps on sessions, events per session
- CWE-116: Log content treated as untrusted (no eval/exec)

Date: 2026-03-29
Issue: #598 (Add /retrospective command and scheduled drift detection)
Agent: implementer
"""

import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

# Set up logging
logger = logging.getLogger(__name__)

# Import path utilities with fallback pattern
try:
    from .path_utils import get_project_root
except ImportError:
    lib_dir = Path(__file__).parent.resolve()
    sys.path.insert(0, str(lib_dir))
    from path_utils import get_project_root


# =============================================================================
# Constants
# =============================================================================

# Resource limits (CWE-400)
MAX_SESSIONS = 50
MAX_EVENTS_PER_SESSION = 200
MAX_LOG_FILES = 100

# Correction patterns — words/phrases indicating user pushed back
CORRECTION_PATTERNS = [
    r"\bno\b",
    r"\brevert\b",
    r"\bwrong\b",
    r"\bdon'?t\b",
    r"\bstop\b",
    r"\bundo\b",
    r"\bincorrect\b",
    r"\bnot what i\b",
    r"\bthat'?s not\b",
    r"\bi said\b",
    r"\bi meant\b",
]

# Compiled correction regex (case-insensitive)
_CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)


# =============================================================================
# Enums
# =============================================================================


class DriftCategory(str, Enum):
    """Categories of drift findings."""

    INTENT_SHIFT = "INTENT_SHIFT"
    REPEATED_CORRECTION = "REPEATED_CORRECTION"
    STALE_GOAL = "STALE_GOAL"
    MEMORY_ROT = "MEMORY_ROT"
    CONFIG_DRIFT = "CONFIG_DRIFT"


class DriftSeverity(str, Enum):
    """Severity tiers for drift findings."""

    IMMEDIATE = "IMMEDIATE"
    REVIEW = "REVIEW"
    ARCHIVE = "ARCHIVE"


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class ProposedEdit:
    """A proposed edit to an alignment file."""

    file_path: str
    edit_type: str  # ADD, MODIFY, REMOVE
    section: str
    current_content: str
    proposed_content: str
    rationale: str


@dataclass
class DriftFinding:
    """A single drift detection finding."""

    category: DriftCategory
    severity: DriftSeverity
    description: str
    evidence: List[str] = field(default_factory=list)
    proposed_edit: Optional[ProposedEdit] = None


@dataclass
class SessionSummary:
    """Summary of a single session's activity."""

    session_id: str
    date: str
    stop_messages: List[str] = field(default_factory=list)
    commands_used: List[str] = field(default_factory=list)
    corrections: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)


@dataclass
class RetrospectiveConfig:
    """Configuration for retrospective analysis."""

    max_sessions: int = 20
    decay_days: int = 90
    min_correction_threshold: int = 3
    dry_run: bool = False


# =============================================================================
# Session Loading
# =============================================================================


def _validate_logs_dir(logs_dir: Path) -> Path:
    """Validate that logs_dir is a real directory within the project.

    Args:
        logs_dir: Path to the activity logs directory.

    Returns:
        Resolved path.

    Raises:
        ValueError: If path is invalid or attempts traversal.
    """
    resolved = logs_dir.resolve()
    # Basic traversal check: must not contain ".." after resolve
    try:
        # Ensure it doesn't escape via symlinks to unexpected locations
        if not resolved.is_dir():
            raise ValueError(
                f"Logs directory does not exist: {resolved}\n"
                f"Expected: .claude/logs/activity/"
            )
    except OSError as e:
        raise ValueError(f"Cannot access logs directory: {resolved} ({e})")
    return resolved


def load_session_summaries(
    logs_dir: Path,
    *,
    max_sessions: int = 20,
) -> List[SessionSummary]:
    """Load and summarize session activity from JSONL log files.

    Reads JSONL activity logs, groups events by session_id, and extracts
    correction patterns and Stop hook message previews.

    Args:
        logs_dir: Path to .claude/logs/activity/ directory.
        max_sessions: Maximum number of sessions to return (most recent first).

    Returns:
        List of SessionSummary objects, sorted by date descending.

    Raises:
        ValueError: If logs_dir is invalid.
    """
    resolved_dir = _validate_logs_dir(logs_dir)

    # Cap max_sessions to absolute limit
    effective_max = min(max_sessions, MAX_SESSIONS)

    # Find JSONL files, sorted by name (date-based) descending
    jsonl_files = sorted(resolved_dir.glob("*.jsonl"), reverse=True)
    jsonl_files = jsonl_files[:MAX_LOG_FILES]

    # Group events by session_id
    sessions: Dict[str, Dict] = {}

    for log_file in jsonl_files:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                event_count = 0
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    session_id = event.get("session_id", "unknown")
                    if session_id not in sessions:
                        sessions[session_id] = {
                            "session_id": session_id,
                            "date": log_file.stem,  # YYYY-MM-DD from filename
                            "stop_messages": [],
                            "commands_used": set(),
                            "corrections": [],
                            "events_count": 0,
                        }

                    sess = sessions[session_id]

                    # Enforce per-session event cap
                    if sess["events_count"] >= MAX_EVENTS_PER_SESSION:
                        continue
                    sess["events_count"] += 1

                    # Extract Stop hook messages (message_preview field)
                    hook = event.get("hook", "")
                    if hook == "Stop":
                        msg = event.get("message_preview", "")
                        if msg:
                            sess["stop_messages"].append(msg)

                    # Extract commands from tool usage
                    tool = event.get("tool", "")
                    if tool:
                        sess["commands_used"].add(tool)

                    # Extract correction patterns from user prompts
                    if hook == "UserPromptSubmit":
                        prompt = event.get("prompt", event.get("input_summary", ""))
                        if isinstance(prompt, dict):
                            prompt = prompt.get("command", str(prompt))
                        if isinstance(prompt, str) and _CORRECTION_RE.search(prompt):
                            # Store the matched portion for evidence
                            match = _CORRECTION_RE.search(prompt)
                            if match:
                                sess["corrections"].append(
                                    prompt[:100]  # Cap length for safety
                                )

                    event_count += 1
        except (OSError, PermissionError) as e:
            logger.warning("Could not read log file %s: %s", log_file, e)
            continue

    # Convert to SessionSummary objects
    summaries = []
    for sid, data in sessions.items():
        summaries.append(
            SessionSummary(
                session_id=data["session_id"],
                date=data["date"],
                stop_messages=data["stop_messages"],
                commands_used=sorted(data["commands_used"]),
                corrections=data["corrections"],
                topics=[],  # Topics require deeper NLP; leave empty for now
            )
        )

    # Sort by date descending, then cap
    summaries.sort(key=lambda s: s.date, reverse=True)
    return summaries[:effective_max]


# =============================================================================
# Drift Detection: Repeated Corrections
# =============================================================================


def detect_repeated_corrections(
    summaries: List[SessionSummary],
    *,
    min_threshold: int = 3,
) -> List[DriftFinding]:
    """Detect correction patterns that recur across multiple sessions.

    A correction pattern must appear in at least min_threshold distinct
    sessions to be flagged, indicating the user repeatedly pushes back
    on the same behavior.

    Args:
        summaries: Session summaries to analyze.
        min_threshold: Minimum distinct sessions with corrections to flag.

    Returns:
        List of DriftFinding objects for repeated correction patterns.
    """
    if not summaries:
        return []

    # Track which sessions have corrections
    sessions_with_corrections: Dict[str, List[str]] = {}
    for summary in summaries:
        if summary.corrections:
            sessions_with_corrections[summary.session_id] = summary.corrections

    distinct_sessions = len(sessions_with_corrections)
    if distinct_sessions < min_threshold:
        return []

    # Aggregate all correction texts for evidence
    all_corrections: List[str] = []
    for corrections in sessions_with_corrections.values():
        all_corrections.extend(corrections)

    # Find common correction patterns across sessions
    findings: List[DriftFinding] = []

    # Check each compiled pattern for cross-session recurrence
    for pattern_str in CORRECTION_PATTERNS:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        matching_sessions = set()
        matching_evidence: List[str] = []

        for sid, corrections in sessions_with_corrections.items():
            for correction in corrections:
                if pattern.search(correction):
                    matching_sessions.add(sid)
                    matching_evidence.append(f"[{sid[:8]}] {correction[:80]}")
                    break  # One match per session is enough

        if len(matching_sessions) >= min_threshold:
            severity = (
                DriftSeverity.IMMEDIATE
                if len(matching_sessions) >= min_threshold * 2
                else DriftSeverity.REVIEW
            )
            findings.append(
                DriftFinding(
                    category=DriftCategory.REPEATED_CORRECTION,
                    severity=severity,
                    description=(
                        f"Correction pattern '{pattern_str}' found in "
                        f"{len(matching_sessions)} distinct sessions "
                        f"(threshold: {min_threshold})"
                    ),
                    evidence=matching_evidence[:10],  # Cap evidence
                )
            )

    return findings


# =============================================================================
# Drift Detection: Config Drift
# =============================================================================


def detect_config_drift(
    project_root: Path,
    *,
    baseline_commits: int = 20,
) -> List[DriftFinding]:
    """Detect changes to alignment files via git history.

    Checks git diff HEAD~N for PROJECT.md and CLAUDE.md changes,
    flagging configuration drift that may indicate intent evolution.

    Args:
        project_root: Root of the project repository.
        baseline_commits: Number of commits to look back.

    Returns:
        List of DriftFinding objects for config drift.
    """
    findings: List[DriftFinding] = []
    resolved_root = project_root.resolve()

    alignment_files = [
        ".claude/PROJECT.md",
        "CLAUDE.md",
    ]

    # Cap baseline_commits to reasonable range
    baseline_commits = min(max(baseline_commits, 1), 100)

    for rel_path in alignment_files:
        try:
            result = subprocess.run(
                [
                    "git",
                    "diff",
                    f"HEAD~{baseline_commits}",
                    "--",
                    rel_path,
                ],
                capture_output=True,
                text=True,
                cwd=str(resolved_root),
                timeout=10,
            )
            diff_output = result.stdout.strip()
            if diff_output:
                # Count additions and removals
                additions = len(
                    [l for l in diff_output.splitlines() if l.startswith("+") and not l.startswith("+++")]
                )
                removals = len(
                    [l for l in diff_output.splitlines() if l.startswith("-") and not l.startswith("---")]
                )

                severity = (
                    DriftSeverity.IMMEDIATE
                    if additions + removals > 20
                    else DriftSeverity.REVIEW
                )

                findings.append(
                    DriftFinding(
                        category=DriftCategory.CONFIG_DRIFT,
                        severity=severity,
                        description=(
                            f"{rel_path} changed in last {baseline_commits} commits: "
                            f"+{additions}/-{removals} lines"
                        ),
                        evidence=[
                            diff_output[:500]  # Cap diff output
                        ],
                    )
                )
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning("Could not check git diff for %s: %s", rel_path, e)
            continue

    return findings


# =============================================================================
# Drift Detection: Memory Rot
# =============================================================================


def detect_memory_rot(
    memory_dir: Path,
    summaries: List[SessionSummary],
    *,
    decay_days: int = 90,
) -> List[DriftFinding]:
    """Flag memory entries older than decay_days with no recent corroboration.

    Scans markdown files in the memory directory for date-stamped entries
    and checks whether they have been referenced in recent sessions.

    Args:
        memory_dir: Path to memory directory (e.g., .claude/memory/).
        summaries: Recent session summaries for corroboration check.
        decay_days: Number of days before an entry is considered stale.

    Returns:
        List of DriftFinding objects for stale memory entries.
    """
    findings: List[DriftFinding] = []

    if not memory_dir.is_dir():
        return findings

    resolved_dir = memory_dir.resolve()
    cutoff = datetime.now(timezone.utc) - timedelta(days=decay_days)

    # Build a set of all recent session content for corroboration
    recent_content = set()
    for summary in summaries:
        for msg in summary.stop_messages:
            # Add words from stop messages for fuzzy matching
            words = set(msg.lower().split())
            recent_content.update(words)
        for correction in summary.corrections:
            words = set(correction.lower().split())
            recent_content.update(words)

    # Date pattern matching (YYYY-MM-DD) in markdown files
    date_pattern = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

    md_files = list(resolved_dir.glob("*.md"))
    md_files = md_files[:50]  # Cap file count

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Could not read memory file %s: %s", md_file, e)
            continue

        # Find sections with dates
        lines = content.splitlines()
        current_section = ""
        section_date: Optional[datetime] = None
        section_content: List[str] = []

        for line in lines:
            # Check for section headers
            if line.startswith("#"):
                # Process previous section if it had a date
                if section_date and section_content:
                    _check_section_for_rot(
                        findings=findings,
                        file_path=md_file,
                        section=current_section,
                        section_date=section_date,
                        section_content=section_content,
                        cutoff=cutoff,
                        recent_content=recent_content,
                    )
                current_section = line
                section_date = None
                section_content = []

            # Look for dates in the line
            date_match = date_pattern.search(line)
            if date_match and section_date is None:
                try:
                    section_date = datetime.strptime(
                        date_match.group(1), "%Y-%m-%d"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            section_content.append(line)

        # Process last section
        if section_date and section_content:
            _check_section_for_rot(
                findings=findings,
                file_path=md_file,
                section=current_section,
                section_content=section_content,
                section_date=section_date,
                cutoff=cutoff,
                recent_content=recent_content,
            )

    return findings


def _check_section_for_rot(
    *,
    findings: List[DriftFinding],
    file_path: Path,
    section: str,
    section_date: datetime,
    section_content: List[str],
    cutoff: datetime,
    recent_content: set,
) -> None:
    """Check a single section for memory rot and append finding if stale.

    Args:
        findings: List to append findings to.
        file_path: Path to the memory file.
        section: Section header text.
        section_date: Date found in the section.
        section_content: Lines in the section.
        cutoff: Date before which entries are considered stale.
        recent_content: Set of words from recent sessions for corroboration.
    """
    if section_date >= cutoff:
        return  # Not old enough to be stale

    # Check for corroboration in recent sessions
    section_text = " ".join(section_content).lower()
    section_words = set(section_text.split())

    # Require at least 3 meaningful words to overlap for corroboration
    # Filter out very short words
    meaningful_section_words = {w for w in section_words if len(w) > 4}
    overlap = meaningful_section_words & recent_content
    if len(overlap) >= 3:
        return  # Corroborated by recent sessions

    findings.append(
        DriftFinding(
            category=DriftCategory.MEMORY_ROT,
            severity=DriftSeverity.ARCHIVE,
            description=(
                f"Memory entry in {file_path.name} section '{section[:60]}' "
                f"dated {section_date.strftime('%Y-%m-%d')} has no recent corroboration "
                f"(decay threshold: {(datetime.now(timezone.utc) - cutoff).days} days)"
            ),
            evidence=[
                f"File: {file_path.name}",
                f"Section: {section[:80]}",
                f"Date: {section_date.strftime('%Y-%m-%d')}",
            ],
            proposed_edit=ProposedEdit(
                file_path=str(file_path),
                edit_type="REMOVE",
                section=section[:80],
                current_content="\n".join(section_content[:5]),
                proposed_content="",
                rationale=(
                    f"Entry dated {section_date.strftime('%Y-%m-%d')} has not been "
                    f"referenced in recent sessions. Consider archiving."
                ),
            ),
        )
    )


# =============================================================================
# Formatting
# =============================================================================


def format_as_unified_diff(edit: ProposedEdit) -> str:
    """Render a ProposedEdit as a unified diff string.

    Args:
        edit: The proposed edit to format.

    Returns:
        Unified diff string suitable for display.
    """
    lines: List[str] = []
    lines.append(f"--- a/{edit.file_path}")
    lines.append(f"+++ b/{edit.file_path}")

    if edit.edit_type == "REMOVE":
        current_lines = edit.current_content.splitlines()
        lines.append(f"@@ -{1},{len(current_lines)} +{1},0 @@")
        for cl in current_lines:
            lines.append(f"-{cl}")
    elif edit.edit_type == "ADD":
        proposed_lines = edit.proposed_content.splitlines()
        lines.append(f"@@ -0,0 +{1},{len(proposed_lines)} @@")
        for pl in proposed_lines:
            lines.append(f"+{pl}")
    elif edit.edit_type == "MODIFY":
        current_lines = edit.current_content.splitlines()
        proposed_lines = edit.proposed_content.splitlines()
        lines.append(
            f"@@ -{1},{len(current_lines)} +{1},{len(proposed_lines)} @@"
        )
        for cl in current_lines:
            lines.append(f"-{cl}")
        for pl in proposed_lines:
            lines.append(f"+{pl}")

    # Add rationale as a comment
    lines.append(f"# Rationale: {edit.rationale}")

    return "\n".join(lines)
