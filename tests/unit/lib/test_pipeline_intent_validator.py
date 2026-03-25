#!/usr/bin/env python3
"""
TDD Tests for Pipeline Intent Validator Library (Issue #367) - RED PHASE

Tests validate pipeline_intent_validator.py which detects intent-level
pipeline violations: step ordering, hard gate bypasses, context dropping,
and parallelization violations.

All tests FAIL initially (lib/pipeline_intent_validator.py doesn't exist yet).
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Portable project root detection
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

from pipeline_intent_validator import (
    Finding,
    MIN_DOC_VERDICT_WORDS,
    PipelineEvent,
    VALID_AGENT_TYPES,
    _correlate_invocation_completion,
    detect_batch_cia_skip,
    detect_context_dropping,
    detect_doc_verdict_missing,
    detect_ghost_invocations,
    detect_hard_gate_ordering,
    detect_parallelization_violations,
    detect_progressive_compression,
    get_minimum_prompt_content,
    parse_session_logs,
    validate_pipeline_intent,
    validate_step_ordering,
)


def _make_event(
    agent: str = "main",
    subagent_type: str = "",
    pipeline_action: str = "agent_invocation",
    tool: str = "Task",
    timestamp: str = "2026-02-28T10:00:00+00:00",
    prompt_word_count: int = 500,
    result_word_count: int = 2000,
    success: bool = True,
    batch_issue_number: int = 0,
) -> PipelineEvent:
    """Helper to create PipelineEvent for tests."""
    return PipelineEvent(
        timestamp=timestamp,
        tool=tool,
        agent=agent,
        subagent_type=subagent_type,
        pipeline_action=pipeline_action,
        prompt_word_count=prompt_word_count,
        result_word_count=result_word_count,
        success=success,
        batch_issue_number=batch_issue_number,
    )


def _make_jsonl_line(
    agent: str = "main",
    subagent_type: str = "",
    pipeline_action: str = "agent_invocation",
    tool: str = "Task",
    timestamp: str = "2026-02-28T10:00:00+00:00",
    prompt_word_count: int = 500,
    result_word_count: int = 2000,
    success: bool = True,
    session_id: str = "test-session",
    command: str = "",
) -> str:
    """Helper to create JSONL log line."""
    if tool == "Task":
        entry = {
            "timestamp": timestamp,
            "tool": tool,
            "input_summary": {
                "description": f"Run {subagent_type}",
                "subagent_type": subagent_type,
                "pipeline_action": pipeline_action,
                "prompt_word_count": prompt_word_count,
            },
            "output_summary": {
                "success": success,
                "result_word_count": result_word_count,
            },
            "session_id": session_id,
            "agent": agent,
        }
    else:
        entry = {
            "timestamp": timestamp,
            "tool": tool,
            "input_summary": {
                "command": command or "pytest --tb=short -q",
                "pipeline_action": pipeline_action,
            },
            "output_summary": {"success": success},
            "session_id": session_id,
            "agent": agent,
        }
    return json.dumps(entry)


def _write_clean_pipeline(log_file: Path, session_id: str = "test-session") -> None:
    """Write a clean pipeline JSONL with correct ordering.

    Includes SubagentStop entries for doc-master (and other STEP 6 agents) so
    that detect_doc_verdict_missing can correlate invocations with completions
    without producing false positives. (Issue #562)
    """
    base = datetime(2026, 2, 28, 10, 0, 0)
    # Build a SubagentStop entry for doc-master (simulates real pipeline behavior)
    doc_master_completion = json.dumps({
        "timestamp": (base + timedelta(minutes=14)).isoformat(),
        "hook": "SubagentStop",
        "subagent_type": "doc-master",
        "duration_ms": 180000,
        "result_word_count": 200,
        "session_id": session_id,
        "success": True,
    })
    lines = [
        _make_jsonl_line(subagent_type="researcher-local", timestamp=(base).isoformat(), session_id=session_id),
        _make_jsonl_line(subagent_type="researcher", timestamp=(base + timedelta(seconds=2)).isoformat(), session_id=session_id),
        _make_jsonl_line(subagent_type="planner", timestamp=(base + timedelta(minutes=2)).isoformat(), session_id=session_id),
        _make_jsonl_line(subagent_type="test-master", timestamp=(base + timedelta(minutes=4)).isoformat(), session_id=session_id),
        _make_jsonl_line(subagent_type="implementer", timestamp=(base + timedelta(minutes=6)).isoformat(), session_id=session_id),
        _make_jsonl_line(tool="Bash", pipeline_action="test_run", timestamp=(base + timedelta(minutes=8)).isoformat(), session_id=session_id),
        _make_jsonl_line(subagent_type="reviewer", timestamp=(base + timedelta(minutes=10)).isoformat(), session_id=session_id),
        _make_jsonl_line(subagent_type="security-auditor", timestamp=(base + timedelta(minutes=12)).isoformat(), session_id=session_id),
        _make_jsonl_line(subagent_type="doc-master", timestamp=(base + timedelta(minutes=10, seconds=4)).isoformat(), session_id=session_id),
        doc_master_completion,
    ]
    log_file.write_text("\n".join(lines) + "\n")


class TestParseSessionLogs:
    """Tests for parse_session_logs function."""

    def test_parses_task_entries_from_jsonl(self, tmp_path):
        """Task tool entries are parsed into PipelineEvent with correct fields."""
        log_file = tmp_path / "session.jsonl"
        log_file.write_text(
            _make_jsonl_line(subagent_type="researcher-local", prompt_word_count=500, result_word_count=2000) + "\n"
        )
        events = parse_session_logs(log_file)
        assert len(events) == 1, "#367: should parse one event"
        e = events[0]
        assert e.subagent_type == "researcher-local", "#367: subagent_type"
        assert e.tool == "Task", "#367: tool"
        assert e.prompt_word_count == 500, "#367: prompt_word_count"
        assert e.result_word_count == 2000, "#367: result_word_count"

    def test_filters_by_session_id(self, tmp_path):
        """Only events matching session_id are returned."""
        log_file = tmp_path / "session.jsonl"
        lines = [
            _make_jsonl_line(subagent_type="researcher", session_id="session-a"),
            _make_jsonl_line(subagent_type="planner", session_id="session-b"),
        ]
        log_file.write_text("\n".join(lines) + "\n")
        events = parse_session_logs(log_file, session_id="session-a")
        assert len(events) == 1, "#367: session filter should return 1 event"
        assert events[0].subagent_type == "researcher"

    def test_handles_empty_file(self, tmp_path):
        """Empty file returns empty list."""
        log_file = tmp_path / "empty.jsonl"
        log_file.write_text("")
        events = parse_session_logs(log_file)
        assert events == [], "#367: empty file should return empty list"

    def test_handles_malformed_lines(self, tmp_path):
        """Malformed JSON lines are skipped."""
        log_file = tmp_path / "bad.jsonl"
        lines = [
            "not json at all",
            _make_jsonl_line(subagent_type="planner"),
            '{"incomplete": true',
        ]
        log_file.write_text("\n".join(lines) + "\n")
        events = parse_session_logs(log_file)
        assert len(events) == 1, "#367: should skip malformed, parse valid"

    def test_includes_bash_test_run(self, tmp_path):
        """Bash entries with pipeline_action=test_run are included."""
        log_file = tmp_path / "session.jsonl"
        log_file.write_text(
            _make_jsonl_line(tool="Bash", pipeline_action="test_run", command="pytest --tb=short -q") + "\n"
        )
        events = parse_session_logs(log_file)
        assert len(events) == 1, "#367: Bash test_run should be included"
        assert events[0].tool == "Bash"
        assert events[0].pipeline_action == "test_run"


class TestParseAgentToolName:
    """Tests for Agent tool name handling (fix for issue #380)."""

    def test_parses_agent_tool_entries(self, tmp_path):
        """Agent tool entries (new Claude Code name) should be parsed into PipelineEvent."""
        log_file = tmp_path / "agent.jsonl"
        # Use "Agent" tool name instead of "Task"
        entry = {
            "timestamp": "2026-03-08T10:00:00+00:00",
            "tool": "Agent",
            "input_summary": {
                "description": "Research patterns",
                "subagent_type": "researcher",
                "pipeline_action": "agent_invocation",
                "prompt_word_count": 500,
            },
            "output_summary": {"success": True, "result_word_count": 2000},
            "session_id": "test-session",
            "agent": "main",
        }
        log_file.write_text(json.dumps(entry) + "\n")
        events = parse_session_logs(log_file)
        assert len(events) == 1, "#380: Agent tool should be parsed"
        assert events[0].subagent_type == "researcher"
        assert events[0].tool == "Agent"

    def test_mixed_task_and_agent_tools(self, tmp_path):
        """Both Task (old) and Agent (new) tool names should be parsed."""
        log_file = tmp_path / "mixed.jsonl"
        task_entry = {
            "timestamp": "2026-02-28T10:00:00+00:00",
            "tool": "Task",
            "input_summary": {"subagent_type": "planner", "pipeline_action": "agent_invocation"},
            "output_summary": {"success": True},
            "session_id": "test-session",
            "agent": "main",
        }
        agent_entry = {
            "timestamp": "2026-03-08T10:00:00+00:00",
            "tool": "Agent",
            "input_summary": {"subagent_type": "implementer", "pipeline_action": "agent_invocation"},
            "output_summary": {"success": True},
            "session_id": "test-session",
            "agent": "main",
        }
        log_file.write_text(json.dumps(task_entry) + "\n" + json.dumps(agent_entry) + "\n")
        events = parse_session_logs(log_file)
        assert len(events) == 2, "#380: both Task and Agent should be parsed"
        assert events[0].subagent_type == "planner"
        assert events[1].subagent_type == "implementer"

    def test_step_ordering_with_agent_tool(self):
        """Step ordering validation should work with Agent tool events."""
        base = datetime(2026, 3, 8, 10, 0, 0)
        events = [
            _make_event(subagent_type="implementer", tool="Agent", timestamp=base.isoformat()),
            _make_event(subagent_type="planner", tool="Agent", timestamp=(base + timedelta(minutes=2)).isoformat()),
        ]
        findings = validate_step_ordering(events)
        assert len(findings) >= 1, "#380: ordering violation should be detected with Agent tool"

    def test_context_dropping_with_agent_tool(self):
        """Context dropping detection should work with Agent tool events."""
        base = datetime(2026, 3, 8, 10, 0, 0)
        events = [
            _make_event(subagent_type="researcher", tool="Agent", timestamp=base.isoformat(), result_word_count=2000),
            _make_event(subagent_type="planner", tool="Agent", timestamp=(base + timedelta(minutes=2)).isoformat(), prompt_word_count=50),
        ]
        findings = detect_context_dropping(events)
        assert len(findings) >= 1, "#380: context dropping should be detected with Agent tool"


class TestValidateStepOrdering:
    """Tests for validate_step_ordering function."""

    def test_correct_order_passes(self):
        """Correctly ordered pipeline produces no findings."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="researcher-local", timestamp=base.isoformat()),
            _make_event(subagent_type="planner", timestamp=(base + timedelta(minutes=2)).isoformat()),
            _make_event(subagent_type="test-master", timestamp=(base + timedelta(minutes=4)).isoformat()),
            _make_event(subagent_type="implementer", timestamp=(base + timedelta(minutes=6)).isoformat()),
        ]
        findings = validate_step_ordering(events)
        assert len(findings) == 0, "#367: correct order should have no findings"

    def test_implementer_before_planner(self):
        """Implementer running before planner is a CRITICAL finding."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="implementer", timestamp=base.isoformat()),
            _make_event(subagent_type="planner", timestamp=(base + timedelta(minutes=2)).isoformat()),
        ]
        findings = validate_step_ordering(events)
        assert len(findings) >= 1, "#367: wrong order should produce findings"
        assert any(f.severity == "CRITICAL" for f in findings), "#367: should be CRITICAL"

    def test_missing_test_master_not_flagged_in_acceptance_first_mode(self):
        """Absence of test-master must NOT produce a CRITICAL finding.

        In acceptance-first mode (the default), test-master is intentionally skipped.
        Flagging it as CRITICAL is a false positive on every default pipeline run. (#518)
        """
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="researcher-local", timestamp=base.isoformat()),
            _make_event(subagent_type="planner", timestamp=(base + timedelta(minutes=2)).isoformat()),
            _make_event(subagent_type="implementer", timestamp=(base + timedelta(minutes=4)).isoformat()),
            _make_event(subagent_type="reviewer", timestamp=(base + timedelta(minutes=6)).isoformat()),
        ]
        findings = validate_step_ordering(events)
        test_master_findings = [
            f for f in findings if f.pattern_id == "step_skipping_test_master"
        ]
        assert len(test_master_findings) == 0, (
            "#518: test-master absence must not produce step_skipping_test_master finding "
            "in acceptance-first (default) mode"
        )

    def test_batch_mode_not_checked(self):
        """Events without full pipeline indicator skip ordering checks."""
        # Single agent invocation - not a full pipeline
        events = [_make_event(subagent_type="implementer")]
        findings = validate_step_ordering(events)
        # Should not flag ordering for incomplete/batch pipelines
        assert not any(f.pattern_id == "step_ordering" for f in findings), (
            "#367: single-agent runs should not trigger ordering checks"
        )


