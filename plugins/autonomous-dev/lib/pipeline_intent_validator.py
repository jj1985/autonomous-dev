#!/usr/bin/env python3
"""
Pipeline Intent Validator - Issue #367

Parses JSONL session logs and validates that the /implement pipeline
coordinator followed step contracts: sequential ordering, hard gate
enforcement, context passing, and correct parallelization.

Used by the continuous-improvement-analyst agent (quality check #8).

Usage:
    from pipeline_intent_validator import validate_pipeline_intent
    findings = validate_pipeline_intent(Path("logs/2026-02-28.jsonl"))
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# Tool names for agent invocations — Claude Code renamed "Task" to "Agent"
# but old logs still use "Task". Accept both for backward compatibility.
AGENT_TOOL_NAMES = {"Task", "Agent"}


@dataclass
class PipelineEvent:
    """A pipeline-relevant event from session logs."""

    timestamp: str
    tool: str
    agent: str
    subagent_type: str
    pipeline_action: str
    prompt_word_count: int = 0
    result_word_count: int = 0
    duration_ms: int = 0
    success: bool = True
    agent_transcript_path: str = ""
    batch_issue_number: int = 0
    session_id: str = ""


@dataclass
class Finding:
    """A pipeline intent violation finding."""

    finding_type: str  # e.g. "step_ordering", "hard_gate_ordering", "context_dropping"
    severity: str  # CRITICAL, WARNING, INFO
    pattern_id: str  # e.g. "implementer_before_planner"
    description: str
    evidence: list = field(default_factory=list)
    recommended_action: Optional[str] = None


# Canonical step ordering: agent type → step index
# Agents with the same index are allowed to run in parallel
STEP_ORDER = {
    "researcher-local": 2,
    "researcher": 2,
    "planner": 3,
    "test-master": 4,
    "implementer": 5,
    "reviewer": 6.0,
    "security-auditor": 6.1,
    "doc-master": 6.0,
}

# Agent pairs that MUST be sequential (first must complete before second starts)
SEQUENTIAL_REQUIRED = [
    ("planner", "test-master"),
    ("planner", "implementer"),
    ("test-master", "implementer"),
    ("implementer", "reviewer"),
    ("implementer", "security-auditor"),
    ("implementer", "doc-master"),
    ("reviewer", "security-auditor"),
]

# Agent pairs that SHOULD be parallel (efficiency check)
PARALLEL_EXPECTED = [
    ("researcher-local", "researcher"),
    # reviewer, security-auditor, doc-master are also parallel but checked differently
]

# STEP 6 agents that must wait for test gate
STEP6_AGENTS = {"reviewer", "security-auditor", "doc-master"}

# Minimum agents to consider this a full pipeline run
MIN_FULL_PIPELINE_AGENTS = 4

# Timestamp window for considering agents "parallel" (seconds)
TIMESTAMP_WINDOW_SECONDS = 5

# Threshold for parallel serialization detection (seconds)
PARALLEL_SERIALIZED_THRESHOLD = 30

# Agents whose prompts are security-critical and must not be compressed
COMPRESSION_CRITICAL_AGENTS = {"security-auditor", "reviewer"}

# Maximum allowed prompt shrinkage ratio from baseline (issue 1) to later issues
# e.g. 0.25 means if issue 3's prompt is < 25% of issue 1's prompt, flag it
MAX_PROMPT_SHRINKAGE_RATIO = 0.25

# Minimum prompt word count for security-critical agents
MIN_CRITICAL_AGENT_PROMPT_WORDS = 80

# Minimum word count for doc-master output to be considered a valid verdict
MIN_DOC_VERDICT_WORDS = 30

# Known valid agent types for file path construction (security whitelist)
VALID_AGENT_TYPES = set(STEP_ORDER.keys())


def get_minimum_prompt_content(agent_type: str, agents_dir: Path) -> Optional[str]:
    """Read minimum prompt content from an agent's .md file on disk.

    Validates agent_type against VALID_AGENT_TYPES whitelist before
    constructing file paths. Returns the first ~200 words of the file
    as a minimum prompt baseline.

    Args:
        agent_type: Agent type string (must be in VALID_AGENT_TYPES).
        agents_dir: Path to the agents directory.

    Returns:
        First ~200 words of the agent's .md file, or None if invalid/missing.
    """
    if agent_type not in VALID_AGENT_TYPES:
        return None

    try:
        agent_file = agents_dir / f"{agent_type}.md"
        if not agent_file.exists():
            return None
        content = agent_file.read_text().strip()
        if not content:
            return None
        words = content.split()
        return " ".join(words[:200])
    except (OSError, IOError):
        return None


def parse_session_logs(
    log_path: Path,
    *,
    session_id: Optional[str] = None,
) -> List[PipelineEvent]:
    """Parse JSONL session log into pipeline-relevant events.

    Args:
        log_path: Path to JSONL log file.
        session_id: Optional session ID filter.

    Returns:
        List of PipelineEvent sorted by timestamp.
    """
    events: List[PipelineEvent] = []

    if not log_path.exists():
        return events

    text = log_path.read_text().strip()
    if not text:
        return events

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Filter by session
        if session_id and entry.get("session_id") != session_id:
            continue

        tool = entry.get("tool", "")
        raw_input_summary = entry.get("input_summary", {})
        output_summary = entry.get("output_summary", {})

        # Guard against non-dict output_summary (e.g. legacy string values)
        if not isinstance(output_summary, dict):
            output_summary = {}

        # Handle non-dict input_summary: try to extract subagent_type from string
        # representation (e.g. "subagent_type: planner") so legacy / test-fixture
        # entries still produce parseable events. (Issue #587)
        if isinstance(raw_input_summary, dict):
            input_summary = raw_input_summary
        else:
            input_summary = {}
            if isinstance(raw_input_summary, str) and "subagent_type:" in raw_input_summary:
                # Parse simple "key: value" format from string input_summary
                for part in raw_input_summary.split(","):
                    part = part.strip()
                    if ":" in part:
                        k, _, v = part.partition(":")
                        input_summary[k.strip()] = v.strip()
                # If we found a subagent_type, synthesize pipeline_action
                if "subagent_type" in input_summary and "pipeline_action" not in input_summary:
                    input_summary["pipeline_action"] = "agent_invocation"

        pipeline_action = input_summary.get("pipeline_action", "")

        # Extract batch_issue_number from input_summary (default 0 = non-batch)
        batch_issue_number = input_summary.get("batch_issue_number", 0)
        if not isinstance(batch_issue_number, int):
            batch_issue_number = 0

        # Include Task (agent invocations) and Bash test_run events
        if tool in AGENT_TOOL_NAMES and pipeline_action == "agent_invocation":
            events.append(PipelineEvent(
                timestamp=entry.get("timestamp", ""),
                tool=tool,
                agent=entry.get("agent", "main"),
                subagent_type=input_summary.get("subagent_type", ""),
                pipeline_action=pipeline_action,
                prompt_word_count=input_summary.get("prompt_word_count", 0),
                result_word_count=output_summary.get("result_word_count", 0),
                duration_ms=entry.get("duration_ms", 0),
                success=output_summary.get("success", True),
                batch_issue_number=batch_issue_number,
                session_id=entry.get("session_id", ""),
            ))
        elif tool == "Bash" and pipeline_action == "test_run":
            events.append(PipelineEvent(
                timestamp=entry.get("timestamp", ""),
                tool=tool,
                agent=entry.get("agent", "main"),
                subagent_type="",
                pipeline_action="test_run",
                duration_ms=entry.get("duration_ms", 0),
                success=output_summary.get("success", True),
                session_id=entry.get("session_id", ""),
            ))
        elif entry.get("hook") == "SubagentStop":
            events.append(PipelineEvent(
                timestamp=entry.get("timestamp", ""),
                tool="Agent",
                agent=entry.get("agent", "main"),
                subagent_type=entry.get("subagent_type", ""),
                pipeline_action="agent_completion",
                result_word_count=entry.get("result_word_count", 0),
                duration_ms=entry.get("duration_ms", 0),
                success=entry.get("success", True),
                agent_transcript_path=entry.get("agent_transcript_path", ""),
                session_id=entry.get("session_id", ""),
            ))

    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp)
    return events


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime."""
    try:
        # Handle various ISO formats
        ts = ts.replace("+00:00", "+0000").replace("Z", "+0000")
        if "+" in ts[10:]:
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")
        return datetime.fromisoformat(ts)
    except (ValueError, IndexError):
        return None


