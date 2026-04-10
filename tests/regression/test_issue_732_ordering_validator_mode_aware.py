"""
Regression test for Issue #732: Step ordering violation false positive.

The pipeline_intent_validator.py was flagging "implementer before planner" in
batch sessions where --fix mode issues (which don't need planner) ran before
--light issues. This was a false positive because --fix mode doesn't use planner.

Fix: The validator skips the planner->implementer ordering check when the
implementer event carries pipeline_mode="--fix" (or "fix").
"""

import sys
from pathlib import Path

import pytest

# Add lib to path (tests/regression/ -> tests/ -> repo root -> plugins)
LIB_DIR = Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from pipeline_intent_validator import (
    PipelineEvent,
    validate_step_ordering,
    _validate_step_ordering_for_group,
)


def _make_event(
    subagent_type: str,
    timestamp: str,
    *,
    batch_issue_number: int = 0,
    pipeline_mode: str = "",
) -> PipelineEvent:
    """Create a minimal PipelineEvent for ordering tests."""
    return PipelineEvent(
        timestamp=timestamp,
        tool="Agent",
        agent="main",
        subagent_type=subagent_type,
        pipeline_action="agent_invocation",
        batch_issue_number=batch_issue_number,
        pipeline_mode=pipeline_mode,
    )


class TestFixModeOrderingNoFalsePositive:
    """Regression tests for Issue #732: --fix mode ordering false positive."""

    def test_fix_mode_implementer_before_planner_not_flagged(self) -> None:
        """Implementer before planner in --fix mode is NOT a violation.

        This is the core regression: in a batch session where a --fix issue
        runs before a --light issue, the validator was incorrectly flagging
        the fix-mode implementer (which ran before planner) as a violation.
        """
        events = [
            # --fix issue: implementer runs at T1, no planner
            _make_event("implementer", "2026-01-01T10:00:00Z",
                        batch_issue_number=101, pipeline_mode="--fix"),
            # --light issue: planner then implementer
            _make_event("planner", "2026-01-01T10:05:00Z",
                        batch_issue_number=102, pipeline_mode="--light"),
            _make_event("implementer", "2026-01-01T10:10:00Z",
                        batch_issue_number=102, pipeline_mode="--light"),
        ]

        findings = validate_step_ordering(events)

        ordering_violations = [
            f for f in findings
            if f.finding_type == "step_ordering"
            and "implementer" in f.description
            and "planner" in f.description
        ]
        assert len(ordering_violations) == 0, (
            f"Should not flag implementer-before-planner for --fix mode issue. "
            f"Got violations: {[f.description for f in ordering_violations]}. "
            f"Issue #732."
        )

    def test_fix_mode_implementer_in_single_group_not_flagged(self) -> None:
        """Single-group ordering check skips planner->implementer for fix mode."""
        events = [
            # Only implementer, no planner (fix mode)
            _make_event("implementer", "2026-01-01T10:00:00Z", pipeline_mode="--fix"),
            _make_event("reviewer", "2026-01-01T10:15:00Z", pipeline_mode="--fix"),
        ]

        findings = _validate_step_ordering_for_group(events, events)

        ordering_violations = [
            f for f in findings
            if f.finding_type == "step_ordering"
            and "planner" in f.description
        ]
        assert len(ordering_violations) == 0, (
            f"Single-group check should skip planner->implementer for fix mode. "
            f"Got violations: {[f.description for f in ordering_violations]}. "
            f"Issue #732."
        )

    def test_non_fix_mode_implementer_before_planner_is_still_flagged(self) -> None:
        """Implementer before planner in non-fix mode IS still a violation.

        The fix must not suppress legitimate ordering violations.
        """
        events = [
            # implementer before planner in full (non-fix) mode
            _make_event("implementer", "2026-01-01T10:00:00Z", pipeline_mode="full"),
            _make_event("planner", "2026-01-01T10:05:00Z", pipeline_mode="full"),
        ]

        findings = _validate_step_ordering_for_group(events, events)

        ordering_violations = [
            f for f in findings
            if f.finding_type == "step_ordering"
            and "planner" in f.description
            and "implementer" in f.description
        ]
        assert len(ordering_violations) > 0, (
            "Should flag implementer-before-planner in full (non-fix) mode. "
            "Issue #732."
        )

    def test_implementer_before_planner_with_no_mode_is_still_flagged(self) -> None:
        """Implementer before planner with no pipeline_mode set is still a violation.

        Empty pipeline_mode must not be treated as fix mode.
        """
        events = [
            _make_event("implementer", "2026-01-01T10:00:00Z", pipeline_mode=""),
            _make_event("planner", "2026-01-01T10:05:00Z", pipeline_mode=""),
        ]

        findings = _validate_step_ordering_for_group(events, events)

        ordering_violations = [
            f for f in findings
            if f.finding_type == "step_ordering"
            and "planner" in f.description
            and "implementer" in f.description
        ]
        assert len(ordering_violations) > 0, (
            "Should flag implementer-before-planner when pipeline_mode is empty. "
            "Issue #732."
        )

    def test_fix_mode_string_without_dashes_also_skipped(self) -> None:
        """pipeline_mode='fix' (without dashes) is also treated as fix mode."""
        events = [
            _make_event("implementer", "2026-01-01T10:00:00Z", pipeline_mode="fix"),
            _make_event("reviewer", "2026-01-01T10:15:00Z", pipeline_mode="fix"),
        ]

        findings = _validate_step_ordering_for_group(events, events)

        ordering_violations = [
            f for f in findings
            if f.finding_type == "step_ordering"
            and "planner" in f.description
        ]
        assert len(ordering_violations) == 0, (
            "pipeline_mode='fix' (without dashes) should also skip the check. "
            "Issue #732."
        )

    def test_mixed_batch_fix_then_light_no_false_positive(self) -> None:
        """Batch with fix issue first, light issue second: no false positive.

        Regression scenario from Issue #732:
        - Batch runs --fix issues (T1..T3), then --light issues (T4..T6)
        - --fix issue 101 has implementer at T1 (no planner)
        - --light issue 102 has planner at T4, implementer at T5
        - Validator must NOT flag issue 101's implementer as "before planner"
        """
        events = [
            # Fix issue runs first
            _make_event("implementer", "2026-01-01T10:00:00Z",
                        batch_issue_number=101, pipeline_mode="--fix"),
            _make_event("reviewer", "2026-01-01T10:05:00Z",
                        batch_issue_number=101, pipeline_mode="--fix"),
            # Light issue runs after
            _make_event("planner", "2026-01-01T10:10:00Z",
                        batch_issue_number=102, pipeline_mode="--light"),
            _make_event("implementer", "2026-01-01T10:15:00Z",
                        batch_issue_number=102, pipeline_mode="--light"),
            _make_event("doc-master", "2026-01-01T10:20:00Z",
                        batch_issue_number=102, pipeline_mode="--light"),
        ]

        findings = validate_step_ordering(events)

        critical_findings = [
            f for f in findings
            if f.severity == "CRITICAL"
            and "planner" in f.description
            and "implementer" in f.description
        ]
        assert len(critical_findings) == 0, (
            f"No CRITICAL planner/implementer ordering violations expected for "
            f"fix+light batch. Got: {[f.description for f in critical_findings]}. "
            f"Issue #732."
        )


class TestPipelineModeFieldParsing:
    """Tests for the new pipeline_mode field on PipelineEvent."""

    def test_pipeline_event_has_pipeline_mode_field(self) -> None:
        """PipelineEvent.pipeline_mode defaults to empty string."""
        event = PipelineEvent(
            timestamp="2026-01-01T10:00:00Z",
            tool="Agent",
            agent="main",
            subagent_type="implementer",
            pipeline_action="agent_invocation",
        )
        assert hasattr(event, "pipeline_mode")
        assert event.pipeline_mode == ""

    def test_pipeline_event_accepts_pipeline_mode(self) -> None:
        """PipelineEvent.pipeline_mode can be set to '--fix'."""
        event = _make_event("implementer", "2026-01-01T10:00:00Z", pipeline_mode="--fix")
        assert event.pipeline_mode == "--fix"