class TestDetectHardGateOrdering:
    """Tests for detect_hard_gate_ordering function."""

    def test_step6_before_pytest_critical(self):
        """STEP 6 agents before any test_run is CRITICAL."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="implementer", timestamp=base.isoformat()),
            _make_event(subagent_type="reviewer", timestamp=(base + timedelta(minutes=1)).isoformat()),
            _make_event(tool="Bash", pipeline_action="test_run", timestamp=(base + timedelta(minutes=5)).isoformat()),
        ]
        findings = detect_hard_gate_ordering(events)
        assert len(findings) >= 1, "#367: step6 before pytest should produce findings"
        assert any(f.severity == "CRITICAL" for f in findings)

    def test_step6_after_pytest_passes(self):
        """STEP 6 agents after pytest produces no findings."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="implementer", timestamp=base.isoformat()),
            _make_event(tool="Bash", pipeline_action="test_run", timestamp=(base + timedelta(minutes=2)).isoformat()),
            _make_event(subagent_type="reviewer", timestamp=(base + timedelta(minutes=4)).isoformat()),
        ]
        findings = detect_hard_gate_ordering(events)
        assert len(findings) == 0, "#367: normal order should have no findings"

    def test_no_pytest_at_all(self):
        """No test_run but STEP 6 agents exist is CRITICAL."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="implementer", timestamp=base.isoformat()),
            _make_event(subagent_type="reviewer", timestamp=(base + timedelta(minutes=2)).isoformat()),
            _make_event(subagent_type="security-auditor", timestamp=(base + timedelta(minutes=3)).isoformat()),
        ]
        findings = detect_hard_gate_ordering(events)
        assert len(findings) >= 1, "#367: no pytest with step6 agents should be CRITICAL"
        assert any(f.severity == "CRITICAL" for f in findings)

    def test_pytest_failed_but_step6_ran(self):
        """Pytest failed (success=false) but STEP 6 ran is CRITICAL."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="implementer", timestamp=base.isoformat()),
            _make_event(tool="Bash", pipeline_action="test_run", timestamp=(base + timedelta(minutes=2)).isoformat(), success=False),
            _make_event(subagent_type="reviewer", timestamp=(base + timedelta(minutes=4)).isoformat()),
        ]
        findings = detect_hard_gate_ordering(events)
        assert len(findings) >= 1, "#367: failed pytest + step6 should be CRITICAL"
        assert any(f.severity == "CRITICAL" for f in findings)