def _seconds_between(ts1: str, ts2: str) -> Optional[float]:
    """Get seconds between two timestamps."""
    dt1 = _parse_timestamp(ts1)
    dt2 = _parse_timestamp(ts2)
    if dt1 is None or dt2 is None:
        return None
    return abs((dt2 - dt1).total_seconds())


def validate_step_ordering(events: List[PipelineEvent]) -> List[Finding]:
    """Validate that pipeline steps executed in correct order.

    Args:
        events: List of PipelineEvent sorted by timestamp.

    Returns:
        List of findings for ordering violations.
    """
    findings: List[Finding] = []

    # Filter to agent invocations with known step assignments
    agent_events = [
        e for e in events
        if e.tool in AGENT_TOOL_NAMES and e.subagent_type in STEP_ORDER
    ]

    # Need at least 2 agents to check ordering
    if len(agent_events) < 2:
        return findings

    # Check ordering: for each sequential pair, verify first completed before second
    # NOTE: test-master absence is intentionally NOT checked here. In acceptance-first mode
    # (the default), test-master is never invoked — it only runs in --tdd-first mode.
    # The pipeline coordinator (implement.md STEP 7) is responsible for mode-specific agent
    # inclusion. Post-hoc log validation must not second-guess mode selection. (#518)
    for first_type, second_type in SEQUENTIAL_REQUIRED:
        first_events = [e for e in agent_events if e.subagent_type == first_type]
        second_events = [e for e in agent_events if e.subagent_type == second_type]

        if not first_events or not second_events:
            continue

        # Use earliest timestamp for each
        first_ts = first_events[0].timestamp
        second_ts = second_events[0].timestamp

        if second_ts < first_ts:
            findings.append(Finding(
                finding_type="step_ordering",
                severity="CRITICAL",
                pattern_id="step_ordering",
                description=f"{second_type} ran before {first_type} (expected {first_type} first)",
                evidence=[
                    f"{first_type} at {first_ts}",
                    f"{second_type} at {second_ts}",
                ],
            ))

    return findings


