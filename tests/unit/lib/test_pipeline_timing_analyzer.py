#!/usr/bin/env python3
"""
Tests for Pipeline Timing Analyzer Library (Issue #621)

Tests validate pipeline_timing_analyzer.py which detects slow, wasteful,
and ghost agent invocations from pipeline session logs.
"""

import json
import sys
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

from pipeline_intent_validator import PipelineEvent, VALID_AGENT_TYPES
from pipeline_timing_analyzer import (
    ADAPTIVE_P95_MULTIPLIER,
    AgentTiming,
    GHOST_MAX_DURATION,
    GHOST_MAX_WORDS,
    MAX_HISTORY_PER_AGENT,
    STATIC_THRESHOLDS,
    TimingFinding,
    WASTEFUL_MIN_DURATION,
    WASTEFUL_WPS_THRESHOLD,
    analyze_timings,
    check_budget_violation,
    check_consecutive_violations,
    compute_adaptive_thresholds,
    extract_agent_timings,
    format_budget_warning,
    format_issue_body,
    format_timing_report,
    load_time_budgets,
    load_timing_history,
    save_timing_entry,
    _sanitize_markdown,
)


def _make_event(
    subagent_type: str = "researcher",
    pipeline_action: str = "agent_invocation",
    timestamp: str = "2026-03-01T10:00:00+00:00",
    result_word_count: int = 500,
    prompt_word_count: int = 200,
    success: bool = True,
) -> PipelineEvent:
    """Helper to create PipelineEvent for tests."""
    return PipelineEvent(
        timestamp=timestamp,
        tool="Task",
        agent="main",
        subagent_type=subagent_type,
        pipeline_action=pipeline_action,
        prompt_word_count=prompt_word_count,
        result_word_count=result_word_count,
        success=success,
    )


def _make_timing(
    agent_type: str = "researcher",
    wall_clock_seconds: float = 60.0,
    result_word_count: int = 500,
) -> AgentTiming:
    """Helper to create AgentTiming for tests."""
    return AgentTiming(
        agent_type=agent_type,
        wall_clock_seconds=wall_clock_seconds,
        result_word_count=result_word_count,
        invocation_ts="2026-03-01T10:00:00+00:00",
        completion_ts="2026-03-01T10:01:00+00:00",
        step_number=2.0,
    )


# --- extract_agent_timings tests ---


class TestExtractAgentTimings:
    """Tests for extract_agent_timings function."""

    def test_paired_events(self):
        """Normal case: matched invocation + completion produces timing."""
        events = [
            _make_event(
                subagent_type="researcher",
                pipeline_action="agent_invocation",
                timestamp="2026-03-01T10:00:00+00:00",
            ),
            _make_event(
                subagent_type="researcher",
                pipeline_action="agent_completion",
                timestamp="2026-03-01T10:01:30+00:00",
                result_word_count=800,
            ),
        ]
        timings = extract_agent_timings(events)
        assert len(timings) == 1
        assert timings[0].agent_type == "researcher"
        assert timings[0].wall_clock_seconds == 90.0
        assert timings[0].result_word_count == 800

    def test_unpaired_invocation(self):
        """Orphan invocation (no completion) is skipped gracefully."""
        events = [
            _make_event(
                subagent_type="planner",
                pipeline_action="agent_invocation",
                timestamp="2026-03-01T10:00:00+00:00",
            ),
        ]
        timings = extract_agent_timings(events)
        assert len(timings) == 0

    def test_unpaired_completion(self):
        """Orphan completion (no invocation) is skipped gracefully."""
        events = [
            _make_event(
                subagent_type="planner",
                pipeline_action="agent_completion",
                timestamp="2026-03-01T10:00:00+00:00",
            ),
        ]
        timings = extract_agent_timings(events)
        assert len(timings) == 0

    def test_empty_events(self):
        """Empty events list returns empty timings."""
        timings = extract_agent_timings([])
        assert timings == []

    def test_multiple_agents(self):
        """Multiple agents in one session are all paired correctly."""
        events = [
            _make_event(subagent_type="researcher", pipeline_action="agent_invocation",
                        timestamp="2026-03-01T10:00:00+00:00"),
            _make_event(subagent_type="planner", pipeline_action="agent_invocation",
                        timestamp="2026-03-01T10:01:00+00:00"),
            _make_event(subagent_type="implementer", pipeline_action="agent_invocation",
                        timestamp="2026-03-01T10:02:00+00:00"),
            _make_event(subagent_type="researcher", pipeline_action="agent_completion",
                        timestamp="2026-03-01T10:01:30+00:00", result_word_count=400),
            _make_event(subagent_type="planner", pipeline_action="agent_completion",
                        timestamp="2026-03-01T10:03:00+00:00", result_word_count=600),
            _make_event(subagent_type="implementer", pipeline_action="agent_completion",
                        timestamp="2026-03-01T10:09:00+00:00", result_word_count=2000),
        ]
        timings = extract_agent_timings(events)
        assert len(timings) == 3
        types = {t.agent_type for t in timings}
        assert types == {"researcher", "planner", "implementer"}

    def test_wall_clock_from_timestamps_not_duration_ms(self):
        """Verify wall-clock is computed from timestamp deltas, not duration_ms."""
        inv = _make_event(
            subagent_type="reviewer",
            pipeline_action="agent_invocation",
            timestamp="2026-03-01T10:00:00+00:00",
        )
        inv.duration_ms = 999999  # Should be ignored
        comp = _make_event(
            subagent_type="reviewer",
            pipeline_action="agent_completion",
            timestamp="2026-03-01T10:02:00+00:00",
            result_word_count=300,
        )
        comp.duration_ms = 999999  # Should be ignored
        timings = extract_agent_timings([inv, comp])
        assert len(timings) == 1
        assert timings[0].wall_clock_seconds == 120.0  # 2 minutes from timestamps

    def test_unknown_agent_type_skipped(self):
        """Agent types not in VALID_AGENT_TYPES are skipped."""
        events = [
            _make_event(subagent_type="unknown-agent", pipeline_action="agent_invocation",
                        timestamp="2026-03-01T10:00:00+00:00"),
            _make_event(subagent_type="unknown-agent", pipeline_action="agent_completion",
                        timestamp="2026-03-01T10:01:00+00:00"),
        ]
        timings = extract_agent_timings(events)
        assert len(timings) == 0


