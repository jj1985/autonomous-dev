#!/usr/bin/env python3
"""
Unit tests for Pipeline Efficiency Analyzer (Issue #714).

Tests cover all public functions: analyze_efficiency, compute_iqr_outliers,
detect_model_tier_recommendations, detect_token_trends, format_efficiency_report,
and load_full_timing_history integration.
"""

import json
import sys
from pathlib import Path

import pytest

# Portable project root detection
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib"))

from pipeline_efficiency_analyzer import (
    BLOAT_TOKENS_PER_WORD,
    EFFICIENT_TOKENS_PER_WORD,
    MAX_FINDINGS_PER_REPORT,
    MIN_OBSERVATIONS,
    MIN_RUNS_FOR_DOWNGRADE,
    QUALITY_CV_THRESHOLD,
    EfficiencyFinding,
    analyze_efficiency,
    compute_iqr_outliers,
    detect_model_tier_recommendations,
    detect_token_trends,
    format_efficiency_report,
)
from pipeline_timing_analyzer import load_full_timing_history


# ---------------------------------------------------------------------------
# TestLoadFullTimingHistory
# ---------------------------------------------------------------------------


class TestLoadFullTimingHistory:
    """Tests for load_full_timing_history from pipeline_timing_analyzer."""

    def test_valid_jsonl_file(self, tmp_path: Path) -> None:
        """Valid JSONL loads entries grouped by agent_type."""
        history = tmp_path / "history.jsonl"
        history.write_text(
            '{"agent_type": "researcher", "wall_clock_seconds": 60, "total_tokens": 5000, "tool_uses": 3}\n'
            '{"agent_type": "planner", "wall_clock_seconds": 120, "total_tokens": 8000, "tool_uses": 5}\n'
            '{"agent_type": "researcher", "wall_clock_seconds": 70, "total_tokens": 6000, "tool_uses": 4}\n'
        )

        result = load_full_timing_history(history)

        assert "researcher" in result
        assert len(result["researcher"]) == 2
        assert "planner" in result
        assert len(result["planner"]) == 1
        assert result["researcher"][0]["total_tokens"] == 5000

    def test_missing_token_fields_default_to_zero(self, tmp_path: Path) -> None:
        """Entries without total_tokens or tool_uses get default 0."""
        history = tmp_path / "history.jsonl"
        history.write_text(
            '{"agent_type": "researcher", "wall_clock_seconds": 60}\n'
        )

        result = load_full_timing_history(history)

        assert result["researcher"][0]["total_tokens"] == 0
        assert result["researcher"][0]["tool_uses"] == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        """Empty file returns empty dict."""
        history = tmp_path / "history.jsonl"
        history.write_text("")

        result = load_full_timing_history(history)
        assert result == {}

    def test_corrupt_lines_skipped(self, tmp_path: Path) -> None:
        """Corrupt lines are skipped; valid lines are loaded."""
        history = tmp_path / "history.jsonl"
        history.write_text(
            '{"agent_type": "researcher", "wall_clock_seconds": 60}\n'
            "not valid json\n"
            '{"agent_type": "planner", "wall_clock_seconds": 120}\n'
        )

        result = load_full_timing_history(history)
        assert "researcher" in result
        assert "planner" in result

    def test_missing_file(self, tmp_path: Path) -> None:
        """Missing file returns empty dict."""
        result = load_full_timing_history(tmp_path / "nonexistent.jsonl")
        assert result == {}


# ---------------------------------------------------------------------------
# TestComputeIqrOutliers
# ---------------------------------------------------------------------------


