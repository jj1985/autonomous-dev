#!/usr/bin/env python3
"""
Smoke regression tests for ghost/absent agent output detection.

Issue #793: Zero-word agent completions silently succeed without validation.
Issue #792: doc-master produces no completions in batch mode.

These tests validate the core detection paths are wired and functional.
"""

import sys
from pathlib import Path

import pytest

# tests/regression/smoke/ -> tests/regression/ -> tests/ -> repo root
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

from agent_output_health import (
    AgentHealthVerdict,
    check_agent_output_health,
    detect_zero_word_completions,
    generate_batch_health_summary,
)
from pipeline_intent_validator import PipelineEvent


def _make_completion(
    subagent_type: str = "implementer",
    result_word_count: int = 200,
    duration_ms: int = 30000,
) -> PipelineEvent:
    """Create a minimal agent_completion PipelineEvent."""
    return PipelineEvent(
        timestamp="2026-04-13T10:00:00+00:00",
        tool="Agent",
        agent="main",
        subagent_type=subagent_type,
        pipeline_action="agent_completion",
        result_word_count=result_word_count,
        duration_ms=duration_ms,
    )


class TestIssue793ZeroWordAgent:
    """Regression: zero-word agent completions must be detected (issue #793)."""

    def test_zero_word_agent_detected_issue_793(self) -> None:
        """Any agent with 0 words triggers CRITICAL finding."""
        events = [_make_completion(result_word_count=0, duration_ms=15000)]
        findings = detect_zero_word_completions(events)

        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"
        assert findings[0].pattern_id == "zero_word_agent_output"


class TestIssue792DocMasterAbsent:
    """Regression: doc-master absent output must be caught (issue #792)."""

    def test_doc_master_absent_output_issue_792(self) -> None:
        """doc-master with 0 words detected by detect_zero_word_completions."""
        events = [_make_completion(subagent_type="doc-master", result_word_count=0)]
        findings = detect_zero_word_completions(events)

        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"
        assert "doc-master" in findings[0].description


class TestGhostCompletionClassification:
    """Ghost completions are correctly classified in health verdicts."""

    def test_ghost_completion_under_5ms_logged(self) -> None:
        """Ghost completion (<5ms, 0 words) has status 'ghost'."""
        events = [_make_completion(result_word_count=0, duration_ms=3)]
        verdicts = check_agent_output_health(events)

        assert len(verdicts) == 1
        assert verdicts[0].status == "ghost"


class TestBatchHealthSummaryStructure:
    """Batch health summary has correct structure and keys."""

    def test_batch_health_summary_includes_agent_stats(self) -> None:
        """Summary dict has all required keys with correct types."""
        events = [
            _make_completion(subagent_type="reviewer", result_word_count=100),
            _make_completion(subagent_type="reviewer", result_word_count=0, duration_ms=3),
        ]
        summary = generate_batch_health_summary(events)

        assert "reviewer" in summary
        stats = summary["reviewer"]
        required_keys = {
            "invocation_count",
            "ghost_count",
            "zero_word_count",
            "avg_word_count",
            "total_word_count",
        }
        assert required_keys == set(stats.keys())
        assert stats["invocation_count"] == 2
        assert stats["ghost_count"] == 1
        assert stats["zero_word_count"] == 1
        assert stats["total_word_count"] == 100
        assert stats["avg_word_count"] == 50.0