# --- compute_adaptive_thresholds tests ---


class TestComputeAdaptiveThresholds:
    """Tests for compute_adaptive_thresholds function."""

    def test_sufficient_data(self):
        """With 15+ observations, returns p95 * multiplier."""
        durations = list(range(10, 30))  # 20 values: 10, 11, ..., 29
        history = {"researcher": durations}
        result = compute_adaptive_thresholds(history, min_observations=10)
        assert result["researcher"] is not None
        assert result["researcher"] > 0
        # p95 of 10..29 (20 items): index 19*0.95=18.05 -> index 18 -> value 28
        expected_p95 = sorted(durations)[int(len(durations) * 0.95)]
        assert result["researcher"] == pytest.approx(expected_p95 * ADAPTIVE_P95_MULTIPLIER)

    def test_insufficient_data(self):
        """With fewer than min_observations, returns None."""
        history = {"researcher": [10.0, 20.0, 30.0]}
        result = compute_adaptive_thresholds(history, min_observations=10)
        assert result["researcher"] is None

    def test_empty_history(self):
        """Empty history returns empty dict."""
        result = compute_adaptive_thresholds({})
        assert result == {}


# --- analyze_timings tests ---


class TestAnalyzeTimings:
    """Tests for analyze_timings function."""

    def test_all_ok(self):
        """All agents within thresholds produces no findings."""
        timings = [
            _make_timing(agent_type="researcher", wall_clock_seconds=60, result_word_count=500),
            _make_timing(agent_type="planner", wall_clock_seconds=100, result_word_count=800),
        ]
        findings = analyze_timings(timings)
        assert findings == []

    def test_slow_agent(self):
        """Agent exceeding static threshold produces SLOW finding."""
        timings = [
            _make_timing(agent_type="researcher", wall_clock_seconds=200, result_word_count=5000),
        ]
        findings = analyze_timings(timings)
        assert len(findings) == 1
        assert findings[0].finding_type == "SLOW"
        assert findings[0].agent_type == "researcher"
        assert findings[0].threshold_type == "static"

    def test_wasteful_agent(self):
        """Slow agent with low output produces WASTEFUL finding."""
        timings = [
            _make_timing(agent_type="researcher", wall_clock_seconds=100, result_word_count=50),
        ]
        findings = analyze_timings(timings)
        assert len(findings) == 1
        assert findings[0].finding_type == "WASTEFUL"
        assert findings[0].agent_type == "researcher"

    def test_ghost_agent(self):
        """Very short, low-output agent produces GHOST finding."""
        timings = [
            _make_timing(agent_type="researcher", wall_clock_seconds=5, result_word_count=10),
        ]
        findings = analyze_timings(timings)
        assert len(findings) == 1
        assert findings[0].finding_type == "GHOST"

    def test_adaptive_threshold(self, tmp_path):
        """With sufficient history, adaptive threshold (p95*1.5) is used."""
        history_path = tmp_path / "history.jsonl"
        # Write 15 entries at ~60s each
        with open(history_path, "w") as f:
            for i in range(15):
                f.write(json.dumps({
                    "agent_type": "researcher",
                    "wall_clock_seconds": 55 + i,  # 55-69
                    "result_word_count": 500,
                    "timestamp": f"2026-03-{i+1:02d}T10:00:00+00:00",
                }) + "\n")

        # Agent at 200s should be SLOW with adaptive threshold
        timings = [
            _make_timing(agent_type="researcher", wall_clock_seconds=200, result_word_count=5000),
        ]
        findings = analyze_timings(timings, history_path=history_path)
        assert len(findings) == 1
        assert findings[0].finding_type == "SLOW"
        assert findings[0].threshold_type == "adaptive"

    def test_no_history_file(self, tmp_path):
        """Missing history file falls back to static thresholds."""
        history_path = tmp_path / "nonexistent.jsonl"
        timings = [
            _make_timing(agent_type="researcher", wall_clock_seconds=200, result_word_count=5000),
        ]
        findings = analyze_timings(timings, history_path=history_path)
        assert len(findings) == 1
        assert findings[0].threshold_type == "static"