class TestDetectContextDropping:
    """Tests for detect_context_dropping function."""

    def test_low_ratio_flagged(self):
        """Prompt much smaller than prior result is WARNING."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="researcher", timestamp=base.isoformat(), result_word_count=2000),
            _make_event(subagent_type="planner", timestamp=(base + timedelta(minutes=2)).isoformat(), prompt_word_count=50, result_word_count=1000),
        ]
        findings = detect_context_dropping(events)
        assert len(findings) >= 1, "#367: 50/2000 ratio should flag context dropping"
        assert any(f.finding_type == "context_dropping" for f in findings)

    def test_high_ratio_passes(self):
        """Reasonable prompt/result ratio produces no findings."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="researcher", timestamp=base.isoformat(), result_word_count=2000),
            _make_event(subagent_type="planner", timestamp=(base + timedelta(minutes=2)).isoformat(), prompt_word_count=800, result_word_count=1000),
        ]
        findings = detect_context_dropping(events)
        assert len(findings) == 0, "#367: 800/2000 ratio should not flag"

    def test_missing_word_counts_skipped(self):
        """Events without word counts are gracefully skipped."""
        events = [
            _make_event(subagent_type="researcher", result_word_count=0),
            _make_event(subagent_type="planner", prompt_word_count=0),
        ]
        findings = detect_context_dropping(events)
        assert len(findings) == 0, "#367: zero word counts should be skipped"

    def test_threshold_configurable(self):
        """Custom threshold catches more cases."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="researcher", timestamp=base.isoformat(), result_word_count=2000),
            _make_event(subagent_type="planner", timestamp=(base + timedelta(minutes=2)).isoformat(), prompt_word_count=800, result_word_count=1000),
        ]
        # Default threshold 0.2 would pass (800/2000=0.4), but 0.5 should flag
        findings = detect_context_dropping(events, threshold=0.5)
        assert len(findings) >= 1, "#367: threshold=0.5 should catch 0.4 ratio"


class TestDetectParallelizationViolations:
    """Tests for detect_parallelization_violations function."""

    def test_sequential_agents_parallelized_critical(self):
        """test-master and implementer within 5s is CRITICAL."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="test-master", timestamp=base.isoformat()),
            _make_event(subagent_type="implementer", timestamp=(base + timedelta(seconds=3)).isoformat()),
        ]
        findings = detect_parallelization_violations(events)
        assert len(findings) >= 1, "#367: sequential agents parallelized should be CRITICAL"
        assert any(f.severity == "CRITICAL" for f in findings)

    def test_parallel_agents_serialized_info(self):
        """researcher-local and researcher >30s apart is INFO."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="researcher-local", timestamp=base.isoformat()),
            _make_event(subagent_type="researcher", timestamp=(base + timedelta(seconds=45)).isoformat()),
        ]
        findings = detect_parallelization_violations(events)
        assert len(findings) >= 1, "#367: parallel agents serialized should produce finding"
        assert any(f.severity == "INFO" for f in findings)

    def test_correct_parallelization_passes(self):
        """Correct parallelization produces no findings."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        events = [
            _make_event(subagent_type="researcher-local", timestamp=base.isoformat()),
            _make_event(subagent_type="researcher", timestamp=(base + timedelta(seconds=2)).isoformat()),
            _make_event(subagent_type="test-master", timestamp=(base + timedelta(minutes=5)).isoformat()),
            _make_event(subagent_type="implementer", timestamp=(base + timedelta(minutes=10)).isoformat()),
        ]
        findings = detect_parallelization_violations(events)
        assert len(findings) == 0, "#367: correct parallelization should have no findings"