class TestComputeIqrOutliers:
    """Tests for compute_iqr_outliers."""

    def test_normal_distribution_with_outlier(self) -> None:
        """Extreme value is detected as outlier."""
        values = [95.0, 100.0, 102.0, 98.0, 101.0, 99.0, 103.0, 97.0, 900.0]
        outliers = compute_iqr_outliers(values)
        assert 900.0 in outliers

    def test_no_outliers_in_tight_data(self) -> None:
        """Tightly clustered data has no outliers."""
        values = [100.0, 101.0, 102.0, 99.0, 100.5, 101.5, 99.5, 100.2]
        outliers = compute_iqr_outliers(values)
        assert len(outliers) == 0

    def test_empty_list(self) -> None:
        """Empty list returns empty outliers."""
        assert compute_iqr_outliers([]) == []

    def test_single_value(self) -> None:
        """Single value returns empty (not enough data)."""
        assert compute_iqr_outliers([42.0]) == []

    def test_all_same_values(self) -> None:
        """All identical values means IQR=0, no outliers."""
        values = [100.0] * 10
        assert compute_iqr_outliers(values) == []

    def test_skewed_distribution(self) -> None:
        """Skewed data still detects extreme outliers."""
        values = [10.0, 12.0, 11.0, 13.0, 14.0, 15.0, 200.0]
        outliers = compute_iqr_outliers(values)
        assert 200.0 in outliers

    def test_three_values_returns_empty(self) -> None:
        """Fewer than 4 values returns empty (insufficient for IQR)."""
        assert compute_iqr_outliers([1.0, 2.0, 100.0]) == []


# ---------------------------------------------------------------------------
# TestAnalyzeEfficiency
# ---------------------------------------------------------------------------


class TestAnalyzeEfficiency:
    """Tests for analyze_efficiency main entry."""

    def test_below_min_observations(self) -> None:
        """Returns empty when agent has fewer than min_observations."""
        observations = [
            {"agent_type": "researcher", "wall_clock_seconds": 100.0, "total_tokens": 5000}
            for _ in range(4)
        ]
        findings = analyze_efficiency(observations)
        assert findings == []

    def test_returns_list(self) -> None:
        """Always returns a list."""
        findings = analyze_efficiency([])
        assert isinstance(findings, list)

    def test_at_threshold_runs(self) -> None:
        """With exactly min_observations, does not crash."""
        observations = [
            {"agent_type": "implementer", "wall_clock_seconds": 600.0, "total_tokens": 200000}
            for _ in range(5)
        ]
        findings = analyze_efficiency(observations)
        assert isinstance(findings, list)

    def test_circuit_breaker_caps_at_five(self) -> None:
        """Never returns more than MAX_FINDINGS_PER_REPORT findings."""
        observations = []
        for agent in ["researcher", "planner", "implementer", "reviewer",
                       "doc-master", "researcher-local", "security-auditor", "test-master"]:
            for _ in range(15):
                observations.append({
                    "agent_type": agent,
                    "wall_clock_seconds": 9999.0,
                    "total_tokens": 999999,
                    "result_word_count": 10,
                    "tool_uses": 100,
                })

        findings = analyze_efficiency(observations)
        assert len(findings) <= MAX_FINDINGS_PER_REPORT

    def test_mixed_agents_some_below_threshold(self) -> None:
        """Only agents with enough observations generate findings."""
        observations = [
            # 3 researcher entries (below threshold)
            {"agent_type": "researcher", "wall_clock_seconds": 60.0, "total_tokens": 5000}
            for _ in range(3)
        ] + [
            # 10 planner entries with bloated tokens (above threshold)
            {"agent_type": "planner", "wall_clock_seconds": 60.0,
             "total_tokens": 100000, "result_word_count": 100}
            for _ in range(10)
        ]

        findings = analyze_efficiency(observations)
        # No findings should be from researcher (only 3 obs)
        researcher_findings = [f for f in findings if f.agent_type == "researcher"]
        assert len(researcher_findings) == 0


# ---------------------------------------------------------------------------
# TestDetectModelTierRecommendations
# ---------------------------------------------------------------------------


