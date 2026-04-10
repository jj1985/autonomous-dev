"""
Regression test for Issue #760: Step ordering validator false positive in mixed-mode batches.

In mixed-mode batches (some --fix, some full), the `all()` check in
`_validate_step_ordering_for_group` failed because not all implementers were
--fix. The validator then compared the earliest implementer timestamp (from a
--fix issue) against the planner timestamp, firing a false CRITICAL.

Fix: Filter out --fix implementers before timestamp comparison instead of
requiring all implementers to be --fix.
"""

import sys
from pathlib import Path

import pytest

# Add lib to path (tests/regression/ -> tests/ -> repo root -> plugins)
LIB_DIR = Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from pipeline_intent_validator import (
    Finding,
    PipelineEvent,
    _validate_step_ordering_for_group,
)


def _make_event(
    subagent_type: str,
    timestamp: str,
    *,
    pipeline_mode: str = "",
) -> PipelineEvent:
    """Create a minimal PipelineEvent for ordering tests."""
    return PipelineEvent(
        timestamp=timestamp,
        tool="Agent",
        agent="main",
        subagent_type=subagent_type,
        pipeline_action="agent_invocation",
        pipeline_mode=pipeline_mode,
    )


class TestIssue760MixedModeOrdering:
    """Regression tests for Issue #760: mixed-mode batch false positive."""

    def test_mixed_mode_no_false_positive(self) -> None:
        """Mixed batch: fix implementer early + full implementer after planner = no violation.

        Scenario from Issue #760:
        - implementer at 09:38 (--fix mode, no planner needed)
        - planner at 09:59 (full mode)
        - implementer at 10:05 (full mode, correctly after planner)

        The non-fix implementer (10:05) is after the planner (09:59), so no
        ordering violation should be reported.
        """
        events = [
            _make_event("implementer", "2026-04-10T09:38:00", pipeline_mode="fix"),
            _make_event("planner", "2026-04-10T09:59:00", pipeline_mode=""),
            _make_event("implementer", "2026-04-10T10:05:00", pipeline_mode=""),
        ]

        findings = _validate_step_ordering_for_group(events, events)

        step_ordering_findings = [
            f for f in findings
            if f.finding_type == "step_ordering"
            and "implementer" in f.description
            and "planner" in f.description
        ]
        assert len(step_ordering_findings) == 0, (
            f"Should not flag implementer-before-planner when the early implementer "
            f"is --fix mode and the non-fix implementer is after the planner. "
            f"Got: {[f.description for f in step_ordering_findings]}. Issue #760."
        )

    def test_mixed_mode_real_violation_detected(self) -> None:
        """Mixed batch: non-fix implementer before planner IS a real violation.

        Scenario:
        - implementer at 09:38 (--fix mode, filtered out)
        - implementer at 09:40 (full mode, BEFORE planner = real violation)
        - planner at 09:59 (full mode)

        After filtering out --fix implementers, earliest non-fix implementer
        (09:40) is before planner (09:59) -> CRITICAL finding.
        """
        events = [
            _make_event("implementer", "2026-04-10T09:38:00", pipeline_mode="fix"),
            _make_event("implementer", "2026-04-10T09:40:00", pipeline_mode=""),
            _make_event("planner", "2026-04-10T09:59:00", pipeline_mode=""),
        ]

        findings = _validate_step_ordering_for_group(events, events)

        step_ordering_findings = [
            f for f in findings
            if f.finding_type == "step_ordering"
            and "implementer" in f.description
            and "planner" in f.description
        ]
        assert len(step_ordering_findings) == 1, (
            f"Should flag non-fix implementer before planner as CRITICAL. "
            f"Got {len(step_ordering_findings)} findings. Issue #760."
        )
        assert step_ordering_findings[0].severity == "CRITICAL"

    def test_all_fix_mode_skip_entirely(self) -> None:
        """All implementers are --fix mode: skip planner->implementer check entirely.

        When every implementer is --fix, there are no non-fix implementers to
        compare against. The check should be skipped (same behavior as #732).
        """
        events = [
            _make_event("implementer", "2026-04-10T09:38:00", pipeline_mode="--fix"),
            _make_event("implementer", "2026-04-10T09:40:00", pipeline_mode="fix"),
            _make_event("planner", "2026-04-10T09:59:00", pipeline_mode=""),
        ]

        findings = _validate_step_ordering_for_group(events, events)

        step_ordering_findings = [
            f for f in findings
            if f.finding_type == "step_ordering"
            and "implementer" in f.description
            and "planner" in f.description
        ]
        assert len(step_ordering_findings) == 0, (
            f"Should skip planner->implementer check when all implementers are fix mode. "
            f"Got: {[f.description for f in step_ordering_findings]}. Issue #760."
        )