class TestValidatePipelineIntent:
    """Tests for validate_pipeline_intent orchestrator function."""

    def test_clean_pipeline_no_findings(self, tmp_path):
        """Clean pipeline JSONL produces no findings."""
        log_file = tmp_path / "clean.jsonl"
        _write_clean_pipeline(log_file)
        findings = validate_pipeline_intent(log_file, session_id="test-session")
        assert len(findings) == 0, "#367: clean pipeline should have no findings"

    def test_multiple_violations_detected(self, tmp_path):
        """JSONL with multiple issues detects all of them."""
        base = datetime(2026, 2, 28, 10, 0, 0)
        log_file = tmp_path / "bad.jsonl"
        lines = [
            # Implementer before planner (ordering violation)
            _make_jsonl_line(subagent_type="implementer", timestamp=base.isoformat()),
            _make_jsonl_line(subagent_type="planner", timestamp=(base + timedelta(minutes=2)).isoformat()),
            # Reviewer before any pytest (hard gate violation)
            _make_jsonl_line(subagent_type="reviewer", timestamp=(base + timedelta(minutes=3)).isoformat()),
        ]
        log_file.write_text("\n".join(lines) + "\n")
        findings = validate_pipeline_intent(log_file, session_id="test-session")
        assert len(findings) >= 2, "#367: multiple violations should all be detected"


class TestDetectGhostInvocations:
    """Tests for detect_ghost_invocations function (Issue #442)."""

    def test_ghost_detected_fast_and_low_output(self):
        """Agent with duration <10s AND result_word_count <50 is a ghost."""
        events = [
            PipelineEvent(
                timestamp="2026-02-28T10:00:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="researcher",
                pipeline_action="agent_invocation",
                duration_ms=5000,
                result_word_count=10,
            ),
        ]
        findings = detect_ghost_invocations(events)
        assert len(findings) == 1
        assert findings[0].finding_type == "ghost_invocation"
        assert findings[0].severity == "WARNING"
        assert "GHOST" in findings[0].description

    def test_no_ghost_when_duration_high(self):
        """Agent with duration >10s should not be flagged even with low output."""
        events = [
            PipelineEvent(
                timestamp="2026-02-28T10:00:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="researcher",
                pipeline_action="agent_invocation",
                duration_ms=15000,
                result_word_count=10,
            ),
        ]
        findings = detect_ghost_invocations(events)
        assert len(findings) == 0

    def test_no_ghost_when_output_high(self):
        """Agent with result_word_count >50 should not be flagged even if fast."""
        events = [
            PipelineEvent(
                timestamp="2026-02-28T10:00:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="implementer",
                pipeline_action="agent_invocation",
                duration_ms=5000,
                result_word_count=200,
            ),
        ]
        findings = detect_ghost_invocations(events)
        assert len(findings) == 0

    def test_ghost_skipped_when_duration_zero(self):
        """Agent with duration_ms=0 (not recorded) should not be flagged."""
        events = [
            PipelineEvent(
                timestamp="2026-02-28T10:00:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="researcher",
                pipeline_action="agent_invocation",
                duration_ms=0,
                result_word_count=10,
            ),
        ]
        findings = detect_ghost_invocations(events)
        assert len(findings) == 0

    def test_custom_thresholds(self):
        """Custom thresholds should be respected."""
        events = [
            PipelineEvent(
                timestamp="2026-02-28T10:00:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="planner",
                pipeline_action="agent_invocation",
                duration_ms=3000,
                result_word_count=30,
            ),
        ]
        # Default thresholds: 10000ms, 50 words -> this IS a ghost
        findings = detect_ghost_invocations(events)
        assert len(findings) == 1
        # Tighter thresholds: 2000ms, 20 words -> NOT a ghost
        findings = detect_ghost_invocations(events, max_duration_ms=2000, max_result_words=20)
        assert len(findings) == 0

    def test_ghost_integrated_in_validate_pipeline_intent(self, tmp_path):
        """Ghost detection runs as part of validate_pipeline_intent."""
        log_file = tmp_path / "ghost.jsonl"
        entry = {
            "timestamp": "2026-02-28T10:00:00+00:00",
            "tool": "Agent",
            "input_summary": {
                "subagent_type": "researcher",
                "pipeline_action": "agent_invocation",
                "prompt_word_count": 500,
            },
            "output_summary": {"success": True, "result_word_count": 5},
            "session_id": "test-session",
            "agent": "main",
            "duration_ms": 2000,
        }
        log_file.write_text(json.dumps(entry) + "\n")
        findings = validate_pipeline_intent(log_file, session_id="test-session")
        ghost_findings = [f for f in findings if f.finding_type == "ghost_invocation"]
        assert len(ghost_findings) == 1