class TestDetectModelTierRecommendations:
    """Tests for detect_model_tier_recommendations."""

    def test_stable_low_tokens_recommends_downgrade(self) -> None:
        """Stable quality + low tokens/word suggests downgrade."""
        entries = [
            {"total_tokens": 3000, "result_word_count": 500, "wall_clock_seconds": 60.0}
            for _ in range(12)
        ]
        findings = detect_model_tier_recommendations(entries, "researcher")
        downgrade = [f for f in findings if f.finding_type == "MODEL_DOWNGRADE"]
        assert len(downgrade) == 1
        assert "downgrad" in downgrade[0].recommendation.lower()

    def test_unstable_quality_no_recommendation(self) -> None:
        """Highly variable quality prevents downgrade recommendation."""
        entries = []
        for i in range(12):
            # Wildly varying word counts -> high CV
            entries.append({
                "total_tokens": 3000,
                "result_word_count": 50 if i % 2 == 0 else 2000,
                "wall_clock_seconds": 60.0,
            })
        findings = detect_model_tier_recommendations(entries, "researcher")
        downgrade = [f for f in findings if f.finding_type == "MODEL_DOWNGRADE"]
        assert len(downgrade) == 0

    def test_high_tokens_per_word_bloat_warning(self) -> None:
        """High tokens/word generates PROMPT_BLOAT warning."""
        entries = [
            {"total_tokens": 100000, "result_word_count": 100, "wall_clock_seconds": 60.0}
            for _ in range(12)
        ]
        findings = detect_model_tier_recommendations(entries, "implementer")
        bloat = [f for f in findings if f.finding_type == "PROMPT_BLOAT"]
        assert len(bloat) == 1

    def test_insufficient_runs_no_recommendation(self) -> None:
        """Fewer than MIN_RUNS_FOR_DOWNGRADE returns empty."""
        entries = [
            {"total_tokens": 3000, "result_word_count": 500, "wall_clock_seconds": 60.0}
            for _ in range(8)
        ]
        findings = detect_model_tier_recommendations(entries, "researcher")
        assert findings == []


# ---------------------------------------------------------------------------
# TestDetectTokenTrends
# ---------------------------------------------------------------------------


class TestDetectTokenTrends:
    """Tests for detect_token_trends."""

    def test_rising_trend_detected(self) -> None:
        """Steadily increasing tokens triggers TOKEN_TREND_RISING."""
        entries = [
            {"total_tokens": 1000 + i * 500, "wall_clock_seconds": 60.0}
            for i in range(10)
        ]
        findings = detect_token_trends(entries, "researcher")
        rising = [f for f in findings if f.finding_type == "TOKEN_TREND_RISING"]
        assert len(rising) == 1

    def test_flat_trend_no_finding(self) -> None:
        """Flat token usage generates no trend finding."""
        entries = [
            {"total_tokens": 5000, "wall_clock_seconds": 60.0}
            for _ in range(10)
        ]
        findings = detect_token_trends(entries, "researcher")
        rising = [f for f in findings if f.finding_type == "TOKEN_TREND_RISING"]
        assert len(rising) == 0

    def test_insufficient_data_no_finding(self) -> None:
        """Fewer than MIN_OBSERVATIONS returns empty."""
        entries = [
            {"total_tokens": 5000, "wall_clock_seconds": 60.0}
            for _ in range(3)
        ]
        findings = detect_token_trends(entries, "researcher")
        assert findings == []


# ---------------------------------------------------------------------------
# TestFormatEfficiencyReport
# ---------------------------------------------------------------------------


class TestFormatEfficiencyReport:
    """Tests for format_efficiency_report."""

    def test_empty_findings(self) -> None:
        """Empty findings produces a 'no findings' report."""
        report = format_efficiency_report([])
        assert "No efficiency findings" in report

    def test_report_structure(self) -> None:
        """Report includes header and numbered findings."""
        findings = [
            EfficiencyFinding(
                agent_type="researcher",
                finding_type="PROMPT_BLOAT",
                confidence="high",
                recommendation="Reduce prompt size.",
                evidence={},
            ),
        ]
        report = format_efficiency_report(findings)
        assert "## Pipeline Efficiency Report" in report
        assert "1." in report
        assert "PROMPT_BLOAT" in report
        assert "researcher" in report

    def test_multiple_findings_formatted(self) -> None:
        """Multiple findings are numbered sequentially."""
        findings = [
            EfficiencyFinding(
                agent_type="researcher",
                finding_type="PROMPT_BLOAT",
                confidence="high",
                recommendation="Fix 1.",
            ),
            EfficiencyFinding(
                agent_type="planner",
                finding_type="TOKEN_TREND_RISING",
                confidence="medium",
                recommendation="Fix 2.",
            ),
        ]
        report = format_efficiency_report(findings)
        assert "1." in report
        assert "2." in report
        assert "2 finding(s)" in report