def detect_hard_gate_ordering(events: List[PipelineEvent]) -> List[Finding]:
    """Detect STEP 6 agents running before STEP 5 test gate passes.

    Args:
        events: List of PipelineEvent sorted by timestamp.

    Returns:
        List of findings for hard gate ordering violations.
    """
    findings: List[Finding] = []

    # Find STEP 6 agent events
    step6_events = [e for e in events if e.subagent_type in STEP6_AGENTS]
    if not step6_events:
        return findings

    # Find successful test_run events
    test_runs = [e for e in events if e.pipeline_action == "test_run"]
    successful_test_runs = [e for e in test_runs if e.success]

    # No pytest at all but STEP 6 ran
    if not test_runs and step6_events:
        findings.append(Finding(
            finding_type="hard_gate_ordering",
            severity="CRITICAL",
            pattern_id="hard_gate_ordering_bypass",
            description="STEP 6 validation agents ran without any pytest execution (STEP 5 test gate skipped)",
            evidence=[f"STEP 6 agents: {[e.subagent_type for e in step6_events]}"],
        ))
        return findings

    # Pytest ran but failed, and STEP 6 still ran
    if test_runs and not successful_test_runs and step6_events:
        findings.append(Finding(
            finding_type="hard_gate_ordering",
            severity="CRITICAL",
            pattern_id="hard_gate_ordering_bypass",
            description="STEP 6 validation agents ran after pytest failed (STEP 5 test gate not passed)",
            evidence=[
                f"test_run at {test_runs[0].timestamp} success=False",
                f"First STEP 6 agent: {step6_events[0].subagent_type} at {step6_events[0].timestamp}",
            ],
        ))
        return findings

    # Check if any STEP 6 agent ran before the first successful pytest
    if successful_test_runs:
        first_pass_ts = successful_test_runs[0].timestamp
        early_step6 = [e for e in step6_events if e.timestamp < first_pass_ts]
        if early_step6:
            findings.append(Finding(
                finding_type="hard_gate_ordering",
                severity="CRITICAL",
                pattern_id="hard_gate_ordering_bypass",
                description="STEP 6 agents launched before STEP 5 pytest passed",
                evidence=[
                    f"First passing test_run: {first_pass_ts}",
                    f"Early STEP 6 agents: {[(e.subagent_type, e.timestamp) for e in early_step6]}",
                ],
            ))

    return findings