class TestSubagentStopParsing:
    """Tests for SubagentStop JSONL entry parsing."""

    def test_parse_subagent_stop_entry(self, tmp_path):
        """SubagentStop JSONL creates PipelineEvent with pipeline_action=agent_completion."""
        log_file = tmp_path / "session.jsonl"
        entry = {
            "timestamp": "2026-03-17T10:00:00+00:00",
            "hook": "SubagentStop",
            "subagent_type": "researcher",
            "duration_ms": 5000,
            "result_word_count": 150,
            "agent_transcript_path": "/Users/test/.claude/transcripts/abc.jsonl",
            "session_id": "test-session",
            "success": True,
        }
        log_file.write_text(json.dumps(entry) + "\n")
        events = parse_session_logs(log_file)
        assert len(events) == 1
        e = events[0]
        assert e.pipeline_action == "agent_completion"
        assert e.subagent_type == "researcher"
        assert e.tool == "Agent"
        assert e.success is True

    def test_subagent_stop_duration_ms(self, tmp_path):
        """duration_ms is populated from SubagentStop entry."""
        log_file = tmp_path / "session.jsonl"
        entry = {
            "timestamp": "2026-03-17T10:05:00+00:00",
            "hook": "SubagentStop",
            "subagent_type": "implementer",
            "duration_ms": 120000,
            "result_word_count": 500,
            "session_id": "test-session",
            "success": True,
        }
        log_file.write_text(json.dumps(entry) + "\n")
        events = parse_session_logs(log_file)
        assert len(events) == 1
        assert events[0].duration_ms == 120000

    def test_subagent_stop_with_transcript_path(self, tmp_path):
        """agent_transcript_path is populated on PipelineEvent."""
        log_file = tmp_path / "session.jsonl"
        entry = {
            "timestamp": "2026-03-17T10:10:00+00:00",
            "hook": "SubagentStop",
            "subagent_type": "planner",
            "duration_ms": 30000,
            "result_word_count": 200,
            "agent_transcript_path": "/Users/test/.claude/transcripts/planner.jsonl",
            "session_id": "test-session",
            "success": True,
        }
        log_file.write_text(json.dumps(entry) + "\n")
        events = parse_session_logs(log_file)
        assert len(events) == 1
        assert events[0].agent_transcript_path == "/Users/test/.claude/transcripts/planner.jsonl"

    def test_ghost_detection_uses_subagent_stop(self, tmp_path):
        """detect_ghost_invocations works with SubagentStop events (agent_completion)."""
        log_file = tmp_path / "session.jsonl"
        entry = {
            "timestamp": "2026-03-17T10:00:00+00:00",
            "hook": "SubagentStop",
            "subagent_type": "researcher",
            "duration_ms": 3000,
            "result_word_count": 10,
            "session_id": "test-session",
            "success": True,
        }
        log_file.write_text(json.dumps(entry) + "\n")
        events = parse_session_logs(log_file)
        assert len(events) == 1
        # SubagentStop events have tool="Agent" and subagent_type set,
        # so ghost detection should pick them up
        findings = detect_ghost_invocations(events)
        assert len(findings) == 1
        assert findings[0].finding_type == "ghost_invocation"


class TestReviewerBeforeSecurityAuditor:
    """Tests for STEP 6 ordering: reviewer before security-auditor (#495, #498)."""

    def test_reviewer_before_security_auditor_no_finding(self):
        """Reviewer completing before security-auditor produces no ordering violation."""
        base = datetime(2026, 3, 19, 10, 0, 0)
        events = [
            _make_event(subagent_type="implementer", timestamp=base.isoformat()),
            _make_event(subagent_type="reviewer", timestamp=(base + timedelta(minutes=10)).isoformat()),
            _make_event(subagent_type="security-auditor", timestamp=(base + timedelta(minutes=15)).isoformat()),
        ]
        findings = validate_step_ordering(events)
        ordering_findings = [f for f in findings if f.finding_type == "step_ordering"]
        assert len(ordering_findings) == 0, "reviewer then security-auditor is correct ordering"

    def test_security_auditor_before_reviewer_flagged(self):
        """Security-auditor running before reviewer is a CRITICAL step_ordering violation."""
        base = datetime(2026, 3, 19, 10, 0, 0)
        events = [
            _make_event(subagent_type="implementer", timestamp=base.isoformat()),
            _make_event(subagent_type="security-auditor", timestamp=(base + timedelta(minutes=10)).isoformat()),
            _make_event(subagent_type="reviewer", timestamp=(base + timedelta(minutes=15)).isoformat()),
        ]
        findings = validate_step_ordering(events)
        ordering_findings = [f for f in findings if f.finding_type == "step_ordering"]
        assert len(ordering_findings) >= 1, "security-auditor before reviewer should be flagged"
        assert any(f.severity == "CRITICAL" for f in ordering_findings)

    def test_reviewer_security_auditor_parallelized_flagged(self):
        """Reviewer and security-auditor launched within 5s is a parallelization violation."""
        base = datetime(2026, 3, 19, 10, 0, 0)
        events = [
            _make_event(subagent_type="reviewer", timestamp=base.isoformat()),
            _make_event(subagent_type="security-auditor", timestamp=(base + timedelta(seconds=2)).isoformat()),
        ]
        findings = detect_parallelization_violations(events)
        assert len(findings) >= 1, "reviewer+security-auditor within 5s should be flagged"
        assert any(
            f.finding_type == "parallelization_violation" and f.severity == "CRITICAL"
            for f in findings
        )


