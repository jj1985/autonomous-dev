"""Tests for Diamond Model tier registry.

Validates tier classification, lifecycle policies, and cross-checks
against conftest.py auto-marker configuration.
"""

import sys
from pathlib import Path

import pytest

# Ensure tier_registry is importable
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent.parent.parent / "plugins" / "autonomous-dev" / "lib"),
)

from tier_registry import (
    TIER_REGISTRY,
    VALID_LIFECYCLES,
    build_directory_markers,
    get_all_tiers,
    get_tier_distribution,
    get_tier_for_path,
    is_prunable,
)


class TestTierRegistry:
    """Core tier registry tests."""

    def test_all_directories_have_tier(self):
        """Every test directory in the repo maps to a tier."""
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        tests_dir = project_root / "tests"

        # Collect all test subdirectories that contain test files
        test_dirs_with_files = set()
        for test_file in tests_dir.rglob("test_*.py"):
            rel = str(test_file.relative_to(project_root))
            test_dirs_with_files.add(rel)

        # Skip archived, top-level test files, and legacy files directly in
        # tests/regression/ (not in a smoke/regression/extended/progression subdir)
        unmapped = []
        for test_path in test_dirs_with_files:
            if "archived" in test_path:
                continue
            parts = test_path.split("/")
            if len(parts) <= 2:
                # tests/test_foo.py -- top-level, skip
                continue
            # Files directly in tests/regression/ (no subdirectory) are legacy
            if parts[0] == "tests" and parts[1] == "regression" and len(parts) == 3:
                continue
            tier = get_tier_for_path(test_path)
            if tier is None:
                unmapped.append(test_path)

        assert unmapped == [], (
            f"Test files without tier mapping: {unmapped}\n"
            f"Add directory patterns to TIER_REGISTRY in tier_registry.py"
        )

    def test_tier_lifecycle_values(self):
        """All lifecycle values in registry are from the allowed set."""
        for tier in TIER_REGISTRY:
            assert tier.lifecycle in VALID_LIFECYCLES, (
                f"Tier {tier.name} has invalid lifecycle: {tier.lifecycle!r}. "
                f"Allowed: {VALID_LIFECYCLES}"
            )

    def test_get_tier_for_known_paths(self):
        """Known test paths return expected tier IDs."""
        cases = [
            ("tests/unit/lib/test_foo.py", "T3"),
            ("tests/regression/smoke/test_bar.py", "T0"),
            ("tests/integration/test_workflow.py", "T1"),
            ("tests/e2e/test_full.py", "T1"),
            ("tests/regression/regression/test_fix.py", "T2"),
            ("tests/regression/extended/test_deep.py", "T2"),
            ("tests/regression/progression/test_new.py", "T3"),
            ("tests/hooks/test_hook.py", "T3"),
            ("tests/security/test_auth.py", "T3"),
            ("tests/property/test_prop.py", "T2"),
            ("tests/genai/test_congruence.py", "T0"),
        ]
        for path, expected_tier in cases:
            tier = get_tier_for_path(path)
            assert tier is not None, f"No tier found for {path}"
            assert tier.tier_id == expected_tier, (
                f"Path {path}: expected {expected_tier}, got {tier.tier_id}"
            )

    def test_get_tier_for_unknown_path(self):
        """Unknown path returns None."""
        assert get_tier_for_path("some/random/path.py") is None
        assert get_tier_for_path("benchmarks/test_perf.py") is None

    def test_tier_distribution_counts(self):
        """Given a list of paths, distribution counts are correct."""
        paths = [
            "tests/unit/lib/test_a.py",
            "tests/unit/lib/test_b.py",
            "tests/regression/smoke/test_c.py",
            "tests/integration/test_d.py",
            "random/unknown.py",
        ]
        dist = get_tier_distribution(paths)
        assert dist["T3"] == 2  # unit tests
        assert dist["T0"] == 1  # smoke
        assert dist["T1"] == 1  # integration
        assert dist["unknown"] == 1

    def test_is_prunable(self):
        """T3 and T2 are prunable, T0 and T1 are not."""
        # T3 (ephemeral) - prunable
        assert is_prunable("tests/unit/test_foo.py") is True
        assert is_prunable("tests/hooks/test_bar.py") is True

        # T2 (semi-stable) - prunable (conditionally)
        assert is_prunable("tests/regression/regression/test_fix.py") is True
        assert is_prunable("tests/property/test_prop.py") is True

        # T1 (stable) - not prunable
        assert is_prunable("tests/integration/test_wf.py") is False
        assert is_prunable("tests/e2e/test_full.py") is False

        # T0 (permanent) - not prunable
        assert is_prunable("tests/regression/smoke/test_smoke.py") is False
        assert is_prunable("tests/genai/test_judge.py") is False

        # Unknown - not prunable
        assert is_prunable("random/test.py") is False

    def test_registry_matches_conftest_markers(self):
        """Cross-validate that build_directory_markers produces markers
        compatible with conftest DIRECTORY_MARKERS."""
        markers = build_directory_markers()

        # All entries must have non-empty marker lists
        for pattern, marker_list in markers.items():
            assert len(marker_list) > 0, f"Pattern {pattern!r} has no markers"

        # Specific known mappings
        assert "unit/" in markers
        assert "unit" in markers["unit/"]

        assert "hooks/" in markers
        assert "hooks" in markers["hooks/"]
        assert "unit" in markers["hooks/"]

        assert "regression/smoke/" in markers
        assert "smoke" in markers["regression/smoke/"]

        assert "e2e/" in markers
        assert "e2e" in markers["e2e/"]

    def test_get_all_tiers_sorted(self):
        """get_all_tiers returns sorted by tier_id then name."""
        tiers = get_all_tiers()
        assert len(tiers) == len(TIER_REGISTRY)

        # Verify sorted order
        for i in range(len(tiers) - 1):
            key_i = (tiers[i].tier_id, tiers[i].name)
            key_next = (tiers[i + 1].tier_id, tiers[i + 1].name)
            assert key_i <= key_next, (
                f"Not sorted: {key_i} > {key_next}"
            )

    def test_tier_distribution_empty_input(self):
        """Empty input returns empty distribution."""
        assert get_tier_distribution([]) == {}

    def test_windows_path_normalization(self):
        """Windows-style backslash paths are handled."""
        tier = get_tier_for_path("tests\\unit\\test_foo.py")
        assert tier is not None
        assert tier.tier_id == "T3"
