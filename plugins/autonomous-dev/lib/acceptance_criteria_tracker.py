"""Acceptance criteria tracker for the /implement pipeline.

Tracks which acceptance criteria have corresponding tests, computing
N/M coverage ratios to surface gaps in the test suite.

Usage:
    from acceptance_criteria_tracker import (
        save_criteria_registry,
        load_criteria_registry,
        compute_criteria_coverage,
    )

    criteria = [
        {"criterion": "User can log in", "scenario_name": "test_user_login", "test_file": "tests/unit/test_auth.py"},
    ]
    save_criteria_registry(criteria, artifact_dir)
    registry = load_criteria_registry(artifact_dir)
    result = compute_criteria_coverage(registry, tests_dir)

Date: 2026-04-06
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

REGISTRY_FILENAME = "acceptance_criteria.json"


@dataclass
class CriteriaCoverageResult:
    """Result of computing acceptance criteria coverage.

    Args:
        total: Total number of acceptance criteria.
        covered: Number of criteria with matching tests.
        uncovered_criteria: List of criterion texts that lack tests.
        coverage_ratio: Fraction covered (0.0 to 1.0).
        has_warning: True when total > 0 but covered == 0.
    """

    total: int
    covered: int
    uncovered_criteria: List[str] = field(default_factory=list)
    coverage_ratio: float = 0.0
    has_warning: bool = False


def save_criteria_registry(
    criteria: List[dict],
    artifact_dir: Path,
) -> Path:
    """Write acceptance criteria registry to JSON file.

    Args:
        criteria: List of dicts, each with keys: criterion, scenario_name, test_file.
        artifact_dir: Directory to write the registry file into.

    Returns:
        Path to the written registry file.

    Raises:
        OSError: If the directory cannot be created or file cannot be written.
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)
    registry_path = artifact_dir / REGISTRY_FILENAME
    registry_path.write_text(json.dumps(criteria, indent=2) + "\n")
    return registry_path


def load_criteria_registry(artifact_dir: Path) -> List[dict]:
    """Read acceptance criteria registry from JSON file.

    Args:
        artifact_dir: Directory containing the registry file.

    Returns:
        List of criterion dicts. Empty list if file is missing or corrupt.
    """
    registry_path = artifact_dir / REGISTRY_FILENAME
    if not registry_path.exists():
        return []

    try:
        data = json.loads(registry_path.read_text())
        if not isinstance(data, list):
            logger.warning(
                "Acceptance criteria registry is not a list: %s", registry_path
            )
            return []
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Could not load acceptance criteria registry from %s: %s",
            registry_path,
            exc,
        )
        return []


def compute_criteria_coverage(
    registry: List[dict],
    tests_dir: Path,
) -> CriteriaCoverageResult:
    """Compute how many acceptance criteria have matching tests.

    For each criterion, checks if its scenario_name appears as a function name
    or its criterion text appears in any test file under tests_dir.

    Args:
        registry: List of criterion dicts from load_criteria_registry.
        tests_dir: Root directory to search for test files.

    Returns:
        CriteriaCoverageResult with coverage metrics.
    """
    total = len(registry)
    if total == 0:
        return CriteriaCoverageResult(total=0, covered=0, coverage_ratio=0.0)

    # Collect all test file contents for matching
    test_contents: dict[Path, str] = {}
    if tests_dir.exists():
        for test_file in tests_dir.rglob("test_*.py"):
            try:
                test_contents[test_file] = test_file.read_text()
            except OSError:
                continue
        # Also match *_test.py pattern
        for test_file in tests_dir.rglob("*_test.py"):
            if test_file not in test_contents:
                try:
                    test_contents[test_file] = test_file.read_text()
                except OSError:
                    continue

    covered = 0
    uncovered: List[str] = []

    for entry in registry:
        scenario_name = entry.get("scenario_name", "")
        criterion_text = entry.get("criterion", "")

        if _is_criterion_covered(scenario_name, criterion_text, test_contents):
            covered += 1
        else:
            uncovered.append(criterion_text)

    coverage_ratio = covered / total if total > 0 else 0.0
    has_warning = total > 0 and covered == 0

    return CriteriaCoverageResult(
        total=total,
        covered=covered,
        uncovered_criteria=uncovered,
        coverage_ratio=round(coverage_ratio, 4),
        has_warning=has_warning,
    )


def _is_criterion_covered(
    scenario_name: str,
    criterion_text: str,
    test_contents: dict[Path, str],
) -> bool:
    """Check if a criterion is covered by any test file.

    Matches either:
    1. scenario_name appears as a function/method name in a test file
    2. criterion_text appears in a test file (e.g., in a docstring or comment)

    Args:
        scenario_name: Expected test function name (e.g., "test_user_login").
        criterion_text: Human-readable criterion description.
        test_contents: Dict mapping test file paths to their contents.

    Returns:
        True if the criterion is covered by at least one test.
    """
    if not test_contents:
        return False

    for content in test_contents.values():
        # Check scenario_name as function name
        if scenario_name and scenario_name in content:
            return True
        # Check criterion text in comments/docstrings
        if criterion_text and criterion_text in content:
            return True

    return False