def detect_context_dropping(
    events: List[PipelineEvent],
    *,
    threshold: float = 0.2,
) -> List[Finding]:
    """Detect when agent prompts are much smaller than prior agent results.

    Args:
        events: List of PipelineEvent sorted by timestamp.
        threshold: Minimum prompt/result ratio (below = context dropping).

    Returns:
        List of findings for context dropping.
    """
    findings: List[Finding] = []

    # Filter to agent invocations only
    agent_events = [e for e in events if e.tool in AGENT_TOOL_NAMES and e.subagent_type]

    for i in range(1, len(agent_events)):
        prev = agent_events[i - 1]
        curr = agent_events[i]

        # Skip if word counts are missing/zero
        if prev.result_word_count == 0 or curr.prompt_word_count == 0:
            continue

        ratio = curr.prompt_word_count / prev.result_word_count
        if ratio < threshold:
            findings.append(Finding(
                finding_type="context_dropping",
                severity="WARNING",
                pattern_id="context_dropping",
                description=(
                    f"Agent {curr.subagent_type} prompt ({curr.prompt_word_count} words) is "
                    f"{ratio:.1%} of {prev.subagent_type} result ({prev.result_word_count} words) "
                    f"— possible context summarization (threshold: {threshold:.0%})"
                ),
                evidence=[
                    f"{prev.subagent_type} result_word_count: {prev.result_word_count}",
                    f"{curr.subagent_type} prompt_word_count: {curr.prompt_word_count}",
                    f"Ratio: {ratio:.3f} (threshold: {threshold})",
                ],
            ))

    return findings


def detect_parallelization_violations(events: List[PipelineEvent]) -> List[Finding]:
    """Detect incorrect parallelization of pipeline steps.

    Args:
        events: List of PipelineEvent sorted by timestamp.

    Returns:
        List of findings for parallelization violations.
    """
    findings: List[Finding] = []

    agent_events = [e for e in events if e.tool in AGENT_TOOL_NAMES and e.subagent_type]

    # Build lookup: agent_type → earliest timestamp
    agent_timestamps: dict[str, str] = {}
    for e in agent_events:
        if e.subagent_type not in agent_timestamps:
            agent_timestamps[e.subagent_type] = e.timestamp

    # Check sequential pairs that were incorrectly parallelized
    for first_type, second_type in SEQUENTIAL_REQUIRED:
        if first_type not in agent_timestamps or second_type not in agent_timestamps:
            continue

        gap = _seconds_between(agent_timestamps[first_type], agent_timestamps[second_type])
        if gap is not None and gap <= TIMESTAMP_WINDOW_SECONDS:
            findings.append(Finding(
                finding_type="parallelization_violation",
                severity="CRITICAL",
                pattern_id="sequential_step_parallelized",
                description=(
                    f"{first_type} and {second_type} launched within {gap:.0f}s "
                    f"(must be sequential — {first_type} must complete before {second_type})"
                ),
                evidence=[
                    f"{first_type} at {agent_timestamps[first_type]}",
                    f"{second_type} at {agent_timestamps[second_type]}",
                    f"Gap: {gap:.1f}s (threshold: {TIMESTAMP_WINDOW_SECONDS}s)",
                ],
            ))

    # Check parallel pairs that were unnecessarily serialized
    for a_type, b_type in PARALLEL_EXPECTED:
        if a_type not in agent_timestamps or b_type not in agent_timestamps:
            continue

        gap = _seconds_between(agent_timestamps[a_type], agent_timestamps[b_type])
        if gap is not None and gap > PARALLEL_SERIALIZED_THRESHOLD:
            findings.append(Finding(
                finding_type="parallelization_suggestion",
                severity="INFO",
                pattern_id="parallel_step_serialized",
                description=(
                    f"{a_type} and {b_type} ran {gap:.0f}s apart "
                    f"(should be parallel for efficiency)"
                ),
                evidence=[
                    f"{a_type} at {agent_timestamps[a_type]}",
                    f"{b_type} at {agent_timestamps[b_type]}",
                    f"Gap: {gap:.1f}s (threshold: {PARALLEL_SERIALIZED_THRESHOLD}s)",
                ],
            ))

    return findings


