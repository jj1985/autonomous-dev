"""Diamond Model tier registry for test classification.

Single source of truth for mapping test directories to tiers,
lifecycle policies, and pytest markers.

Usage:
    from tier_registry import get_tier_for_path, get_all_tiers, is_prunable

    tier = get_tier_for_path("tests/unit/lib/test_foo.py")
    assert tier.tier_id == "T3"
    assert tier.lifecycle == "ephemeral"

Date: 2026-04-06
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TierInfo:
    """Metadata for a single test tier classification.

    Args:
        tier_id: Tier identifier (T0-T3).
        name: Human-readable tier name.
        directory_pattern: Path substring used for matching test files.
        lifecycle: Retention policy (permanent|stable|semi-stable|ephemeral).
        markers: Pytest markers auto-applied to tests in this directory.
        max_duration: Optional max expected duration per test (e.g. "5s", "30s").
    """

    tier_id: str
    name: str
    directory_pattern: str
    lifecycle: str
    markers: List[str] = field(default_factory=list)
    max_duration: Optional[str] = None


# Ordered from most specific to least specific for matching.
# Order matters: first match wins, so more specific patterns come first.
TIER_REGISTRY: List[TierInfo] = [
    TierInfo(
        tier_id="T0",
        name="GenAI Acceptance",
        directory_pattern="tests/genai/",
        lifecycle="permanent",
        markers=["genai", "acceptance"],
        max_duration=None,
    ),
    TierInfo(
        tier_id="T0",
        name="Smoke",
        directory_pattern="tests/regression/smoke/",
        lifecycle="permanent",
        markers=["smoke"],
        max_duration="5s",
    ),
    TierInfo(
        tier_id="T1",
        name="E2E",
        directory_pattern="tests/e2e/",
        lifecycle="stable",
        markers=["e2e", "slow"],
        max_duration="5min",
    ),
    TierInfo(
        tier_id="T1",
        name="Integration",
        directory_pattern="tests/integration/",
        lifecycle="stable",
        markers=["integration"],
        max_duration="30s",
    ),
    TierInfo(
        tier_id="T2",
        name="Regression",
        directory_pattern="tests/regression/regression/",
        lifecycle="semi-stable",
        markers=["regression"],
        max_duration="30s",
    ),
    TierInfo(
        tier_id="T2",
        name="Extended",
        directory_pattern="tests/regression/extended/",
        lifecycle="semi-stable",
        markers=["extended", "slow"],
        max_duration="5min",
    ),
    TierInfo(
        tier_id="T2",
        name="Property",
        directory_pattern="tests/property/",
        lifecycle="semi-stable",
        markers=["property", "slow"],
        max_duration="5min",
    ),
    TierInfo(
        tier_id="T3",
        name="Progression",
        directory_pattern="tests/regression/progression/",
        lifecycle="ephemeral",
        markers=["progression", "tdd_red"],
        max_duration=None,
    ),
    TierInfo(
        tier_id="T3",
        name="Unit",
        directory_pattern="tests/unit/",
        lifecycle="ephemeral",
        markers=["unit"],
        max_duration="1s",
    ),
    TierInfo(
        tier_id="T3",
        name="Hooks",
        directory_pattern="tests/hooks/",
        lifecycle="ephemeral",
        markers=["hooks", "unit"],
        max_duration="1s",
    ),
    TierInfo(
        tier_id="T3",
        name="Security",
        directory_pattern="tests/security/",
        lifecycle="ephemeral",
        markers=["unit"],
        max_duration="1s",
    ),
]

# Valid lifecycle values
VALID_LIFECYCLES = {"permanent", "stable", "semi-stable", "ephemeral"}


def get_tier_for_path(test_path: str) -> Optional[TierInfo]:
    """Match a test file path against the tier registry.

    Args:
        test_path: Absolute or relative path to a test file.

    Returns:
        TierInfo for the matching tier, or None if no match.
    """
    # Normalize to forward slashes for consistent matching
    normalized = test_path.replace("\\", "/")

    for tier in TIER_REGISTRY:
        if tier.directory_pattern in normalized:
            return tier

    return None


def get_all_tiers() -> List[TierInfo]:
    """Return all tier definitions sorted by tier_id then name.

    Returns:
        Sorted list of TierInfo entries.
    """
    return sorted(TIER_REGISTRY, key=lambda t: (t.tier_id, t.name))


def get_tier_distribution(test_paths: List[str]) -> Dict[str, int]:
    """Count how many test paths fall into each tier.

    Args:
        test_paths: List of test file paths.

    Returns:
        Dict mapping tier_id (e.g. "T0") to count. Paths that don't
        match any tier are counted under "unknown".
    """
    distribution: Dict[str, int] = {}

    for path in test_paths:
        tier = get_tier_for_path(path)
        tier_id = tier.tier_id if tier else "unknown"
        distribution[tier_id] = distribution.get(tier_id, 0) + 1

    return distribution


def is_prunable(test_path: str) -> bool:
    """Check whether a test file can be pruned (deleted).

    T3 (ephemeral) = always prunable.
    T2 (semi-stable) = conditionally prunable (after 90d unused).
    T0 (permanent) and T1 (stable) = never prunable.

    Args:
        test_path: Path to a test file.

    Returns:
        True if the test is prunable (T3 always, T2 conditionally).
        False for T0, T1, or unknown paths.
    """
    tier = get_tier_for_path(test_path)
    if tier is None:
        return False

    return tier.lifecycle in ("ephemeral", "semi-stable")


def build_directory_markers() -> Dict[str, List[str]]:
    """Build a DIRECTORY_MARKERS dict compatible with conftest.py.

    Converts TIER_REGISTRY entries into the format expected by
    pytest_collection_modifyitems: {pattern_suffix: [markers]}.

    Returns:
        Dict mapping directory pattern suffixes to marker lists.
    """
    markers: Dict[str, List[str]] = {}
    for tier in TIER_REGISTRY:
        # Strip "tests/" prefix to match conftest.py convention
        pattern = tier.directory_pattern
        if pattern.startswith("tests/"):
            pattern = pattern[len("tests/"):]
        markers[pattern] = list(tier.markers)
    return markers