# --- load/save timing history tests ---


class TestTimingHistory:
    """Tests for load_timing_history and save_timing_entry."""

    def test_load_missing_file(self, tmp_path):
        """Missing file returns empty dict."""
        result = load_timing_history(tmp_path / "nonexistent.jsonl")
        assert result == {}

    def test_load_corrupted_lines(self, tmp_path):
        """Corrupted lines are skipped, valid lines are loaded."""
        history_path = tmp_path / "history.jsonl"
        history_path.write_text(
            '{"agent_type": "researcher", "wall_clock_seconds": 60}\n'
            "this is not json\n"
            '{"agent_type": "planner", "wall_clock_seconds": 120}\n'
        )
        result = load_timing_history(history_path)
        assert "researcher" in result
        assert result["researcher"] == [60.0]
        assert "planner" in result
        assert result["planner"] == [120.0]

    def test_save_creates_file(self, tmp_path):
        """save_timing_entry creates a new file if it doesn't exist."""
        history_path = tmp_path / "new_history.jsonl"
        timings = [_make_timing(agent_type="researcher", wall_clock_seconds=60)]
        save_timing_entry(timings, history_path)
        assert history_path.exists()
        loaded = load_timing_history(history_path)
        assert "researcher" in loaded
        assert len(loaded["researcher"]) == 1

    def test_save_appends(self, tmp_path):
        """save_timing_entry adds to existing history."""
        history_path = tmp_path / "history.jsonl"
        history_path.write_text(
            '{"agent_type": "researcher", "wall_clock_seconds": 60, "result_word_count": 500, "timestamp": "2026-03-01T10:00:00+00:00"}\n'
        )
        timings = [_make_timing(agent_type="researcher", wall_clock_seconds=90)]
        save_timing_entry(timings, history_path)
        loaded = load_timing_history(history_path)
        assert len(loaded["researcher"]) == 2

    def test_save_caps_at_max(self, tmp_path):
        """save_timing_entry keeps only last MAX_HISTORY_PER_AGENT entries per agent."""
        history_path = tmp_path / "history.jsonl"
        # Write MAX_HISTORY_PER_AGENT entries
        with open(history_path, "w") as f:
            for i in range(MAX_HISTORY_PER_AGENT):
                f.write(json.dumps({
                    "agent_type": "researcher",
                    "wall_clock_seconds": float(i + 1),
                    "result_word_count": 500,
                    "timestamp": f"2026-03-01T10:{i:02d}:00+00:00",
                }) + "\n")

        # Add one more
        timings = [_make_timing(agent_type="researcher", wall_clock_seconds=999)]
        save_timing_entry(timings, history_path)

        loaded = load_timing_history(history_path)
        assert len(loaded["researcher"]) == MAX_HISTORY_PER_AGENT
        # The newest entry (999) should be present
        assert 999.0 in loaded["researcher"]
        # The oldest entry (1.0) should have been dropped
        assert 1.0 not in loaded["researcher"]