def detect_ghost_invocations(
    events: List[PipelineEvent],
    *,
    max_duration_ms: int = 10000,
    max_result_words: int = 50,
) -> List[Finding]:
    """Detect ghost invocations: agent calls that completed too fast with minimal output.

    A ghost invocation is an agent call with duration < max_duration_ms AND
    result_word_count < max_result_words, suggesting the agent did not actually
    perform meaningful work.

    Args:
        events: List of PipelineEvent sorted by timestamp.
        max_duration_ms: Maximum duration in milliseconds to consider suspicious.
        max_result_words: Maximum result word count to consider suspicious.

    Returns:
        List of findings for ghost invocations.
    """
    findings: List[Finding] = []

    agent_events = [
        e for e in events
        if e.tool in AGENT_TOOL_NAMES and e.subagent_type
    ]

    for event in agent_events:
        # Both conditions must be true: fast AND low output
        if event.duration_ms > 0 and event.duration_ms < max_duration_ms and event.result_word_count < max_result_words:
            findings.append(Finding(
                finding_type="ghost_invocation",
                severity="WARNING",
                pattern_id="ghost_invocation",
                description=(
                    f"Agent {event.subagent_type} completed in {event.duration_ms}ms "
                    f"with only {event.result_word_count} result words "
                    f"(thresholds: <{max_duration_ms}ms, <{max_result_words} words) [GHOST]"
                ),
                evidence=[
                    f"subagent_type: {event.subagent_type}",
                    f"duration_ms: {event.duration_ms}",
                    f"result_word_count: {event.result_word_count}",
                    f"timestamp: {event.timestamp}",
                ],
            ))

    return findings


def detect_progressive_compression(events: List[PipelineEvent], *, agents_dir: Optional[Path] = None) -> List[Finding]:
    """Detect progressive prompt compression across batch issues.

    Groups agent events by batch_issue_number and compares prompt_word_count
    across issues for each agent type. Flags when prompts shrink beyond
    MAX_PROMPT_SHRINKAGE_RATIO from the baseline (issue with lowest number).

    Args:
        events: List of PipelineEvent sorted by timestamp.

    Returns:
        List of findings for progressive compression violations.
    """
    findings: List[Finding] = []

    # Filter to batch agent invocations with valid batch_issue_number
    batch_events = [
        e for e in events
        if e.tool in AGENT_TOOL_NAMES
        and e.subagent_type
        and e.batch_issue_number > 0
        and e.prompt_word_count > 0
    ]

    if not batch_events:
        return findings

    # Group by agent type -> {issue_number: prompt_word_count}
    # Use the first (earliest) event per agent per issue as representative
    agent_issue_prompts: dict[str, dict[int, int]] = {}
    for e in batch_events:
        agent_type = e.subagent_type
        if agent_type not in agent_issue_prompts:
            agent_issue_prompts[agent_type] = {}
        # Only record the first prompt per agent per issue
        if e.batch_issue_number not in agent_issue_prompts[agent_type]:
            agent_issue_prompts[agent_type][e.batch_issue_number] = e.prompt_word_count

    # For each agent, compare later issues against the baseline (lowest issue number)
    for agent_type, issue_prompts in agent_issue_prompts.items():
        if len(issue_prompts) < 2:
            continue

        sorted_issues = sorted(issue_prompts.keys())
        baseline_issue = sorted_issues[0]
        baseline_words = issue_prompts[baseline_issue]

        if baseline_words == 0:
            continue

        for issue_num in sorted_issues[1:]:
            current_words = issue_prompts[issue_num]
            ratio = current_words / baseline_words

            if ratio < (1 - MAX_PROMPT_SHRINKAGE_RATIO):
                shrinkage_pct = (1 - ratio) * 100

                severity = (
                    "CRITICAL"
                    if agent_type in COMPRESSION_CRITICAL_AGENTS
                    else "WARNING"
                )

                recommended_action = (
                    f"Reload prompt from agents/{agent_type}.md before "
                    f"processing issue #{issue_num}. Re-read the agent prompt "
                    f"file from disk instead of reusing compressed context."
                )
                evidence_list = [
                    f"baseline (issue #{baseline_issue}): {baseline_words} words",
                    f"current (issue #{issue_num}): {current_words} words",
                    f"ratio: {ratio:.3f} (threshold: {1 - MAX_PROMPT_SHRINKAGE_RATIO})",
                    f"agent_type: {agent_type}",
                ]
                if agents_dir is not None:
                    evidence_list.append(f"prompt_source: {agents_dir / f'{agent_type}.md'}")
                findings.append(Finding(
                    finding_type="progressive_compression",
                    severity=severity,
                    pattern_id="progressive_prompt_compression",
                    description=(
                        f"Agent {agent_type} prompt shrank {shrinkage_pct:.0f}% "
                        f"from issue #{baseline_issue} ({baseline_words} words) to "
                        f"issue #{issue_num} ({current_words} words) "
                        f"— progressive compression detected "
                        f"(threshold: {MAX_PROMPT_SHRINKAGE_RATIO:.0%} shrinkage)"
                    ),
                    evidence=evidence_list,
                    recommended_action=recommended_action,
                ))

    return findings


