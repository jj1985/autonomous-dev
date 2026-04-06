"""Tests for acceptance_criteria_tracker module."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib")
)

from acceptance_criteria_tracker import (
    CriteriaCoverageResult,
    compute_criteria_coverage,
    load_criteria_registry,
    save_criteria_registry,
)


class TestSaveAndLoadRegistry:
    """Tests for save_criteria_registry and load_criteria_registry round-trip."""

    def test_save_and_load_registry(self, tmp_path: Path) -> None:
        """Round-trip: save then load returns identical data."""
        criteria = [
            {
                "criterion": "User can log in",
                "scenario_name": "test_user_login",
                "test_file": "tests/unit/test_auth.py",
            },
            {
                "criterion": "User can log out",
                "scenario_name": "test_user_logout",
                "test_file": "tests/unit/test_auth.py",
            },
        ]
        save_criteria_registry(criteria, tmp_path)
        loaded = load_criteria_registry(tmp_path)
        assert loaded == criteria

    def test_load_missing_registry(self, tmp_path: Path) -> None:
        """Missing registry file returns empty list."""
        result = load_criteria_registry(tmp_path)
        assert result == []

    def test_load_corrupt_registry(self, tmp_path: Path) -> None:
        """Corrupt JSON returns empty list and logs warning."""
        registry_path = tmp_path / "acceptance_criteria.json"
        registry_path.write_text("{not valid json!!!")
        result = load_criteria_registry(tmp_path)
        assert result == []

    def test_load_non_list_registry(self, tmp_path: Path) -> None:
        """Registry that is valid JSON but not a list returns empty list."""
        registry_path = tmp_path / "acceptance_criteria.json"
        registry_path.write_text(json.dumps({"not": "a list"}))
        result = load_criteria_registry(tmp_path)
        assert result == []

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """save_criteria_registry creates parent directories as needed."""
        deep_dir = tmp_path / "a" / "b" / "c"
        criteria = [{"criterion": "Test", "scenario_name": "test_x", "test_file": "t.py"}]
        path = save_criteria_registry(criteria, deep_dir)
        assert path.exists()
        assert json.loads(path.read_text()) == criteria


class TestComputeCriteriaCoverage:
    """Tests for compute_criteria_coverage."""

    def _write_test_file(self, tests_dir: Path, filename: str, content: str) -> None:
        """Helper to write a test file."""
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / filename).write_text(content)

    def test_compute_coverage_all_covered(self, tmp_path: Path) -> None:
        """All criteria covered yields N/M = M/M."""
        tests_dir = tmp_path / "tests"
        self._write_test_file(
            tests_dir,
            "test_auth.py",
            "def test_user_login():\n    pass\n\ndef test_user_logout():\n    pass\n",
        )
        registry = [
            {"criterion": "User can log in", "scenario_name": "test_user_login", "test_file": ""},
            {"criterion": "User can log out", "scenario_name": "test_user_logout", "test_file": ""},
        ]
        result = compute_criteria_coverage(registry, tests_dir)
        assert result.total == 2
        assert result.covered == 2
        assert result.uncovered_criteria == []
        assert result.coverage_ratio == 1.0
        assert result.has_warning is False

    def test_compute_coverage_partial(self, tmp_path: Path) -> None:
        """Some criteria uncovered."""
        tests_dir = tmp_path / "tests"
        self._write_test_file(
            tests_dir, "test_auth.py", "def test_user_login():\n    pass\n"
        )
        registry = [
            {"criterion": "User can log in", "scenario_name": "test_user_login", "test_file": ""},
            {"criterion": "User can register", "scenario_name": "test_user_register", "test_file": ""},
        ]
        result = compute_criteria_coverage(registry, tests_dir)
        assert result.total == 2
        assert result.covered == 1
        assert result.uncovered_criteria == ["User can register"]
        assert result.coverage_ratio == 0.5

    def test_compute_coverage_zero_criteria(self, tmp_path: Path) -> None:
        """Empty registry yields zero total, no warning."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        result = compute_criteria_coverage([], tests_dir)
        assert result.total == 0
        assert result.covered == 0
        assert result.coverage_ratio == 0.0
        assert result.has_warning is False

    def test_compute_coverage_zero_tests(self, tmp_path: Path) -> None:
        """Criteria exist but no test files: covered=0, has_warning=True."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        registry = [
            {"criterion": "Feature X works", "scenario_name": "test_feature_x", "test_file": ""},
        ]
        result = compute_criteria_coverage(registry, tests_dir)
        assert result.total == 1
        assert result.covered == 0
        assert result.has_warning is True
        assert result.uncovered_criteria == ["Feature X works"]

    def test_criterion_matching_by_scenario_name(self, tmp_path: Path) -> None:
        """Criterion matched when scenario_name appears as function name in test file."""
        tests_dir = tmp_path / "tests"
        self._write_test_file(
            tests_dir,
            "test_feature.py",
            "class TestFeature:\n    def test_my_scenario(self):\n        assert True\n",
        )
        registry = [
            {"criterion": "My scenario works", "scenario_name": "test_my_scenario", "test_file": ""},
        ]
        result = compute_criteria_coverage(registry, tests_dir)
        assert result.covered == 1

    def test_criterion_matching_by_text(self, tmp_path: Path) -> None:
        """Criterion matched when criterion text appears in comment/docstring."""
        tests_dir = tmp_path / "tests"
        self._write_test_file(
            tests_dir,
            "test_feature.py",
            '"""Tests for User can reset password feature."""\ndef test_something():\n    pass\n',
        )
        registry = [
            {
                "criterion": "User can reset password",
                "scenario_name": "test_nonexistent_function",
                "test_file": "",
            },
        ]
        result = compute_criteria_coverage(registry, tests_dir)
        assert result.covered == 1

    def test_coverage_ratio_computation(self, tmp_path: Path) -> None:
        """Verify float math for coverage ratio."""
        tests_dir = tmp_path / "tests"
        self._write_test_file(
            tests_dir, "test_a.py", "def test_a():\n    pass\n"
        )
        registry = [
            {"criterion": "A", "scenario_name": "test_a", "test_file": ""},
            {"criterion": "B", "scenario_name": "test_b", "test_file": ""},
            {"criterion": "C", "scenario_name": "test_c", "test_file": ""},
        ]
        result = compute_criteria_coverage(registry, tests_dir)
        assert result.total == 3
        assert result.covered == 1
        # 1/3 = 0.3333...
        assert result.coverage_ratio == pytest.approx(0.3333, abs=0.001)

    def test_nonexistent_tests_dir(self, tmp_path: Path) -> None:
        """Tests directory does not exist: all criteria uncovered."""
        tests_dir = tmp_path / "nonexistent"
        registry = [
            {"criterion": "Feature", "scenario_name": "test_feature", "test_file": ""},
        ]
        result = compute_criteria_coverage(registry, tests_dir)
        assert result.total == 1
        assert result.covered == 0
        assert result.has_warning is True
