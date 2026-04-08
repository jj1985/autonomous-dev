#!/usr/bin/env python3
"""
Pipeline Efficiency Analyzer - Issue #714

Provides data-driven agent optimization recommendations after N pipeline runs.
Analyzes cross-run efficiency trends including model tier recommendations,
token usage trends, and IQR-based outlier detection.

Used by the continuous-improvement-analyst agent (quality check #14).

Usage:
    from pipeline_efficiency_analyzer import analyze_efficiency, format_efficiency_report
    findings = analyze_efficiency(observations)
    print(format_efficiency_report(findings))
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pipeline_timing_analyzer import load_full_timing_history

logger = logging.getLogger(__name__)

# Minimum observations per agent before any analysis runs
MIN_OBSERVATIONS = 5

# Minimum runs required before recommending model tier changes
MIN_RUNS_FOR_DOWNGRADE = 10

# Coefficient of variation threshold for quality stability
QUALITY_CV_THRESHOLD = 0.3

# Maximum findings returned per report (circuit breaker)
MAX_FINDINGS_PER_REPORT = 5

# Tokens-per-word threshold: below this suggests efficient agent (potential downgrade)
EFFICIENT_TOKENS_PER_WORD = 100

# Tokens-per-word threshold: above this suggests prompt bloat
BLOAT_TOKENS_PER_WORD = 500

# R-squared threshold for trend detection
TREND_R_SQUARED_THRESHOLD = 0.5

# Maps agent_type to current model tier for recommendations
AGENT_MODEL_TIERS: dict[str, str] = {
    "researcher-local": "sonnet",
    "researcher": "sonnet",
    "planner": "opus",
    "implementer": "opus",
    "reviewer": "opus",
    "security-auditor": "opus",
    "doc-master": "sonnet",
    "test-master": "opus",
    "continuous-improvement-analyst": "sonnet",
}


@dataclass
class EfficiencyFinding:
    """A single efficiency analysis finding."""

    agent_type: str
    finding_type: str  # MODEL_DOWNGRADE, PROMPT_BLOAT, TOKEN_TREND_RISING, UNDERPERFORMING
    confidence: str  # low, medium, high
    recommendation: str
    evidence: dict = field(default_factory=dict)


def compute_iqr_outliers(values: list[float]) -> list[float]:
    """Compute IQR-based outliers from a list of values.

    Uses the standard interquartile range method:
    - Q1 = 25th percentile, Q3 = 75th percentile
    - IQR = Q3 - Q1
    - Lower fence = Q1 - 1.5 * IQR
    - Upper fence = Q3 + 1.5 * IQR
    - Values outside fences are outliers

    Args:
        values: List of numeric values to analyze.

    Returns:
        List of values that are outliers (outside the IQR fences).
        Returns empty list if fewer than 4 values or all values are identical.
    """
    if len(values) < 4:
        return []

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    # Compute Q1 (25th percentile) and Q3 (75th percentile)
    q1_index = n * 0.25
    q3_index = n * 0.75

    # Linear interpolation for quartiles
    q1_lower = int(q1_index)
    q1_frac = q1_index - q1_lower
    if q1_lower >= n - 1:
        q1 = sorted_vals[-1]
    else:
        q1 = sorted_vals[q1_lower] + q1_frac * (sorted_vals[q1_lower + 1] - sorted_vals[q1_lower])

    q3_lower = int(q3_index)
    q3_frac = q3_index - q3_lower
    if q3_lower >= n - 1:
        q3 = sorted_vals[-1]
    else:
        q3 = sorted_vals[q3_lower] + q3_frac * (sorted_vals[q3_lower + 1] - sorted_vals[q3_lower])

    iqr = q3 - q1

    if iqr == 0:
        return []

    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr

    return [v for v in values if v < lower_fence or v > upper_fence]


def detect_model_tier_recommendations(
    agent_entries: list[dict],
    agent_type: str,
) -> list[EfficiencyFinding]:
    """Detect whether an agent could use a different model tier.

    Recommends downgrade if:
    - Median tokens_per_word < EFFICIENT_TOKENS_PER_WORD
    - Quality is stable (CV of result_word_count < QUALITY_CV_THRESHOLD)
    - At least MIN_RUNS_FOR_DOWNGRADE observations

    Warns of prompt bloat if:
    - Median tokens_per_word > BLOAT_TOKENS_PER_WORD

    Args:
        agent_entries: List of history entry dicts for this agent.
        agent_type: The agent type being analyzed.

    Returns:
        List of EfficiencyFinding for model tier recommendations.
    """
    findings: list[EfficiencyFinding] = []

    if len(agent_entries) < MIN_RUNS_FOR_DOWNGRADE:
        return findings

    # Compute tokens_per_word for entries with both token and word data
    tpw_values: list[float] = []
    word_counts: list[float] = []
    for entry in agent_entries:
        tokens = entry.get("total_tokens", 0)
        words = entry.get("result_word_count", 0)
        if tokens > 0 and words > 0:
            tpw_values.append(tokens / words)
            word_counts.append(float(words))

    if len(tpw_values) < MIN_RUNS_FOR_DOWNGRADE:
        return findings

    median_tpw = statistics.median(tpw_values)

    # Check quality stability via coefficient of variation
    if len(word_counts) >= 2:
        mean_words = statistics.mean(word_counts)
        stdev_words = statistics.stdev(word_counts)
        cv = stdev_words / mean_words if mean_words > 0 else float("inf")
    else:
        cv = float("inf")

    current_tier = AGENT_MODEL_TIERS.get(agent_type, "unknown")

    # Low tokens/word + stable quality = potential downgrade
    if median_tpw < EFFICIENT_TOKENS_PER_WORD and cv < QUALITY_CV_THRESHOLD:
        if current_tier in ("opus", "sonnet"):
            target_tier = "haiku" if current_tier == "sonnet" else "sonnet"
            findings.append(EfficiencyFinding(
                agent_type=agent_type,
                finding_type="MODEL_DOWNGRADE",
                confidence="medium",
                recommendation=(
                    f"{agent_type} has stable quality (CV={cv:.2f}) with efficient "
                    f"token usage (median {median_tpw:.0f} tok/word) over "
                    f"{len(tpw_values)} runs. Consider downgrading from "
                    f"{current_tier} to {target_tier}."
                ),
                evidence={
                    "median_tokens_per_word": round(median_tpw, 1),
                    "quality_cv": round(cv, 3),
                    "current_tier": current_tier,
                    "suggested_tier": target_tier,
                    "run_count": len(tpw_values),
                },
            ))

    # High tokens/word = prompt bloat warning
    if median_tpw > BLOAT_TOKENS_PER_WORD:
        findings.append(EfficiencyFinding(
            agent_type=agent_type,
            finding_type="PROMPT_BLOAT",
            confidence="high",
            recommendation=(
                f"{agent_type} uses a median of {median_tpw:.0f} tokens per output word "
                f"over {len(tpw_values)} runs. This suggests prompt bloat or excessive "
                f"context injection. Review the agent's prompt and skill injections."
            ),
            evidence={
                "median_tokens_per_word": round(median_tpw, 1),
                "run_count": len(tpw_values),
            },
        ))

    return findings


def _simple_linear_regression(
    x: list[float], y: list[float]
) -> tuple[float, float, float]:
    """Compute simple linear regression: y = slope * x + intercept.

    Args:
        x: Independent variable values.
        y: Dependent variable values.

    Returns:
        Tuple of (slope, intercept, r_squared).
    """
    n = len(x)
    if n < 2:
        return 0.0, 0.0, 0.0

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    ss_xx = sum((xi - mean_x) ** 2 for xi in x)
    ss_yy = sum((yi - mean_y) ** 2 for yi in y)
    ss_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))

    if ss_xx == 0 or ss_yy == 0:
        return 0.0, mean_y, 0.0

    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy)

    return slope, intercept, r_squared


def detect_token_trends(
    agent_entries: list[dict],
    agent_type: str,
) -> list[EfficiencyFinding]:
    """Detect rising token usage trends over time using linear regression.

    A rising trend is flagged when:
    - Positive slope in token counts over sequential runs
    - R-squared > TREND_R_SQUARED_THRESHOLD (good fit)

    Args:
        agent_entries: List of history entry dicts for this agent.
        agent_type: The agent type being analyzed.

    Returns:
        List of EfficiencyFinding for token trends.
    """
    findings: list[EfficiencyFinding] = []

    token_values = [
        entry.get("total_tokens", 0) for entry in agent_entries
        if entry.get("total_tokens", 0) > 0
    ]

    if len(token_values) < MIN_OBSERVATIONS:
        return findings

    x = list(range(len(token_values)))
    y = [float(v) for v in token_values]

    slope, _intercept, r_squared = _simple_linear_regression(x, y)

    if slope > 0 and r_squared > TREND_R_SQUARED_THRESHOLD:
        findings.append(EfficiencyFinding(
            agent_type=agent_type,
            finding_type="TOKEN_TREND_RISING",
            confidence="medium" if r_squared > 0.7 else "low",
            recommendation=(
                f"{agent_type} token usage is trending upward (slope={slope:.0f} "
                f"tokens/run, R²={r_squared:.2f}) over {len(token_values)} runs. "
                f"Investigate growing context or prompt drift."
            ),
            evidence={
                "slope": round(slope, 1),
                "r_squared": round(r_squared, 3),
                "run_count": len(token_values),
                "first_tokens": token_values[0],
                "last_tokens": token_values[-1],
            },
        ))

    return findings


def analyze_efficiency(
    observations: list[dict],
    *,
    min_observations: int = MIN_OBSERVATIONS,
) -> list[EfficiencyFinding]:
    """Analyze pipeline efficiency from historical observation data.

    Main entry point. Groups observations by agent_type, runs all analysis
    functions, and returns aggregated findings capped at MAX_FINDINGS_PER_REPORT.

    Args:
        observations: List of entry dicts with keys: agent_type, wall_clock_seconds,
            total_tokens, tool_uses, result_word_count. Can come from
            load_full_timing_history() or be constructed directly.
        min_observations: Minimum observations per agent before analysis runs.

    Returns:
        List of EfficiencyFinding, capped at MAX_FINDINGS_PER_REPORT.
    """
    # Group observations by agent_type
    by_agent: dict[str, list[dict]] = {}
    for obs in observations:
        agent_type = obs.get("agent_type", "")
        if agent_type:
            by_agent.setdefault(agent_type, []).append(obs)

    all_findings: list[EfficiencyFinding] = []

    for agent_type, entries in by_agent.items():
        if len(entries) < min_observations:
            continue

        # Run all analysis functions
        all_findings.extend(detect_model_tier_recommendations(entries, agent_type))
        all_findings.extend(detect_token_trends(entries, agent_type))

        # IQR outlier detection on token usage
        token_values = [
            float(e.get("total_tokens", 0)) for e in entries
            if e.get("total_tokens", 0) > 0
        ]
        if len(token_values) >= 4:
            outliers = compute_iqr_outliers(token_values)
            if outliers:
                all_findings.append(EfficiencyFinding(
                    agent_type=agent_type,
                    finding_type="UNDERPERFORMING",
                    confidence="low",
                    recommendation=(
                        f"{agent_type} has {len(outliers)} token usage outlier(s) "
                        f"detected via IQR analysis. Values: "
                        f"{[round(v) for v in outliers[:3]]}. "
                        f"Investigate these runs for anomalies."
                    ),
                    evidence={
                        "outlier_count": len(outliers),
                        "outlier_values": [round(v) for v in outliers[:5]],
                        "total_observations": len(token_values),
                    },
                ))

        # Circuit breaker: stop early if we hit the cap
        if len(all_findings) >= MAX_FINDINGS_PER_REPORT:
            break

    # Apply circuit breaker cap
    return all_findings[:MAX_FINDINGS_PER_REPORT]


def format_efficiency_report(findings: list[EfficiencyFinding]) -> str:
    """Format efficiency findings as a Markdown report.

    Args:
        findings: List of EfficiencyFinding from analyze_efficiency().

    Returns:
        Markdown-formatted report string.
    """
    lines: list[str] = []
    lines.append("## Pipeline Efficiency Report")
    lines.append("")

    if not findings:
        lines.append("No efficiency findings. All agents operating within normal parameters.")
        return "\n".join(lines)

    lines.append(f"**{len(findings)} finding(s)** detected:")
    lines.append("")

    for i, f in enumerate(findings, 1):
        lines.append(
            f"{i}. **{f.finding_type}** ({f.agent_type}, confidence: {f.confidence}): "
            f"{f.recommendation}"
        )

    lines.append("")
    lines.append("---")
    lines.append("*Advisory only. Review before acting on recommendations.*")

    return "\n".join(lines)
