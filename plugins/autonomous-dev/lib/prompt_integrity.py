#!/usr/bin/env python3
"""
Prompt Integrity - Issue #601, #603

Provides prompt integrity validation and prevention functions for the batch
coordinator. While pipeline_intent_validator.py detects compression after the
fact (post-hoc analysis of logs), this module provides real-time prevention
that the coordinator calls before each agent invocation.

Usage:
    from prompt_integrity import (
        validate_prompt_word_count,
        record_prompt_baseline,
        get_prompt_baseline,
        get_agent_prompt_template,
        clear_prompt_baselines,
    )

    # At batch start
    clear_prompt_baselines()

    # First issue - establish baselines
    result = validate_prompt_word_count("reviewer", prompt)
    record_prompt_baseline("reviewer", issue_number=1, word_count=len(prompt.split()))

    # Subsequent issues - validate against baseline
    baseline = get_prompt_baseline("reviewer")
    result = validate_prompt_word_count("reviewer", prompt, baseline)
    if result.should_reload:
        template = get_agent_prompt_template("reviewer")
        # Reconstruct prompt from template + issue context
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Critical agents that require minimum prompt word counts.
# Mirrors COMPRESSION_CRITICAL_AGENTS in pipeline_intent_validator.py.
COMPRESSION_CRITICAL_AGENTS = {"security-auditor", "reviewer", "researcher-local", "researcher"}

# Minimum word count for critical agent prompts.
# Matches MIN_CRITICAL_AGENT_PROMPT_WORDS in pipeline_intent_validator.py.
MIN_CRITICAL_AGENT_PROMPT_WORDS = 80

# Default baseline persistence location (relative to project root).
_DEFAULT_BASELINES_RELPATH = Path(".claude") / "logs" / "prompt_baselines.json"


@dataclass
class PromptIntegrityResult:
    """Result of a prompt integrity validation check.

    Attributes:
        agent_type: Agent name that was validated.
        word_count: Actual word count of the prompt.
        baseline_word_count: Word count from the first issue (None if first issue).
        shrinkage_pct: Shrinkage percentage vs baseline (0.0 if no baseline).
        passed: Whether the validation passed.
        reason: Human-readable explanation of the result.
        should_reload: True if coordinator should re-read agent source from disk.
    """

    agent_type: str
    word_count: int
    baseline_word_count: Optional[int]
    shrinkage_pct: float
    passed: bool
    reason: str
    should_reload: bool


def _find_project_root(start: Optional[Path] = None) -> Path:
    """Walk up from start directory looking for project root markers.

    Args:
        start: Directory to start searching from. Defaults to CWD.

    Returns:
        Path to project root.

    Raises:
        FileNotFoundError: If no project root can be found.
    """
    current = start or Path.cwd()
    while current != current.parent:
        if (current / "plugins" / "autonomous-dev" / "agents").is_dir():
            return current
        if (current / ".git").exists() or (current / ".claude").exists():
            return current
        current = current.parent
    raise FileNotFoundError(
        f"Could not find project root from {start or Path.cwd()}.\n"
        f"Expected a directory containing plugins/autonomous-dev/agents/ or .git/"
    )


def get_agent_prompt_template(
    agent_type: str,
    *,
    agents_dir: Optional[Path] = None,
) -> str:
    """Read an agent's prompt template from its source file on disk.

    Args:
        agent_type: Agent name (e.g., 'reviewer', 'security-auditor').
        agents_dir: Optional override for agents directory path.

    Returns:
        Full text content of the agent's .md file.

    Raises:
        FileNotFoundError: If agent file does not exist.
    """
    if agents_dir is None:
        root = _find_project_root()
        agents_dir = root / "plugins" / "autonomous-dev" / "agents"

    agent_file = agents_dir / f"{agent_type}.md"
    if not agent_file.exists():
        raise FileNotFoundError(
            f"Agent prompt template not found: {agent_file}\n"
            f"Expected .md file in {agents_dir}/"
        )

    return agent_file.read_text(encoding="utf-8")


def validate_prompt_word_count(
    agent_type: str,
    prompt: str,
    baseline_word_count: Optional[int] = None,
    *,
    max_shrinkage: float = 0.20,
) -> PromptIntegrityResult:
    """Validate a constructed prompt against word count thresholds.

    Checks (in order):
    1. Prompt must not be empty.
    2. For critical agents, word count must be >= MIN_CRITICAL_AGENT_PROMPT_WORDS.
    3. If baseline provided, shrinkage must be <= max_shrinkage (default 20%).

    Args:
        agent_type: Agent name for context.
        prompt: The constructed prompt text to validate.
        baseline_word_count: Word count from first issue (None if first issue).
        max_shrinkage: Maximum allowed shrinkage ratio (0.20 = 20%).

    Returns:
        PromptIntegrityResult with validation outcome.
    """
    word_count = len(prompt.split())

    # Check 1: Empty prompt
    if word_count == 0:
        return PromptIntegrityResult(
            agent_type=agent_type,
            word_count=0,
            baseline_word_count=baseline_word_count,
            shrinkage_pct=100.0 if baseline_word_count else 0.0,
            passed=False,
            reason=f"Prompt for {agent_type} is empty (0 words).",
            should_reload=True,
        )

    # Check 2: Critical agent minimum
    if (
        agent_type in COMPRESSION_CRITICAL_AGENTS
        and word_count < MIN_CRITICAL_AGENT_PROMPT_WORDS
    ):
        return PromptIntegrityResult(
            agent_type=agent_type,
            word_count=word_count,
            baseline_word_count=baseline_word_count,
            shrinkage_pct=(
                round((1.0 - word_count / baseline_word_count) * 100, 1)
                if baseline_word_count
                else 0.0
            ),
            passed=False,
            reason=(
                f"Critical agent {agent_type} has only {word_count} words "
                f"(minimum: {MIN_CRITICAL_AGENT_PROMPT_WORDS})."
            ),
            should_reload=True,
        )

    # Check 3: Baseline shrinkage
    if baseline_word_count is not None and baseline_word_count > 0:
        shrinkage_pct = round((1.0 - word_count / baseline_word_count) * 100, 1)

        if shrinkage_pct > max_shrinkage * 100:
            return PromptIntegrityResult(
                agent_type=agent_type,
                word_count=word_count,
                baseline_word_count=baseline_word_count,
                shrinkage_pct=shrinkage_pct,
                passed=False,
                reason=(
                    f"Prompt for {agent_type} shrank {shrinkage_pct:.1f}% "
                    f"from baseline ({baseline_word_count} -> {word_count} words, "
                    f"threshold: {max_shrinkage:.0%})."
                ),
                should_reload=True,
            )
    else:
        shrinkage_pct = 0.0

    # All checks passed
    return PromptIntegrityResult(
        agent_type=agent_type,
        word_count=word_count,
        baseline_word_count=baseline_word_count,
        shrinkage_pct=shrinkage_pct if baseline_word_count else 0.0,
        passed=True,
        reason=f"Prompt for {agent_type} OK ({word_count} words).",
        should_reload=False,
    )


def _get_baselines_path(state_dir: Optional[Path] = None) -> Path:
    """Resolve the path to the prompt baselines JSON file.

    Args:
        state_dir: Optional override directory. If None, uses project root.

    Returns:
        Absolute path to prompt_baselines.json.
    """
    if state_dir is not None:
        return state_dir / "prompt_baselines.json"
    root = _find_project_root()
    return root / _DEFAULT_BASELINES_RELPATH


def record_prompt_baseline(
    agent_type: str,
    issue_number: int,
    word_count: int,
    *,
    state_dir: Optional[Path] = None,
) -> None:
    """Record prompt word count as baseline for comparison across issues.

    Persists to .claude/logs/prompt_baselines.json (or state_dir override).
    Structure: {agent_type: {str(issue_number): word_count}}

    Args:
        agent_type: Agent name (e.g., 'reviewer').
        issue_number: GitHub issue number being processed.
        word_count: Word count of the prompt sent to this agent.
        state_dir: Optional override for state directory.
    """
    baselines_path = _get_baselines_path(state_dir)
    baselines_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if baselines_path.exists():
        try:
            data = json.loads(baselines_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read baselines file, starting fresh: %s", baselines_path)
            data = {}

    if agent_type not in data:
        data[agent_type] = {}

    data[agent_type][str(issue_number)] = word_count

    baselines_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.debug(
        "Recorded baseline: %s issue #%d = %d words", agent_type, issue_number, word_count
    )


def get_prompt_baseline(
    agent_type: str,
    *,
    state_dir: Optional[Path] = None,
) -> Optional[int]:
    """Get the baseline word count (from first recorded issue) for an agent.

    The baseline is the word count from the issue with the lowest number,
    representing the first issue processed in the batch.

    Args:
        agent_type: Agent name to look up.
        state_dir: Optional override for state directory.

    Returns:
        Word count from the first issue, or None if no baseline exists.
    """
    baselines_path = _get_baselines_path(state_dir)

    if not baselines_path.exists():
        return None

    try:
        data = json.loads(baselines_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Could not read baselines file: %s", baselines_path)
        return None

    agent_data = data.get(agent_type)
    if not agent_data:
        return None

    # Find entry with lowest issue number (first issue in batch)
    try:
        lowest_issue = min(agent_data.keys(), key=lambda k: int(k))
        return agent_data[lowest_issue]
    except (ValueError, TypeError):
        return None


def clear_prompt_baselines(*, state_dir: Optional[Path] = None) -> None:
    """Clear all prompt baselines. Call at batch start.

    Args:
        state_dir: Optional override for state directory.
    """
    baselines_path = _get_baselines_path(state_dir)
    if baselines_path.exists():
        baselines_path.unlink()
        logger.debug("Cleared prompt baselines: %s", baselines_path)
