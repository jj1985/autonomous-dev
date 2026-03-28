"""Unit tests for reviewer_weakness_analyzer module.

Tests weakness identification, failure-mode weighting, priority sorting,
and improvement instruction generation.

GitHub Issue: #578
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Add lib to path
_LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(_LIB_DIR))

from reviewer_weakness_analyzer import (
    MODEL_FAILURE_WEIGHTS,
    WeaknessItem,
    WeaknessReport,
    analyze_weaknesses,
    generate_improvement_instructions,
)


@dataclass
class FakeScoringReport:
    """Minimal ScoringReport stub for testing."""

    balanced_accuracy: float = 0.85
    per_defect_category: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class FakeSample:
    """Minimal BenchmarkSample stub for testing."""

    sample_id: str = "s1"
    defect_category: str = ""


SAMPLE_TAXONOMY = {
    "categories": {
        "error-swallowed": {
            "group": "silent-failure",
            "description": "An exception is caught and silently discarded.",
        },
        "race-condition": {
            "group": "concurrency",
            "description": "Shared mutable state accessed without synchronization.",
        },
        "hardcoded-value": {
            "group": "functionality",
            "description": "A computed value replaced with a hardcoded literal.",
        },
        "removed-security": {
            "group": "security",
            "description": "A security check silently removed during refactoring.",
        },
        "test-zero-assertions": {
            "group": "testing",
            "description": "A test function contains no assert statements.",
        },
    }
}


class TestAnalyzeWeaknesses:
    """Tests for analyze_weaknesses function."""

    def test_empty_report(self) -> None:
        """Empty per_defect_category produces no weaknesses."""
        report = FakeScoringReport(per_defect_category={})
        result = analyze_weaknesses(report, taxonomy=SAMPLE_TAXONOMY)
        assert len(result.items) == 0

    def test_all_above_threshold(self) -> None:
        """Categories above threshold are not flagged."""
        report = FakeScoringReport(
            per_defect_category={
                "hardcoded-value": {"accuracy": 0.80, "total": 5, "correct": 4},
                "error-swallowed": {"accuracy": 0.75, "total": 4, "correct": 3},
            }
        )
        result = analyze_weaknesses(report, taxonomy=SAMPLE_TAXONOMY, threshold=0.70)
        assert len(result.items) == 0

    def test_identifies_weak_categories(self) -> None:
        """Categories below threshold are identified as weaknesses."""
        report = FakeScoringReport(
            per_defect_category={
                "hardcoded-value": {"accuracy": 0.50, "total": 6, "correct": 3},
                "error-swallowed": {"accuracy": 0.80, "total": 5, "correct": 4},
            }
        )
        result = analyze_weaknesses(report, taxonomy=SAMPLE_TAXONOMY, threshold=0.70)
        assert len(result.items) == 1
        assert result.items[0].category == "hardcoded-value"
        assert result.items[0].accuracy == 0.50

    def test_applies_failure_mode_weights(self) -> None:
        """Silent-failure group has higher priority than functionality."""
        report = FakeScoringReport(
            per_defect_category={
                "hardcoded-value": {"accuracy": 0.50, "total": 5, "correct": 2},
                "error-swallowed": {"accuracy": 0.50, "total": 5, "correct": 2},
            }
        )
        result = analyze_weaknesses(report, taxonomy=SAMPLE_TAXONOMY, threshold=0.70)
        assert len(result.items) == 2
        # error-swallowed (silent-failure, weight 1.5) should be first
        assert result.items[0].category == "error-swallowed"
        assert result.items[0].group == "silent-failure"

    def test_respects_min_samples(self) -> None:
        """Categories with fewer than min_samples are excluded."""
        report = FakeScoringReport(
            per_defect_category={
                "hardcoded-value": {"accuracy": 0.30, "total": 2, "correct": 0},
            }
        )
        result = analyze_weaknesses(
            report, taxonomy=SAMPLE_TAXONOMY, threshold=0.70, min_samples=3
        )
        assert len(result.items) == 0

    def test_threshold_stored_in_report(self) -> None:
        """WeaknessReport stores the threshold used."""
        report = FakeScoringReport(per_defect_category={})
        result = analyze_weaknesses(report, taxonomy=SAMPLE_TAXONOMY, threshold=0.65)
        assert result.threshold == 0.65

    def test_taxonomy_group_lookup(self) -> None:
        """Group is looked up from taxonomy."""
        report = FakeScoringReport(
            per_defect_category={
                "race-condition": {"accuracy": 0.40, "total": 5, "correct": 2},
            }
        )
        result = analyze_weaknesses(report, taxonomy=SAMPLE_TAXONOMY, threshold=0.70)
        assert len(result.items) == 1
        assert result.items[0].group == "concurrency"

    def test_unknown_category_group(self) -> None:
        """Unknown category gets 'unknown' group."""
        report = FakeScoringReport(
            per_defect_category={
                "totally-made-up": {"accuracy": 0.30, "total": 5, "correct": 1},
            }
        )
        result = analyze_weaknesses(report, taxonomy=SAMPLE_TAXONOMY, threshold=0.70)
        assert len(result.items) == 1
        assert result.items[0].group == "unknown"

    def test_weighted_priority_ordering(self) -> None:
        """Items are sorted by weighted priority descending."""
        report = FakeScoringReport(
            per_defect_category={
                "hardcoded-value": {"accuracy": 0.60, "total": 3, "correct": 1},
                "race-condition": {"accuracy": 0.60, "total": 3, "correct": 1},
                "error-swallowed": {"accuracy": 0.60, "total": 3, "correct": 1},
                "removed-security": {"accuracy": 0.60, "total": 3, "correct": 1},
            }
        )
        result = analyze_weaknesses(report, taxonomy=SAMPLE_TAXONOMY, threshold=0.70)
        groups = [item.group for item in result.items]
        # silent-failure (1.5) > concurrency (1.4) > security (1.2) > functionality (1.0)
        assert groups[0] == "silent-failure"
        assert groups[1] == "concurrency"
        assert groups[2] == "security"
        assert groups[3] == "functionality"

    def test_severity_assignment(self) -> None:
        """Severity is assigned based on accuracy and group weight."""
        report = FakeScoringReport(
            per_defect_category={
                "error-swallowed": {"accuracy": 0.10, "total": 5, "correct": 0},
            }
        )
        result = analyze_weaknesses(report, taxonomy=SAMPLE_TAXONOMY, threshold=0.70)
        assert len(result.items) == 1
        # 0.10 / 1.5 = 0.067 < 0.30, so critical
        assert result.items[0].severity == "critical"

    def test_no_taxonomy_still_works(self) -> None:
        """Analysis works without taxonomy (uses 'unknown' group)."""
        report = FakeScoringReport(
            per_defect_category={
                "some-cat": {"accuracy": 0.40, "total": 5, "correct": 2},
            }
        )
        result = analyze_weaknesses(report, taxonomy=None, threshold=0.70)
        assert len(result.items) == 1
        assert result.items[0].group == "unknown"


class TestGenerateImprovementInstructions:
    """Tests for generate_improvement_instructions function."""

    def test_empty_weaknesses(self) -> None:
        """Empty weakness report produces no instructions."""
        report = WeaknessReport(items=[], threshold=0.70)
        instructions = generate_improvement_instructions(report)
        assert instructions == []

    def test_respects_max_instructions(self) -> None:
        """Only top N instructions are generated."""
        items = [
            WeaknessItem(
                category=f"cat-{i}",
                accuracy=0.50,
                sample_count=5,
                failure_count=2,
                group="functionality",
                severity="moderate",
                suggested_instruction=f"Instruction {i}",
            )
            for i in range(5)
        ]
        report = WeaknessReport(items=items, threshold=0.70)
        instructions = generate_improvement_instructions(report, max_instructions=2)
        assert len(instructions) == 2

    def test_content_quality(self) -> None:
        """Generated instructions contain category and group info."""
        items = [
            WeaknessItem(
                category="error-swallowed",
                accuracy=0.40,
                sample_count=5,
                failure_count=3,
                group="silent-failure",
                severity="critical",
                suggested_instruction=(
                    "When reviewing diffs that involve **error swallowed** patterns, "
                    "pay special attention to silent-failure checks because "
                    "An exception is caught and silently discarded."
                ),
            )
        ]
        report = WeaknessReport(items=items, threshold=0.70)
        instructions = generate_improvement_instructions(report, max_instructions=3)
        assert len(instructions) == 1
        assert "error swallowed" in instructions[0]
        assert "silent-failure" in instructions[0]

    def test_max_instructions_cap_with_fewer_items(self) -> None:
        """max_instructions larger than items doesn't error."""
        items = [
            WeaknessItem(
                category="cat-1",
                accuracy=0.50,
                sample_count=5,
                failure_count=2,
                group="functionality",
                severity="moderate",
                suggested_instruction="Instruction 1",
            )
        ]
        report = WeaknessReport(items=items, threshold=0.70)
        instructions = generate_improvement_instructions(report, max_instructions=10)
        assert len(instructions) == 1