class TestDataStructures:
    """Tests for PipelineEvent and Finding dataclasses."""

    def test_pipeline_event_fields(self):
        """PipelineEvent has all required fields."""
        e = PipelineEvent(
            timestamp="2026-02-28T10:00:00+00:00",
            tool="Task",
            agent="main",
            subagent_type="researcher",
            pipeline_action="agent_invocation",
            prompt_word_count=500,
            result_word_count=2000,
        )
        assert e.timestamp == "2026-02-28T10:00:00+00:00"
        assert e.tool == "Task"
        assert e.subagent_type == "researcher"

    def test_finding_fields(self):
        """Finding has all required fields."""
        f = Finding(
            finding_type="step_ordering",
            severity="CRITICAL",
            pattern_id="implementer_before_planner",
            description="Implementer ran before planner",
            evidence=["timestamp1", "timestamp2"],
        )
        assert f.severity == "CRITICAL"
        assert f.finding_type == "step_ordering"
        assert len(f.evidence) == 2
        assert f.recommended_action is None  # default is None
        f2 = Finding(
            finding_type="test",
            severity="INFO",
            pattern_id="test",
            description="test",
            recommended_action="Reload from agents/reviewer.md",
        )
        assert f2.recommended_action == "Reload from agents/reviewer.md"


class TestDetectDocVerdictMissing:
    """Tests for detect_doc_verdict_missing function (Issues #543, #562)."""

    def test_doc_master_with_completion_passes(self):
        """doc-master invocation paired with healthy completion produces NO findings."""
        events = [
            _make_event(
                subagent_type="doc-master",
                tool="Agent",
                pipeline_action="agent_invocation",
                result_word_count=0,  # PostToolUse always 0
                success=True,
                timestamp="2026-03-22T10:00:00+00:00",
            ),
            PipelineEvent(
                timestamp="2026-03-22T10:02:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="doc-master",
                pipeline_action="agent_completion",
                result_word_count=200,  # SubagentStop has actual output
                success=True,
            ),
        ]
        findings = detect_doc_verdict_missing(events)
        assert len(findings) == 0, "#562: healthy completion should produce no findings"

    def test_doc_master_no_completion_flagged(self):
        """doc-master invocation with no matching completion is flagged."""
        events = [
            _make_event(
                subagent_type="doc-master",
                tool="Agent",
                pipeline_action="agent_invocation",
                result_word_count=0,
                success=True,
            ),
        ]
        findings = detect_doc_verdict_missing(events)
        assert len(findings) == 1
        assert findings[0].finding_type == "doc_verdict_missing"
        assert findings[0].severity == "WARNING"
        assert "[DOC-VERDICT-MISSING]" in findings[0].description

    def test_doc_master_completion_low_output_flagged(self):
        """doc-master completion with very low word count is flagged."""
        events = [
            _make_event(
                subagent_type="doc-master",
                tool="Agent",
                pipeline_action="agent_invocation",
                result_word_count=0,
                success=True,
                timestamp="2026-03-22T10:00:00+00:00",
            ),
            PipelineEvent(
                timestamp="2026-03-22T10:02:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="doc-master",
                pipeline_action="agent_completion",
                result_word_count=10,  # Below MIN_DOC_VERDICT_WORDS
                success=True,
            ),
        ]
        findings = detect_doc_verdict_missing(events)
        assert len(findings) == 1
        assert findings[0].finding_type == "doc_verdict_missing"
        assert "[DOC-VERDICT-MISSING]" in findings[0].description

    def test_doc_master_completion_failed_flagged(self):
        """doc-master completion with success=False is flagged."""
        events = [
            _make_event(
                subagent_type="doc-master",
                tool="Agent",
                pipeline_action="agent_invocation",
                result_word_count=0,
                success=True,
                timestamp="2026-03-22T10:00:00+00:00",
            ),
            PipelineEvent(
                timestamp="2026-03-22T10:02:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="doc-master",
                pipeline_action="agent_completion",
                result_word_count=200,
                success=False,
            ),
        ]
        findings = detect_doc_verdict_missing(events)
        assert len(findings) == 1
        assert findings[0].finding_type == "doc_verdict_missing"
        assert "[DOC-VERDICT-MISSING]" in findings[0].description

    def test_no_doc_master_events_no_findings(self):
        """Events without doc-master produce no findings."""
        events = [
            _make_event(subagent_type="researcher", tool="Agent", result_word_count=500),
            _make_event(subagent_type="implementer", tool="Agent", result_word_count=1000),
        ]
        findings = detect_doc_verdict_missing(events)
        assert len(findings) == 0

    def test_integrated_in_validate_pipeline_intent(self, tmp_path):
        """Verify detect_doc_verdict_missing works through validate_pipeline_intent.

        When a doc-master invocation has result_word_count=0 (PostToolUse) but
        a matching SubagentStop has result_word_count=200, no finding should be produced.
        This is the false positive that Issue #562 fixes.
        """
        log_file = tmp_path / "doc_missing.jsonl"
        # PostToolUse entry (invocation with result_word_count=0)
        invocation_entry = {
            "timestamp": "2026-03-22T10:00:00+00:00",
            "tool": "Agent",
            "input_summary": {
                "subagent_type": "doc-master",
                "pipeline_action": "agent_invocation",
                "prompt_word_count": 500,
            },
            "output_summary": {"success": True, "result_word_count": 0},
            "session_id": "test-session",
            "agent": "main",
        }
        # SubagentStop entry (completion with actual word count)
        completion_entry = {
            "timestamp": "2026-03-22T10:02:00+00:00",
            "hook": "SubagentStop",
            "subagent_type": "doc-master",
            "duration_ms": 30000,
            "result_word_count": 200,
            "session_id": "test-session",
            "success": True,
        }
        log_file.write_text(
            json.dumps(invocation_entry) + "\n" + json.dumps(completion_entry) + "\n"
        )
        findings = validate_pipeline_intent(log_file, session_id="test-session")
        doc_findings = [f for f in findings if f.finding_type == "doc_verdict_missing"]
        assert len(doc_findings) == 0, (
            "#562: doc-master with healthy SubagentStop should NOT produce false positive"
        )

    def test_invocation_only_no_completion_flagged_via_log(self, tmp_path):
        """Verify that an invocation-only log (no SubagentStop) is flagged."""
        log_file = tmp_path / "doc_missing_no_completion.jsonl"
        entry = {
            "timestamp": "2026-03-22T10:00:00+00:00",
            "tool": "Agent",
            "input_summary": {
                "subagent_type": "doc-master",
                "pipeline_action": "agent_invocation",
                "prompt_word_count": 500,
            },
            "output_summary": {"success": True, "result_word_count": 0},
            "session_id": "test-session",
            "agent": "main",
        }
        log_file.write_text(json.dumps(entry) + "\n")
        findings = validate_pipeline_intent(log_file, session_id="test-session")
        doc_findings = [f for f in findings if f.finding_type == "doc_verdict_missing"]
        assert len(doc_findings) == 1
        assert "[DOC-VERDICT-MISSING]" in doc_findings[0].description


