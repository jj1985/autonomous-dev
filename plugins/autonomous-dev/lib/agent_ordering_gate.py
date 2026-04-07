#!/usr/bin/env python3
"""
Agent Ordering Gate - Pure logic for pipeline agent ordering decisions.

No I/O, no side effects. Receives state as input, returns gate decisions.
Used by unified_pre_tool.py Layer 4 to enforce agent ordering at hook level.

Issues: #625, #629, #632, #636, #669
"""

from dataclasses import dataclass, field
from typing import Optional, Set

# Import canonical ordering from pipeline_intent_validator if available.
# Fall back to inline constants if import fails (e.g., running outside plugin).
try:
    from pipeline_intent_validator import SEQUENTIAL_REQUIRED, STEP_ORDER, TDD_FIRST_PAIRS
except ImportError:
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
    SEQUENTIAL_REQUIRED = [
        ("planner", "implementer"),
        ("implementer", "reviewer"),
        ("implementer", "security-auditor"),
        ("implementer", "doc-master"),
        ("reviewer", "security-auditor"),
    ]

    # TDD-first mode pairs: only enforced when test-master is in the pipeline.
    # In acceptance-first mode (default), test-master is skipped entirely.
    # Issue #636: unconditional enforcement blocked implementer in default mode.
    TDD_FIRST_PAIRS = [
        ("planner", "test-master"),
        ("test-master", "implementer"),
    ]

# Full set of agents for a complete pipeline run
FULL_PIPELINE_AGENTS = {
    "researcher-local",
    "researcher",
    "planner",
    "implementer",
    "reviewer",
    "security-auditor",
    "doc-master",
}

# Light mode requires fewer agents
LIGHT_PIPELINE_AGENTS = {
    "planner",
    "implementer",
    "doc-master",
}

# Fix mode requires only the core fix agents
FIX_PIPELINE_AGENTS = {
    "implementer",
    "reviewer",
    "doc-master",
}

# The sequential pair that is mode-dependent:
# In sequential mode, security-auditor requires reviewer.
# In parallel mode, this constraint is relaxed.
MODE_DEPENDENT_PAIRS = {("reviewer", "security-auditor")}

# Core ordering prerequisites (always enforced regardless of mode):
# These are derived from SEQUENTIAL_REQUIRED minus mode-dependent pairs.
CORE_PREREQUISITES: dict[str, set[str]] = {}

# Build prerequisite map from SEQUENTIAL_REQUIRED
for _prereq, _target in SEQUENTIAL_REQUIRED:
    if (_prereq, _target) not in MODE_DEPENDENT_PAIRS:
        CORE_PREREQUISITES.setdefault(_target, set()).add(_prereq)

# Mode-dependent prerequisites (only enforced in sequential mode)
SEQUENTIAL_ONLY_PREREQUISITES: dict[str, set[str]] = {}
for _prereq, _target in MODE_DEPENDENT_PAIRS:
    SEQUENTIAL_ONLY_PREREQUISITES.setdefault(_target, set()).add(_prereq)

# TDD-first prerequisites (only enforced when test-master has completed,
# indicating TDD-first mode is active). Issue #636.
TDD_FIRST_PREREQUISITES: dict[str, set[str]] = {}
for _prereq, _target in TDD_FIRST_PAIRS:
    TDD_FIRST_PREREQUISITES.setdefault(_target, set()).add(_prereq)


@dataclass
class GateResult:
    """Result of an ordering gate check.

    Attributes:
        passed: Whether the gate check passed.
        reason: Human-readable explanation.
        missing_agents: List of agents that need to complete first.
        warning: Optional warning message (e.g., parallel mode advisory). Issue #669.
    """

    passed: bool
    reason: str
    missing_agents: list[str] = field(default_factory=list)
    warning: Optional[str] = None