def detect_minimum_prompt_violation(events: List[PipelineEvent]) -> List[Finding]:
    """Check security-critical agents have minimum prompt word counts.

    Ensures that agents in COMPRESSION_CRITICAL_AGENTS receive prompts of at
    least MIN_CRITICAL_AGENT_PROMPT_WORDS words. Returns CRITICAL findings
    for violations.

    Args:
        events: List of PipelineEvent sorted by timestamp.

    Returns:
        List of findings for minimum prompt violations.
    """
    findings: List[Finding] = []

    # Filter to agent invocations for security-critical agents
    critical_events = [
        e for e in events
        if e.tool in AGENT_TOOL_NAMES
        and e.subagent_type in COMPRESSION_CRITICAL_AGENTS
        and e.prompt_word_count > 0
    ]

    for event in critical_events:
        if event.prompt_word_count < MIN_CRITICAL_AGENT_PROMPT_WORDS:
            findings.append(Finding(
                finding_type="minimum_prompt_violation",
                severity="CRITICAL",
                pattern_id="minimum_prompt_violation",
                description=(
                    f"Security-critical agent {event.subagent_type} received only "
                    f"{event.prompt_word_count} prompt words "
                    f"(minimum: {MIN_CRITICAL_AGENT_PROMPT_WORDS}) "
                    f"— prompt too short for meaningful analysis"
                ),
                evidence=[
                    f"agent_type: {event.subagent_type}",
                    f"prompt_word_count: {event.prompt_word_count}",
                    f"minimum_required: {MIN_CRITICAL_AGENT_PROMPT_WORDS}",
                    f"timestamp: {event.timestamp}",
                ],
            ))

    return findings


def _correlate_invocation_completion(
    events: List[PipelineEvent],
    *,
    max_window_seconds: float = 600,
) -> List[tuple]:
    """Pair agent invocation events with their completion events.

    Matches PostToolUse agent_invocation events with SubagentStop
    agent_completion events by subagent_type and temporal proximity.
    Each invocation is paired with the closest subsequent completion
    of the same subagent_type within max_window_seconds.

    Args:
        events: List of PipelineEvent sorted by timestamp.
        max_window_seconds: Maximum seconds between invocation and completion
            to consider them a pair.

    Returns:
        List of (invocation_event, completion_event_or_None) tuples.
    """
    invocations = [
        e for e in events
        if e.pipeline_action == "agent_invocation" and e.subagent_type
    ]
    completions = [
        e for e in events
        if e.pipeline_action == "agent_completion" and e.subagent_type
    ]

    used_completions: set[int] = set()  # indices into completions list
    pairs: List[tuple] = []

    for inv in invocations:
        best_completion = None
        best_idx = -1
        best_gap = float("inf")

        for idx, comp in enumerate(completions):
            if idx in used_completions:
                continue
            if comp.subagent_type != inv.subagent_type:
                continue

            gap = _seconds_between(inv.timestamp, comp.timestamp)
            if gap is None:
                continue

            # Completion must be AFTER invocation (or very close)
            inv_dt = _parse_timestamp(inv.timestamp)
            comp_dt = _parse_timestamp(comp.timestamp)
            if inv_dt is None or comp_dt is None:
                continue
            if comp_dt < inv_dt:
                continue

            if gap <= max_window_seconds and gap < best_gap:
                best_gap = gap
                best_completion = comp
                best_idx = idx

        if best_completion is not None:
            used_completions.add(best_idx)
            pairs.append((inv, best_completion))
        else:
            pairs.append((inv, None))

    return pairs