class TestDetectBatchCiaSkip:
    """Tests for detect_batch_cia_skip function (Issue #559)."""

    def _make_batch_event(
        self,
        subagent_type: str,
        issue_number: int,
        timestamp: str = "2026-03-25T10:00:00+00:00",
    ) -> PipelineEvent:
        """Helper to create a batch PipelineEvent with issue number."""
        return PipelineEvent(
            timestamp=timestamp,
            tool="Agent",
            agent="main",
            subagent_type=subagent_type,
            pipeline_action="agent_invocation",
            prompt_word_count=500,
            result_word_count=2000,
            success=True,
            batch_issue_number=issue_number,
        )

    def test_no_batch_events_returns_empty(self):
        """No batch events (batch_issue_number=0) should return no findings."""
        events = [
            _make_event(subagent_type="implementer"),
            _make_event(subagent_type="reviewer"),
        ]
        findings = detect_batch_cia_skip(events)
        assert findings == [], "#559: non-batch events should return empty"

    def test_all_issues_have_cia_returns_empty(self):
        """All batch issues with CIA invoked should return no findings."""
        events = [
            self._make_batch_event("implementer", 100, "2026-03-25T10:00:00+00:00"),
            self._make_batch_event("continuous-improvement-analyst", 100, "2026-03-25T10:05:00+00:00"),
            self._make_batch_event("implementer", 200, "2026-03-25T10:10:00+00:00"),
            self._make_batch_event("continuous-improvement-analyst", 200, "2026-03-25T10:15:00+00:00"),
        ]
        findings = detect_batch_cia_skip(events)
        assert findings == [], "#559: all issues have CIA, no findings"

    def test_last_issue_missing_cia_flagged(self):
        """Last issue missing CIA should be flagged as WARNING with batch_last_issue_cia_skip."""
        events = [
            self._make_batch_event("implementer", 100, "2026-03-25T10:00:00+00:00"),
            self._make_batch_event("continuous-improvement-analyst", 100, "2026-03-25T10:05:00+00:00"),
            self._make_batch_event("implementer", 200, "2026-03-25T10:10:00+00:00"),
            self._make_batch_event("reviewer", 200, "2026-03-25T10:15:00+00:00"),
            # Issue 200 has no CIA
        ]
        findings = detect_batch_cia_skip(events)
        assert len(findings) == 1, "#559: last issue missing CIA should produce one finding"
        assert findings[0].severity == "WARNING"
        assert findings[0].pattern_id == "batch_last_issue_cia_skip"
        assert "200" in findings[0].description
        assert "LAST ISSUE" in findings[0].description

    def test_middle_issue_missing_cia_flagged(self):
        """Non-last issue missing CIA should be flagged as INFO with batch_issue_cia_skip."""
        events = [
            self._make_batch_event("implementer", 100, "2026-03-25T10:00:00+00:00"),
            # Issue 100 has no CIA
            self._make_batch_event("implementer", 200, "2026-03-25T10:10:00+00:00"),
            self._make_batch_event("continuous-improvement-analyst", 200, "2026-03-25T10:15:00+00:00"),
        ]
        findings = detect_batch_cia_skip(events)
        assert len(findings) == 1, "#559: middle issue missing CIA should produce one finding"
        assert findings[0].severity == "INFO"
        assert findings[0].pattern_id == "batch_issue_cia_skip"
        assert "100" in findings[0].description

    def test_single_issue_batch_missing_cia(self):
        """Single-issue batch missing CIA should flag as WARNING (it is both first and last)."""
        events = [
            self._make_batch_event("implementer", 42, "2026-03-25T10:00:00+00:00"),
            self._make_batch_event("reviewer", 42, "2026-03-25T10:05:00+00:00"),
        ]
        findings = detect_batch_cia_skip(events)
        assert len(findings) == 1, "#559: single issue batch missing CIA"
        assert findings[0].severity == "WARNING"
        assert findings[0].pattern_id == "batch_last_issue_cia_skip"
        assert "42" in findings[0].description


