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
COMPRESSION_CRITICAL_AGENTS = {
    "security-auditor",
    "reviewer",
    "researcher-local",
    "researcher",
    "implementer",
    "planner",
    "doc-master",
}

# Minimum word count for critical agent prompts.
# Matches MIN_CRITICAL_AGENT_PROMPT_WORDS in pipeline_intent_validator.py.
MIN_CRITICAL_AGENT_PROMPT_WORDS = 80

# Maximum cumulative shrinkage across an entire batch (Issue #794).
# Individual issues may pass the 25% per-issue threshold but accumulate
# progressive 3-5% per-iteration compression that this catches.
MAX_CUMULATIVE_SHRINKAGE = 0.20  # 20% total drift threshold

# Known reinvocation context strings (Issue #789, #791).
# These represent legitimate secondary agent invocations that produce
# naturally shorter prompts, so the shrinkage threshold is relaxed.
REINVOCATION_CONTEXTS = {"remediation", "re-review", "doc-update-retry"}


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
    max_shrinkage: float = 0.15,
    invocation_context: Optional[str] = None,
) -> PromptIntegrityResult:
    """Validate a constructed prompt against word count thresholds.

    Checks (in order):
    1. Prompt must not be empty.
    2. For critical agents, word count must be >= MIN_CRITICAL_AGENT_PROMPT_WORDS.
    3. If baseline provided, shrinkage must be <= max_shrinkage (default 15%).

    Args:
        agent_type: Agent name for context.
        prompt: The constructed prompt text to validate.
        baseline_word_count: Word count from first issue (None if first issue).
        max_shrinkage: Maximum allowed shrinkage ratio (0.15 = 15%).

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

        # Relax threshold for known reinvocation contexts (Issue #789, #791)
        effective_max_shrinkage = max_shrinkage
        if invocation_context and invocation_context in REINVOCATION_CONTEXTS:
            effective_max_shrinkage = max_shrinkage * 2.0
            logger.debug(
                "Relaxed shrinkage threshold for %s context: %.0f%% -> %.0f%%",
                invocation_context,
                max_shrinkage * 100,
                effective_max_shrinkage * 100,
            )

        if shrinkage_pct > effective_max_shrinkage * 100:
            ctx_note = (
                f" [relaxed from {max_shrinkage:.0%} for {invocation_context}]"
                if invocation_context and invocation_context in REINVOCATION_CONTEXTS
                else ""
            )
            return PromptIntegrityResult(
                agent_type=agent_type,
                word_count=word_count,
                baseline_word_count=baseline_word_count,
                shrinkage_pct=shrinkage_pct,
                passed=False,
                reason=(
                    f"Prompt for {agent_type} shrank {shrinkage_pct:.1f}% "
                    f"from baseline ({baseline_word_count} -> {word_count} words, "
                    f"threshold: {effective_max_shrinkage:.0%}{ctx_note})."
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
    issue_number: Optional[int] = None,
    state_dir: Optional[Path] = None,
) -> Optional[int]:
    """Get the baseline word count for an agent.

    When issue_number is provided, returns the baseline for THAT specific issue
    only (per-issue isolation for batch mode — Issue #764). When issue_number is
    None, falls back to the original behavior: returns the word count from the
    issue with the lowest number (first issue in batch).

    Args:
        agent_type: Agent name to look up.
        issue_number: Specific issue to get baseline for. When provided, only
            returns the baseline recorded for this exact issue. When None,
            returns the baseline from the lowest-numbered issue (backward compat).
        state_dir: Optional override for state directory.

    Returns:
        Word count baseline, or None if no baseline exists.
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

    # Per-issue lookup (Issue #764): return baseline for this specific issue only
    if issue_number is not None:
        issue_key = str(issue_number)
        baseline = agent_data.get(issue_key)
        if baseline is not None:
            logger.debug(
                "Per-issue baseline lookup: %s issue #%s = %d words",
                agent_type, issue_key, baseline,
            )
        return baseline

    # Backward compat: find entry with lowest issue number (first issue in batch)
    try:
        lowest_issue = min(agent_data.keys(), key=lambda k: int(k))
        return agent_data[lowest_issue]
    except (ValueError, TypeError):
        return None


def clear_prompt_baselines(*, state_dir: Optional[Path] = None) -> None:
    """Clear all prompt baselines and batch observations. Call at batch start.

    Also clears batch observations (Issue #794) so cumulative drift tracking
    resets alongside baselines.

    Args:
        state_dir: Optional override for state directory.
    """
    baselines_path = _get_baselines_path(state_dir)
    if baselines_path.exists():
        baselines_path.unlink()
        logger.debug("Cleared prompt baselines: %s", baselines_path)
    # Also clear batch observations (Issue #794)
    clear_batch_observations(state_dir=state_dir)


def compute_template_baselines(*, agents_dir: Optional[Path] = None) -> dict:
    """Compute word counts for each critical agent's prompt template.

    Reads each agent's .md file from disk and measures its word count.
    Agents with missing template files are skipped with a warning.

    Args:
        agents_dir: Optional override for agents directory path.

    Returns:
        Mapping of {agent_type: word_count} for agents with found templates.
    """
    if agents_dir is None:
        root = _find_project_root()
        agents_dir = root / "plugins" / "autonomous-dev" / "agents"

    baselines: dict = {}
    for agent_type in COMPRESSION_CRITICAL_AGENTS:
        agent_file = agents_dir / f"{agent_type}.md"
        if not agent_file.exists():
            logger.warning(
                "Template baseline: agent file not found, skipping: %s", agent_file
            )
            continue
        try:
            template = agent_file.read_text(encoding="utf-8")
            baselines[agent_type] = len(template.split())
            logger.debug(
                "Template baseline computed: %s = %d words", agent_type, baselines[agent_type]
            )
        except OSError as exc:
            logger.warning(
                "Template baseline: could not read %s: %s", agent_file, exc
            )

    return baselines


def seed_baselines_from_templates(
    *,
    agents_dir: Optional[Path] = None,
    state_dir: Optional[Path] = None,
) -> dict:
    """Seed prompt baselines from template word counts at batch start.

    Computes word counts from agent template files and records them as
    issue_number=0 baselines so the first real issue is compared against
    the canonical template size, not the (potentially already-compressed)
    observed first invocation.

    A 0.70 slack factor is applied (Issue #759) because template files are
    the full agent definition (~2500 words) but task-specific prompts are
    naturally 20-40% shorter. Seeding at 100% caused immediate false positives.

    Call this immediately after clear_prompt_baselines() at the start of
    each batch run.

    Args:
        agents_dir: Optional override for agents directory path.
        state_dir: Optional override for state directory (baseline JSON location).

    Returns:
        Mapping of {agent_type: adjusted_word_count} for agents successfully seeded.
    """
    # Slack factor for template-seeded baselines (Issue #759).
    # Template files are the full agent definition; task-specific prompts are
    # naturally 20-40% shorter. 0.70 allows legitimate variation without
    # triggering false positives.
    TEMPLATE_BASELINE_SLACK_FACTOR = 0.70

    template_baselines = compute_template_baselines(agents_dir=agents_dir)
    for agent_type, word_count in template_baselines.items():
        adjusted_wc = int(word_count * TEMPLATE_BASELINE_SLACK_FACTOR)
        record_prompt_baseline(
            agent_type, issue_number=0, word_count=adjusted_wc, state_dir=state_dir
        )
        logger.debug(
            "Seeded template baseline: %s = %d words (adjusted from %d)",
            agent_type, adjusted_wc, word_count,
        )
    logger.info(
        "Seeded template baselines for %d agents: %s",
        len(template_baselines),
        sorted(template_baselines.keys()),
    )
    return template_baselines


def _get_observations_path(state_dir: Optional[Path] = None) -> Path:
    """Resolve the path to the batch observations JSON file.

    Args:
        state_dir: Optional override directory. If None, uses project root.

    Returns:
        Absolute path to prompt_batch_observations.json.
    """
    if state_dir is not None:
        return state_dir / "prompt_batch_observations.json"
    root = _find_project_root()
    return root / ".claude" / "logs" / "prompt_batch_observations.json"


def record_batch_observation(
    agent_type: str,
    issue_number: int,
    word_count: int,
    *,
    state_dir: Optional[Path] = None,
) -> None:
    """Record a prompt word count observation for cumulative drift tracking.

    Appends to prompt_batch_observations.json file. Each agent_type gets a list
    of observations recording the word count at each issue in the batch.

    Args:
        agent_type: Agent name (e.g., 'reviewer').
        issue_number: GitHub issue number being processed.
        word_count: Word count of the prompt sent to this agent.
        state_dir: Optional override for state directory.
    """
    obs_path = _get_observations_path(state_dir)
    obs_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if obs_path.exists():
        try:
            data = json.loads(obs_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "Could not read batch observations file, starting fresh: %s", obs_path
            )
            data = {}

    if agent_type not in data:
        data[agent_type] = []

    data[agent_type].append({"issue": issue_number, "word_count": word_count})

    obs_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.debug(
        "Recorded batch observation: %s issue #%d = %d words",
        agent_type,
        issue_number,
        word_count,
    )


def get_cumulative_shrinkage(
    agent_type: str,
    *,
    state_dir: Optional[Path] = None,
) -> Optional[float]:
    """Get cumulative shrinkage percentage for an agent across the batch.

    Computes drift from the first observation to the latest observation for
    the specified agent_type.

    Args:
        agent_type: Agent name to look up.
        state_dir: Optional override for state directory.

    Returns:
        Shrinkage percentage (e.g., 20.0 for 20%), or None if fewer than
        2 observations exist for this agent. Returns 0.0 if latest >= first.
    """
    obs_path = _get_observations_path(state_dir)

    if not obs_path.exists():
        return None

    try:
        data = json.loads(obs_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Could not read batch observations file: %s", obs_path)
        return None

    observations = data.get(agent_type)
    if not observations or len(observations) < 2:
        return None

    first_wc = observations[0]["word_count"]
    latest_wc = observations[-1]["word_count"]

    if first_wc <= 0:
        return None

    shrinkage = (first_wc - latest_wc) / first_wc * 100
    return max(0.0, round(shrinkage, 1))


def clear_batch_observations(*, state_dir: Optional[Path] = None) -> None:
    """Clear all batch observations. Call at batch start.

    Args:
        state_dir: Optional override for state directory.
    """
    obs_path = _get_observations_path(state_dir)
    obs_path.unlink(missing_ok=True)
    logger.debug("Cleared batch observations: %s", obs_path)