def check_ordering_prerequisites(
    target_agent: str,
    completed_agents: set[str],
    *,
    validation_mode: str = "sequential",
    launched_agents: Optional[set[str]] = None,
) -> GateResult:
    """Check if ordering prerequisites are met for a target agent.

    In sequential mode: all SEQUENTIAL_REQUIRED pairs are enforced.
    In parallel mode: mode-dependent pairs (reviewer -> security-auditor) are relaxed,
        but only if the prerequisite has at least been launched. If the prerequisite
        hasn't been launched at all, the check still blocks. Issue #669.
    Unknown agents always pass through.

    Args:
        target_agent: The agent about to be invoked.
        completed_agents: Set of agents that have already completed.
        validation_mode: "sequential" or "parallel".
        launched_agents: Set of agents that have been launched (started but not
            necessarily completed). Used in parallel mode to distinguish "running
            concurrently" from "skipped entirely". Issue #669.

    Returns:
        GateResult indicating whether the agent may proceed.
    """
    target = target_agent.strip().lower()

    # Unknown agents pass through
    if target not in STEP_ORDER:
        return GateResult(passed=True, reason=f"Unknown agent '{target}' - no ordering constraints")

    # Check core prerequisites (always enforced)
    missing = []
    core_prereqs = CORE_PREREQUISITES.get(target, set())
    for prereq in core_prereqs:
        if prereq not in completed_agents:
            missing.append(prereq)

    # Check mode-dependent prerequisites
    if validation_mode == "sequential":
        # Sequential mode: prerequisite must have completed
        seq_prereqs = SEQUENTIAL_ONLY_PREREQUISITES.get(target, set())
        for prereq in seq_prereqs:
            if prereq not in completed_agents:
                missing.append(prereq)
    elif validation_mode == "parallel":
        # Parallel mode: prerequisite is relaxed (doesn't need to have completed),
        # BUT if launched_agents is available, verify the prerequisite has at least
        # been launched. This prevents security-auditor from running when reviewer
        # hasn't even been started — parallel means "run concurrently", not "skip".
        # Issue #669: 3rd recurrence of security-auditor ordering violation.
        seq_prereqs = SEQUENTIAL_ONLY_PREREQUISITES.get(target, set())
        for prereq in seq_prereqs:
            if launched_agents is not None and prereq not in launched_agents:
                # Prerequisite hasn't been launched at all — block even in parallel mode
                missing.append(prereq)

    # Check TDD-first prerequisites (only when test-master has completed,
    # meaning TDD-first mode is active). Issue #636.
    if "test-master" in completed_agents:
        tdd_prereqs = TDD_FIRST_PREREQUISITES.get(target, set())
        for prereq in tdd_prereqs:
            if prereq not in completed_agents:
                missing.append(prereq)

    if missing:
        missing_str = ", ".join(sorted(missing))
        return GateResult(
            passed=False,
            reason=(
                f"ORDERING VIOLATION: '{target}' requires [{missing_str}] to complete first. "
                f"Mode: {validation_mode}. "
                f"REQUIRED NEXT ACTION: Wait for the prerequisite agent(s) to complete "
                f"before invoking this one. Do NOT skip or reorder pipeline agents."
            ),
            missing_agents=sorted(missing),
        )

    # Build result with optional parallel mode warning
    result_warning = None
    if validation_mode == "parallel":
        seq_prereqs = SEQUENTIAL_ONLY_PREREQUISITES.get(target, set())
        for prereq in seq_prereqs:
            if prereq not in completed_agents:
                result_warning = (
                    f"PARALLEL MODE WARNING: '{target}' running while prerequisite "
                    f"'{prereq}' has not completed. This is allowed in parallel mode "
                    f"but may indicate an ordering issue. Issue #669."
                )
                break

    return GateResult(
        passed=True,
        reason=f"Prerequisites met for '{target}'",
        warning=result_warning,
    )


def get_required_agents(
    mode: str = "full",
    *,
    research_skipped: bool = False,
) -> Set[str]:
    """Return the set of required agents for a given pipeline mode.

    Args:
        mode: Pipeline mode — "full", "light", "fix", or "tdd-first".
        research_skipped: If True and mode is "full", excludes researcher-local
            and researcher (they are legitimately skipped when issue body
            contains pre-researched content).

    Returns:
        A new set of required agent names (copy, not reference).
    """
    if mode == "fix":
        return set(FIX_PIPELINE_AGENTS)
    elif mode == "light":
        return set(LIGHT_PIPELINE_AGENTS)
    elif mode == "tdd-first":
        return set(FULL_PIPELINE_AGENTS) | {"test-master"}
    else:
        # full mode (default)
        agents = set(FULL_PIPELINE_AGENTS)
        if research_skipped:
            agents.discard("researcher-local")
            agents.discard("researcher")
        return agents


def check_minimum_agent_count(
    completed_agents: set[str],
    *,
    required_agents: set[str],
) -> GateResult:
    """Check that all required agents have completed (e.g., before git operations).

    Args:
        completed_agents: Set of agents that have completed.
        required_agents: Set of agents required to have completed.

    Returns:
        GateResult with missing agents if any are absent.
    """
    missing = sorted(required_agents - completed_agents)
    if missing:
        return GateResult(
            passed=False,
            reason=f"Missing required agents: {', '.join(missing)}",
            missing_agents=missing,
        )
    return GateResult(passed=True, reason="All required agents completed")


def check_batch_agent_completeness(
    completed_agents: set[str],
    issue_number: int,
    *,
    mode: str = "default",
) -> GateResult:
    """Check if all required agents have completed for a batch issue.

    Args:
        completed_agents: Set of agents that have completed for this issue.
        issue_number: The issue number being checked.
        mode: "default" for full pipeline, "light" for --light mode.

    Returns:
        GateResult with missing agents if pipeline is incomplete.
    """
    if mode == "light":
        required = LIGHT_PIPELINE_AGENTS
    elif mode == "fix":
        required = FIX_PIPELINE_AGENTS
    else:
        required = FULL_PIPELINE_AGENTS

    missing = sorted(required - completed_agents)
    if missing:
        return GateResult(
            passed=False,
            reason=f"Issue #{issue_number}: missing agents [{', '.join(missing)}] for {mode} mode",
            missing_agents=missing,
        )
    return GateResult(
        passed=True,
        reason=f"Issue #{issue_number}: all {mode} mode agents completed",
    )