# --- format tests ---


class TestFormatTimingReport:
    """Tests for format_timing_report."""

    def test_correct_table_structure(self):
        """Report includes Markdown table with correct headers and rows."""
        timings = [
            _make_timing(agent_type="researcher", wall_clock_seconds=60, result_word_count=300),
        ]
        findings = [
            TimingFinding(
                agent_type="researcher",
                finding_type="SLOW",
                actual_seconds=60,
                threshold_seconds=50,
                threshold_type="static",
                recommendation="Too slow.",
            ),
        ]
        report = format_timing_report(timings, findings)
        assert "| Agent |" in report
        assert "| researcher |" in report
        assert "### Findings" in report
        assert "SLOW" in report
        assert "Total pipeline duration" in report


class TestFormatIssueBody:
    """Tests for format_issue_body."""

    def test_sanitized_output(self):
        """CRLF stripped, Markdown escaped within code fences, capped at 2000 chars."""
        finding = TimingFinding(
            agent_type="researcher",
            finding_type="SLOW",
            actual_seconds=200,
            threshold_seconds=120,
            threshold_type="static",
            result_word_count=500,
            recommendation="Investigate\r\nperformance\r\nbottlenecks.",
        )
        body = format_issue_body(finding, "2026-03-01", "session-123")
        assert "\r\n" not in body
        assert "\r" not in body
        assert "researcher" in body
        assert "session-123" in body
        assert len(body) <= 2000

    def test_long_recommendation_capped(self):
        """Very long recommendation text is capped at 2000 chars."""
        finding = TimingFinding(
            agent_type="researcher",
            finding_type="SLOW",
            actual_seconds=200,
            threshold_seconds=120,
            threshold_type="static",
            result_word_count=500,
            recommendation="x" * 3000,
        )
        body = format_issue_body(finding, "2026-03-01", "session-123")
        assert len(body) <= 2000
        assert body.endswith("...")


# --- static thresholds coverage test ---


class TestStaticThresholds:
    """Tests for static threshold coverage."""

    def test_thresholds_cover_all_agents(self):
        """All VALID_AGENT_TYPES have static thresholds defined."""
        for agent_type in VALID_AGENT_TYPES:
            assert agent_type in STATIC_THRESHOLDS, (
                f"Missing static threshold for agent: {agent_type}"
            )


# --- check_consecutive_violations test ---


class TestCheckConsecutiveViolations:
    """Tests for check_consecutive_violations."""

    def test_correct_count(self, tmp_path):
        """Counts consecutive violations from most recent backward."""
        history_path = tmp_path / "history.jsonl"
        # Write: 50, 50, 200, 200, 200 (last 3 exceed threshold of 100)
        with open(history_path, "w") as f:
            for val in [50, 50, 200, 200, 200]:
                f.write(json.dumps({
                    "agent_type": "researcher",
                    "wall_clock_seconds": val,
                    "result_word_count": 500,
                    "timestamp": "2026-03-01T10:00:00+00:00",
                }) + "\n")

        count = check_consecutive_violations("researcher", history_path, 100)
        assert count == 3

    def test_no_history(self, tmp_path):
        """No history file returns 0."""
        count = check_consecutive_violations("researcher", tmp_path / "nope.jsonl", 100)
        assert count == 0

    def test_no_violations(self, tmp_path):
        """All below threshold returns 0."""
        history_path = tmp_path / "history.jsonl"
        with open(history_path, "w") as f:
            for val in [50, 60, 70]:
                f.write(json.dumps({
                    "agent_type": "researcher",
                    "wall_clock_seconds": val,
                    "result_word_count": 500,
                    "timestamp": "2026-03-01T10:00:00+00:00",
                }) + "\n")

        count = check_consecutive_violations("researcher", history_path, 100)
        assert count == 0


# --- sanitize_markdown test ---