class TestCorrelateInvocationCompletion:
    """Tests for _correlate_invocation_completion helper (Issue #562)."""

    def test_pairs_invocation_with_completion(self):
        """Basic pairing: invocation + completion of same type."""
        events = [
            _make_event(
                subagent_type="doc-master",
                tool="Agent",
                pipeline_action="agent_invocation",
                timestamp="2026-03-22T10:00:00+00:00",
            ),
            PipelineEvent(
                timestamp="2026-03-22T10:02:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="doc-master",
                pipeline_action="agent_completion",
                result_word_count=200,
                success=True,
            ),
        ]
        pairs = _correlate_invocation_completion(events)
        assert len(pairs) == 1
        inv, comp = pairs[0]
        assert inv.pipeline_action == "agent_invocation"
        assert comp is not None
        assert comp.pipeline_action == "agent_completion"
        assert comp.result_word_count == 200

    def test_unmatched_invocation_returns_none(self):
        """Invocation with no matching completion returns (inv, None)."""
        events = [
            _make_event(
                subagent_type="doc-master",
                tool="Agent",
                pipeline_action="agent_invocation",
                timestamp="2026-03-22T10:00:00+00:00",
            ),
        ]
        pairs = _correlate_invocation_completion(events)
        assert len(pairs) == 1
        inv, comp = pairs[0]
        assert inv.subagent_type == "doc-master"
        assert comp is None

    def test_multiple_agents_paired_correctly(self):
        """Multiple agent types are paired independently."""
        events = [
            _make_event(
                subagent_type="reviewer",
                tool="Agent",
                pipeline_action="agent_invocation",
                timestamp="2026-03-22T10:00:00+00:00",
            ),
            _make_event(
                subagent_type="doc-master",
                tool="Agent",
                pipeline_action="agent_invocation",
                timestamp="2026-03-22T10:00:01+00:00",
            ),
            PipelineEvent(
                timestamp="2026-03-22T10:02:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="reviewer",
                pipeline_action="agent_completion",
                result_word_count=300,
                success=True,
            ),
            PipelineEvent(
                timestamp="2026-03-22T10:03:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="doc-master",
                pipeline_action="agent_completion",
                result_word_count=200,
                success=True,
            ),
        ]
        pairs = _correlate_invocation_completion(events)
        assert len(pairs) == 2
        reviewer_pairs = [(i, c) for i, c in pairs if i.subagent_type == "reviewer"]
        doc_pairs = [(i, c) for i, c in pairs if i.subagent_type == "doc-master"]
        assert len(reviewer_pairs) == 1
        assert len(doc_pairs) == 1
        assert reviewer_pairs[0][1].result_word_count == 300
        assert doc_pairs[0][1].result_word_count == 200

    def test_completion_before_invocation_not_matched(self):
        """Completion that occurs before invocation should not be matched."""
        events = [
            PipelineEvent(
                timestamp="2026-03-22T09:58:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="doc-master",
                pipeline_action="agent_completion",
                result_word_count=200,
                success=True,
            ),
            _make_event(
                subagent_type="doc-master",
                tool="Agent",
                pipeline_action="agent_invocation",
                timestamp="2026-03-22T10:00:00+00:00",
            ),
        ]
        pairs = _correlate_invocation_completion(events)
        assert len(pairs) == 1
        inv, comp = pairs[0]
        assert comp is None  # The completion was BEFORE the invocation

    def test_multiple_invocations_of_same_type(self):
        """Multiple invocations of same agent type are each paired with distinct completions."""
        events = [
            _make_event(
                subagent_type="doc-master",
                tool="Agent",
                pipeline_action="agent_invocation",
                timestamp="2026-03-22T10:00:00+00:00",
            ),
            PipelineEvent(
                timestamp="2026-03-22T10:02:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="doc-master",
                pipeline_action="agent_completion",
                result_word_count=150,
                success=True,
            ),
            _make_event(
                subagent_type="doc-master",
                tool="Agent",
                pipeline_action="agent_invocation",
                timestamp="2026-03-22T10:05:00+00:00",
            ),
            PipelineEvent(
                timestamp="2026-03-22T10:07:00+00:00",
                tool="Agent",
                agent="main",
                subagent_type="doc-master",
                pipeline_action="agent_completion",
                result_word_count=180,
                success=True,
            ),
        ]
        pairs = _correlate_invocation_completion(events)
        assert len(pairs) == 2
        assert pairs[0][1].result_word_count == 150
        assert pairs[1][1].result_word_count == 180


class TestGetMinimumPromptContent:
    """Tests for get_minimum_prompt_content function (Issue #561)."""

    def test_valid_agent_type_returns_content(self, tmp_path):
        """Valid agent type with existing file returns first 200 words."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        content = " ".join(f"word{i}" for i in range(300))
        (agents_dir / "reviewer.md").write_text(content)
        result = get_minimum_prompt_content("reviewer", agents_dir)
        assert result is not None
        assert len(result.split()) == 200

    def test_invalid_agent_type_returns_none(self, tmp_path):
        """Invalid agent type (not in whitelist) returns None."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        result = get_minimum_prompt_content("../../etc/passwd", agents_dir)
        assert result is None

    def test_unknown_agent_type_returns_none(self, tmp_path):
        """Unknown agent type not in STEP_ORDER returns None."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        result = get_minimum_prompt_content("not-a-real-agent", agents_dir)
        assert result is None

    def test_missing_file_returns_none(self, tmp_path):
        """Valid agent type but missing file returns None."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        result = get_minimum_prompt_content("reviewer", agents_dir)
        assert result is None

    def test_empty_file_returns_none(self, tmp_path):
        """Valid agent type but empty file returns None."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "reviewer.md").write_text("")
        result = get_minimum_prompt_content("reviewer", agents_dir)
        assert result is None

    def test_short_file_returns_all_content(self, tmp_path):
        """File with fewer than 200 words returns all words."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        file_content = "This is a short agent prompt file."
        (agents_dir / "planner.md").write_text(file_content)
        result = get_minimum_prompt_content("planner", agents_dir)
        assert result == file_content

