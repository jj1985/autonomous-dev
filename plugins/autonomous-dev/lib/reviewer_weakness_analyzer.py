"""Reviewer weakness analysis from benchmark scoring reports.

Identifies weak defect categories, applies failure-mode weights,
and generates improvement instructions for the reviewer agent.

GitHub Issue: #578
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# Failure-mode weights: categories in these groups are penalized more
# when computing priority because they represent harder-to-detect patterns.
MODEL_FAILURE_WEIGHTS: Dict[str, float] = {
    "silent-failure": 1.5,
    "concurrency": 1.4,
    "cross-path-parity": 1.3,
    "security": 1.2,
}


@dataclass
class WeaknessItem:
    """A single identified weakness from benchmark analysis.

    Args:
        category: Defect category name from taxonomy
        accuracy: Accuracy achieved for this category (0.0-1.0)
        sample_count: Total number of samples in this category
        failure_count: Number of incorrect classifications
        group: Taxonomy group the category belongs to
        severity: Severity level (critical/moderate/low)
        sample_ids: List of sample IDs that were misclassified
        suggested_instruction: Generated instruction for the reviewer
    """

    category: str
    accuracy: float
    sample_count: int
    failure_count: int
    group: str
    severity: str
    sample_ids: List[str] = field(default_factory=list)
    suggested_instruction: str = ""


@dataclass
class WeaknessReport:
    """Aggregate weakness report from benchmark analysis.

    Args:
        items: List of weakness items, sorted by priority
        threshold: The accuracy threshold used to identify weaknesses
        timestamp: When the analysis was performed
    """

    items: List[WeaknessItem]
    threshold: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _lookup_group(category: str, taxonomy: Dict[str, Any]) -> str:
    """Look up the taxonomy group for a defect category.

    Args:
        category: Defect category name
        taxonomy: Loaded taxonomy dict

    Returns:
        Group name, or 'unknown' if not found
    """
    categories = taxonomy.get("categories", {})
    if isinstance(categories, dict):
        cat_entry = categories.get(category, {})
        if isinstance(cat_entry, dict):
            return cat_entry.get("group", "unknown")
    return "unknown"


def _lookup_description(category: str, taxonomy: Dict[str, Any]) -> str:
    """Look up the taxonomy description for a defect category.

    Args:
        category: Defect category name
        taxonomy: Loaded taxonomy dict

    Returns:
        Description string, or empty string if not found
    """
    categories = taxonomy.get("categories", {})
    if isinstance(categories, dict):
        cat_entry = categories.get(category, {})
        if isinstance(cat_entry, dict):
            return cat_entry.get("description", "")
    return ""


def _compute_severity(accuracy: float, group: str) -> str:
    """Compute severity based on accuracy and group weight.

    Args:
        accuracy: Category accuracy (0.0-1.0)
        group: Taxonomy group name

    Returns:
        Severity string: 'critical', 'moderate', or 'low'
    """
    weight = MODEL_FAILURE_WEIGHTS.get(group, 1.0)
    weighted_score = accuracy / weight  # Lower = worse

    if weighted_score < 0.30:
        return "critical"
    elif weighted_score < 0.50:
        return "moderate"
    return "low"


def _compute_priority(accuracy: float, group: str, sample_count: int) -> float:
    """Compute priority score for sorting weaknesses.

    Higher priority = worse weakness. Combines accuracy deficit,
    failure-mode weight, and sample count.

    Args:
        accuracy: Category accuracy (0.0-1.0)
        group: Taxonomy group name
        sample_count: Number of samples in category

    Returns:
        Priority score (higher = more urgent)
    """
    weight = MODEL_FAILURE_WEIGHTS.get(group, 1.0)
    deficit = 1.0 - accuracy
    return deficit * weight * min(sample_count, 10)


def analyze_weaknesses(
    report: Any,
    *,
    samples: Optional[List[Any]] = None,
    taxonomy: Optional[Dict[str, Any]] = None,
    threshold: float = 0.70,
    min_samples: int = 3,
) -> WeaknessReport:
    """Analyze a scoring report to identify weak defect categories.

    Filters per_defect_category entries below threshold, looks up taxonomy
    group, applies failure-mode weights to compute priority, and sorts
    by priority descending.

    Args:
        report: A ScoringReport instance with per_defect_category data
        samples: Optional list of BenchmarkSample for sample ID extraction
        taxonomy: Taxonomy dict for group/description lookup
        threshold: Accuracy threshold below which a category is weak (default: 0.70)
        min_samples: Minimum samples required to consider a category (default: 3)

    Returns:
        WeaknessReport with sorted weakness items
    """
    taxonomy = taxonomy or {}
    per_defect = getattr(report, "per_defect_category", {}) or {}

    # Build sample lookup for extracting failed sample IDs
    sample_lookup: Dict[str, List[Any]] = {}
    if samples:
        for s in samples:
            cat = getattr(s, "defect_category", "")
            if cat:
                sample_lookup.setdefault(cat, []).append(s)

    items: List[WeaknessItem] = []
    for category, stats in per_defect.items():
        if not isinstance(stats, dict):
            continue

        total = stats.get("total", 0)
        if total < min_samples:
            continue

        accuracy = stats.get("accuracy", 1.0)
        if accuracy >= threshold:
            continue

        correct = stats.get("correct", 0)
        failure_count = total - correct
        group = _lookup_group(category, taxonomy)
        severity = _compute_severity(accuracy, group)
        description = _lookup_description(category, taxonomy)

        # Extract sample IDs for failed samples
        sample_ids: List[str] = []
        if category in sample_lookup:
            sample_ids = [
                getattr(s, "sample_id", "") for s in sample_lookup[category]
            ]

        # Generate suggested instruction
        suggested = _generate_single_instruction(category, group, description)

        items.append(
            WeaknessItem(
                category=category,
                accuracy=accuracy,
                sample_count=total,
                failure_count=failure_count,
                group=group,
                severity=severity,
                sample_ids=sample_ids,
                suggested_instruction=suggested,
            )
        )

    # Sort by priority (highest first)
    items.sort(
        key=lambda w: _compute_priority(w.accuracy, w.group, w.sample_count),
        reverse=True,
    )

    return WeaknessReport(items=items, threshold=threshold)


def _generate_single_instruction(
    category: str,
    group: str,
    description: str,
) -> str:
    """Generate a single improvement instruction for a weak category.

    Args:
        category: Defect category name
        group: Taxonomy group name
        description: Taxonomy description of the category

    Returns:
        Markdown instruction string
    """
    reason = description if description else f"this is a common {group} defect pattern"
    category_display = category.replace("-", " ").replace("_", " ")

    return (
        f"When reviewing diffs that involve **{category_display}** patterns, "
        f"pay special attention to {group} checks because {reason}."
    )


def generate_improvement_instructions(
    weaknesses: WeaknessReport,
    *,
    max_instructions: int = 3,
) -> List[str]:
    """Generate markdown improvement instructions from a weakness report.

    Takes the top N weaknesses by priority and generates actionable
    instructions for the reviewer agent.

    Args:
        weaknesses: WeaknessReport with sorted items
        max_instructions: Maximum number of instructions to generate (default: 3)

    Returns:
        List of markdown instruction strings
    """
    if not weaknesses.items:
        return []

    instructions: List[str] = []
    for item in weaknesses.items[:max_instructions]:
        instructions.append(item.suggested_instruction)

    return instructions