class TestSanitizeMarkdown:
    """Tests for _sanitize_markdown helper."""

    def test_strips_crlf(self):
        """CRLF is converted to LF."""
        result = _sanitize_markdown("hello\r\nworld\r\n")
        assert "\r" not in result
        assert "hello\nworld\n" == result

    def test_strips_control_chars(self):
        """Control characters are removed."""
        result = _sanitize_markdown("hello\x00world\x07")
        assert result == "helloworld"

    def test_caps_length(self):
        """Text longer than 2000 chars is truncated with ellipsis."""
        long_text = "a" * 3000
        result = _sanitize_markdown(long_text)
        assert len(result) == 2000
        assert result.endswith("...")


# --- token tracking tests (Issue #704) ---


class TestAgentTimingTokenFields:
    """Tests for token fields on AgentTiming."""

    def test_agent_timing_has_token_fields(self):
        """AgentTiming with token data stores total_tokens and tool_uses."""
        timing = AgentTiming(
            agent_type="researcher",
            wall_clock_seconds=60.0,
            result_word_count=500,
            invocation_ts="2026-03-01T10:00:00+00:00",
            completion_ts="2026-03-01T10:01:00+00:00",
            step_number=2.0,
            total_tokens=25000,
            tool_uses=5,
        )
        assert timing.total_tokens == 25000
        assert timing.tool_uses == 5

    def test_agent_timing_defaults_zero(self):
        """AgentTiming without token data defaults to 0."""
        timing = _make_timing()
        assert timing.total_tokens == 0
        assert timing.tool_uses == 0


class TestFormatTimingReportTokens:
    """Tests for token columns in format_timing_report."""

    def test_format_timing_report_with_tokens(self):
        """Report includes Tokens and Tok/Word columns when token data present."""
        timings = [
            AgentTiming(
                agent_type="researcher",
                wall_clock_seconds=60.0,
                result_word_count=300,
                invocation_ts="2026-03-01T10:00:00+00:00",
                completion_ts="2026-03-01T10:01:00+00:00",
                step_number=2.0,
                total_tokens=15000,
                tool_uses=3,
            ),
        ]
        report = format_timing_report(timings, [])
        assert "Tokens" in report
        assert "Tok/Word" in report
        assert "15000" in report

    def test_format_timing_report_without_tokens(self):
        """Report omits Tokens and Tok/Word columns when no token data."""
        timings = [
            _make_timing(agent_type="researcher", wall_clock_seconds=60, result_word_count=300),
        ]
        report = format_timing_report(timings, [])
        assert "Tokens" not in report
        assert "Tok/Word" not in report


class TestTokenEfficiencyFinding:
    """Tests for TOKEN_EFFICIENCY finding in analyze_timings."""

    def test_token_efficiency_finding(self):
        """High tokens/word ratio produces TOKEN_EFFICIENCY finding."""
        timings = [
            AgentTiming(
                agent_type="researcher",
                wall_clock_seconds=60.0,
                result_word_count=100,
                invocation_ts="2026-03-01T10:00:00+00:00",
                completion_ts="2026-03-01T10:01:00+00:00",
                step_number=2.0,
                total_tokens=60000,  # 600 tokens/word > 500 threshold
                tool_uses=5,
            ),
        ]
        findings = analyze_timings(timings)
        token_findings = [f for f in findings if f.finding_type == "TOKEN_EFFICIENCY"]
        assert len(token_findings) == 1
        assert "smaller model tier" in token_findings[0].recommendation

    def test_token_efficiency_normal(self):
        """Normal tokens/word ratio produces no TOKEN_EFFICIENCY finding."""
        timings = [
            AgentTiming(
                agent_type="researcher",
                wall_clock_seconds=60.0,
                result_word_count=500,
                invocation_ts="2026-03-01T10:00:00+00:00",
                completion_ts="2026-03-01T10:01:00+00:00",
                step_number=2.0,
                total_tokens=25000,  # 50 tokens/word < 500 threshold
                tool_uses=3,
            ),
        ]
        findings = analyze_timings(timings)
        token_findings = [f for f in findings if f.finding_type == "TOKEN_EFFICIENCY"]
        assert len(token_findings) == 0


# ---------------------------------------------------------------------------
# TestTimeBudgets — per-agent time budget functions (Issue #705)
# ---------------------------------------------------------------------------