def detect_doc_verdict_missing(events: List[PipelineEvent]) -> List[Finding]:
    """Detect doc-master invocations that produced no output or failed.

    Correlates doc-master agent_invocation events with their matching
    agent_completion (SubagentStop) events to get actual result word counts.
    PostToolUse invocation events always have result_word_count=0, so this
    function uses the completion event's word count instead.

    Flags when:
    - No completion event exists for a doc-master invocation
    - Completion result_word_count < MIN_DOC_VERDICT_WORDS (too short for verdict)
    - Completion success is False

    Args:
        events: List of PipelineEvent sorted by timestamp.

    Returns:
        List of findings for doc-master verdict issues.
    """
    findings: List[Finding] = []

    # Get all correlated pairs
    pairs = _correlate_invocation_completion(events)

    # Filter to doc-master pairs
    doc_pairs = [(inv, comp) for inv, comp in pairs if inv.subagent_type == "doc-master"]

    for inv, comp in doc_pairs:
        if comp is None:
            # No completion event found — doc-master may have timed out or crashed
            findings.append(Finding(
                finding_type="doc_verdict_missing",
                severity="WARNING",
                pattern_id="doc_verdict_missing",
                description=(
                    f"[DOC-VERDICT-MISSING] doc-master invocation at {inv.timestamp} "
                    f"has no matching completion event — agent may have timed out or crashed. "
                    f"Documentation drift may go undetected."
                ),
                evidence=[
                    f"subagent_type: {inv.subagent_type}",
                    f"invocation_timestamp: {inv.timestamp}",
                    f"completion: not found",
                    f"success: unknown",
                ],
            ))
        elif not comp.success:
            # Completion exists but failed
            findings.append(Finding(
                finding_type="doc_verdict_missing",
                severity="WARNING",
                pattern_id="doc_verdict_missing",
                description=(
                    f"[DOC-VERDICT-MISSING] doc-master failed (success=False) "
                    f"at {comp.timestamp} — no DOC-DRIFT-VERDICT generated. "
                    f"Documentation drift may go undetected."
                ),
                evidence=[
                    f"subagent_type: {comp.subagent_type}",
                    f"result_word_count: {comp.result_word_count}",
                    f"invocation_timestamp: {inv.timestamp}",
                    f"completion_timestamp: {comp.timestamp}",
                    f"success: {comp.success}",
                ],
            ))
        elif comp.result_word_count < MIN_DOC_VERDICT_WORDS:
            # Completion exists but output too short for a meaningful verdict
            findings.append(Finding(
                finding_type="doc_verdict_missing",
                severity="WARNING",
                pattern_id="doc_verdict_missing",
                description=(
                    f"[DOC-VERDICT-MISSING] doc-master produced only "
                    f"{comp.result_word_count} result words at {comp.timestamp} "
                    f"(minimum: {MIN_DOC_VERDICT_WORDS}) — output too short for "
                    f"meaningful DOC-DRIFT-VERDICT. Documentation drift may go undetected."
                ),
                evidence=[
                    f"subagent_type: {comp.subagent_type}",
                    f"result_word_count: {comp.result_word_count}",
                    f"minimum_required: {MIN_DOC_VERDICT_WORDS}",
                    f"invocation_timestamp: {inv.timestamp}",
                    f"completion_timestamp: {comp.timestamp}",
                    f"success: {comp.success}",
                ],
            ))
        # else: completion has sufficient output and success=True — no finding

    return findings

def detect_batch_cia_skip(events: List[PipelineEvent]) -> List[Finding]:
    """Detect batch issues where continuous-improvement-analyst was not invoked.

    Identifies batch sessions by looking for events with batch_issue_number > 0,
    groups events by issue_number, and checks whether the continuous-improvement-analyst
    agent was invoked for each issue. The last issue missing CIA is flagged as WARNING
    (known regression pattern, Issue #505); non-last issues are flagged as INFO.

    Args:
        events: List of PipelineEvent sorted by timestamp.

    Returns:
        List of findings for batch CIA skip violations.
    """
    findings: List[Finding] = []

    # Filter to batch agent invocations with valid batch_issue_number
    batch_events = [
        e for e in events
        if e.tool in AGENT_TOOL_NAMES
        and e.subagent_type
        and e.batch_issue_number > 0
    ]

    if not batch_events:
        return findings

    # Group by issue number -> set of agent types that ran
    issue_agents: dict[int, set[str]] = {}
    for e in batch_events:
        issue_num = e.batch_issue_number
        if issue_num not in issue_agents:
            issue_agents[issue_num] = set()
        issue_agents[issue_num].add(e.subagent_type)

    if not issue_agents:
        return findings

    sorted_issues = sorted(issue_agents.keys())
    last_issue = sorted_issues[-1]

    for issue_num in sorted_issues:
        agents_ran = issue_agents[issue_num]
        if "continuous-improvement-analyst" not in agents_ran:
            is_last = issue_num == last_issue
            severity = "WARNING" if is_last else "INFO"
            pattern_id = (
                "batch_last_issue_cia_skip" if is_last
                else "batch_issue_cia_skip"
            )

            findings.append(Finding(
                finding_type="batch_cia_skip",
                severity=severity,
                pattern_id=pattern_id,
                description=(
                    f"Batch issue #{issue_num} missing continuous-improvement-analyst "
                    f"invocation{' (LAST ISSUE — known regression, Issue #505)' if is_last else ''}"
                ),
                evidence=[
                    f"issue_number: {issue_num}",
                    f"agents_ran: {sorted(agents_ran)}",
                    f"is_last_issue: {is_last}",
                    f"total_batch_issues: {len(sorted_issues)}",
                ],
            ))

    return findings

def _run_checks_on_events(events: List[PipelineEvent]) -> List[Finding]:
    """Run all check functions on a list of events from a single session.

    Args:
        events: List of PipelineEvent from one session (or ungrouped events).

    Returns:
        Combined list of all findings from all checks.
    """
    findings: List[Finding] = []
    findings.extend(validate_step_ordering(events))
    findings.extend(detect_hard_gate_ordering(events))
    findings.extend(detect_context_dropping(events))
    findings.extend(detect_parallelization_violations(events))
    findings.extend(detect_ghost_invocations(events))
    findings.extend(detect_progressive_compression(events))
    findings.extend(detect_minimum_prompt_violation(events))
    findings.extend(detect_doc_verdict_missing(events))
    findings.extend(detect_batch_cia_skip(events))
    return findings


def validate_pipeline_intent(
    log_path: Path,
    *,
    session_id: Optional[str] = None,
) -> List[Finding]:
    """Orchestrate all intent validation checks on a session log.

    When session_id is provided, only events from that session are checked
    (existing single-session behavior is unchanged).

    When session_id is not provided, events are grouped by their session_id
    field and each session's events are checked independently. This prevents
    false CRITICAL "step_ordering" findings that arise from comparing events
    across different sessions in the same daily JSONL log file (Issue #587).

    Events with an empty session_id (legacy logs without session tracking) are
    grouped together as a fallback and checked as a single virtual session.

    Args:
        log_path: Path to JSONL log file.
        session_id: Optional session ID filter. When provided, only events
            from this session are validated (single-session mode).

    Returns:
        Combined list of all findings, aggregated across all session groups.
    """
    events = parse_session_logs(log_path, session_id=session_id)
    if not events:
        return []

    # When an explicit session_id filter was provided, all returned events
    # already belong to that session — run checks on the flat list directly.
    if session_id:
        return _run_checks_on_events(events)

    # Group events by session_id to avoid cross-session false positives.
    # Events with empty session_id share a fallback group ("").
    session_groups: dict[str, List[PipelineEvent]] = {}
    for event in events:
        key = event.session_id  # "" for legacy events without session tracking
        if key not in session_groups:
            session_groups[key] = []
        session_groups[key].append(event)

    findings: List[Finding] = []
    for _sid, session_events in session_groups.items():
        findings.extend(_run_checks_on_events(session_events))
    return findings