class TestTimeBudgets:
    """Tests for load_time_budgets, check_budget_violation, format_budget_warning."""

    def test_load_time_budgets_from_config(self, tmp_path: Path) -> None:
        """load_time_budgets loads from a JSON config file when it exists."""
        config = {
            "implementer": {"budget_seconds": 600, "warning_pct": 0.75},
            "planner": {"budget_seconds": 200, "warning_pct": 0.9},
        }
        config_path = tmp_path / "budgets.json"
        config_path.write_text(__import__("json").dumps(config))

        result = load_time_budgets(config_path)

        # Loaded agents from file
        assert "implementer" in result
        assert result["implementer"]["budget_seconds"] == 600.0
        assert result["implementer"]["warning_pct"] == 0.75
        assert "planner" in result
        assert result["planner"]["budget_seconds"] == 200.0

    def test_load_time_budgets_fallback_to_static(self, tmp_path: Path) -> None:
        """load_time_budgets returns STATIC_THRESHOLDS when config file is missing."""
        nonexistent = tmp_path / "no_such_file.json"
        result = load_time_budgets(nonexistent)

        assert isinstance(result, dict)
        assert len(result) > 0
        # Every STATIC_THRESHOLDS key should be in the fallback
        for agent_type in STATIC_THRESHOLDS:
            assert agent_type in result, f"Missing fallback entry for {agent_type}"

    def test_load_time_budgets_invalid_json(self, tmp_path: Path) -> None:
        """load_time_budgets falls back to static on invalid JSON."""
        bad_config = tmp_path / "bad.json"
        bad_config.write_text("{ this is not valid json }")

        result = load_time_budgets(bad_config)

        # Must still return the static fallback
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_check_budget_no_violation(self) -> None:
        """check_budget_violation returns None when duration is well within budget."""
        budgets = {"implementer": {"budget_seconds": 480.0, "warning_pct": 0.8}}
        # 50% of budget — no violation
        result = check_budget_violation("implementer", 240.0, budgets)
        assert result is None

    def test_check_budget_warning_level(self) -> None:
        """check_budget_violation returns warning when >= warning_pct of budget."""
        budgets = {"implementer": {"budget_seconds": 480.0, "warning_pct": 0.8}}
        # 85% of budget — should be "warning"
        result = check_budget_violation("implementer", 408.0, budgets)
        assert result is not None
        assert result["level"] == "warning"
        assert result["agent_type"] == "implementer"
        assert abs(result["pct_used"] - 408.0 / 480.0) < 0.001

    def test_check_budget_exceeded_level(self) -> None:
        """check_budget_violation returns exceeded when duration > budget_seconds."""
        budgets = {"implementer": {"budget_seconds": 480.0, "warning_pct": 0.8}}
        # 110% of budget — should be "exceeded"
        result = check_budget_violation("implementer", 528.0, budgets)
        assert result is not None
        assert result["level"] == "exceeded"
        assert result["budget"] == 480.0
        assert result["duration"] == 528.0

    def test_check_budget_unknown_agent(self) -> None:
        """check_budget_violation returns None for unknown agent types."""
        budgets: dict = {}
        result = check_budget_violation("unknown-agent", 9999.0, budgets)
        assert result is None

    def test_check_budget_zero_duration(self) -> None:
        """check_budget_violation returns None when duration <= 0."""
        budgets = {"implementer": {"budget_seconds": 480.0, "warning_pct": 0.8}}
        assert check_budget_violation("implementer", 0.0, budgets) is None
        assert check_budget_violation("implementer", -1.0, budgets) is None

    def test_format_budget_warning_exceeded(self) -> None:
        """format_budget_warning produces a non-empty string for exceeded violations."""
        violation = {
            "level": "exceeded",
            "agent_type": "implementer",
            "duration": 520.0,
            "budget": 480.0,
            "pct_used": 520.0 / 480.0,
        }
        msg = format_budget_warning(violation)
        assert isinstance(msg, str)
        assert len(msg) > 0
        assert "BUDGET-EXCEEDED" in msg or "exceeded" in msg.lower()
        assert "implementer" in msg
        assert "REQUIRED NEXT ACTION" in msg

    def test_format_budget_warning_soft(self) -> None:
        """format_budget_warning produces a non-empty string for warning-level violations."""
        violation = {
            "level": "warning",
            "agent_type": "planner",
            "duration": 150.0,
            "budget": 180.0,
            "pct_used": 150.0 / 180.0,
        }
        msg = format_budget_warning(violation)
        assert isinstance(msg, str)
        assert len(msg) > 0
        assert "BUDGET-WARNING" in msg or "warning" in msg.lower()
        assert "planner" in msg
        assert "REQUIRED NEXT ACTION" in msg
