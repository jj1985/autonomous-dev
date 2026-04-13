"""Unit tests for plan_validator.py library.

Tests the plan validation logic including section checking,
plan discovery, and expiry detection.
"""

import time
from pathlib import Path

import pytest

# Add lib to path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib"))

from plan_validator import (
    PLAN_EXPIRY_HOURS,
    REQUIRED_SECTIONS,
    PlanValidationResult,
    find_latest_plan,
    validate_plan,
)


class TestPlanValidationResult:
    """Tests for the PlanValidationResult dataclass."""

    def test_default_values(self):
        result = PlanValidationResult(valid=True)
        assert result.valid is True
        assert result.missing_sections == []
        assert result.plan_path is None
        assert result.age_hours == 0.0
        assert result.expired is False

    def test_invalid_result_with_missing_sections(self):
        result = PlanValidationResult(
            valid=False,
            missing_sections=["## WHY + SCOPE", "## Minimal Path"],
        )
        assert result.valid is False
        assert len(result.missing_sections) == 2


class TestFindLatestPlan:
    """Tests for find_latest_plan function."""

    def test_empty_directory(self, tmp_path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        assert find_latest_plan(plans_dir) is None

    def test_nonexistent_directory(self, tmp_path):
        plans_dir = tmp_path / "nonexistent"
        assert find_latest_plan(plans_dir) is None

    def test_single_plan_file(self, tmp_path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        plan = plans_dir / "feature.md"
        plan.write_text("# Plan")
        assert find_latest_plan(plans_dir) == plan

    def test_multiple_files_returns_newest(self, tmp_path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()

        older = plans_dir / "older.md"
        older.write_text("# Old plan")
        # Force older mtime
        import os
        os.utime(older, (time.time() - 3600, time.time() - 3600))

        newer = plans_dir / "newer.md"
        newer.write_text("# New plan")

        result = find_latest_plan(plans_dir)
        assert result == newer

    def test_non_md_files_ignored(self, tmp_path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        (plans_dir / "notes.txt").write_text("not a plan")
        (plans_dir / "data.json").write_text("{}")
        assert find_latest_plan(plans_dir) is None

    def test_file_not_directory(self, tmp_path):
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.write_text("not a directory")
        assert find_latest_plan(not_a_dir) is None


class TestValidatePlan:
    """Tests for validate_plan function."""

    def _write_valid_plan(self, path: Path) -> None:
        path.write_text(
            "# Plan: Test Feature\n\n"
            "## WHY + SCOPE\n"
            "We need this because reasons.\n\n"
            "## Existing Solutions\n"
            "Searched codebase, nothing found.\n\n"
            "## Minimal Path\n"
            "Create one file, modify another.\n"
        )

    def test_valid_plan_with_all_sections(self, tmp_path):
        plan = tmp_path / "test.md"
        self._write_valid_plan(plan)
        result = validate_plan(plan)
        assert result.valid is True
        assert result.missing_sections == []
        assert result.plan_path == plan

    def test_missing_all_sections(self, tmp_path):
        plan = tmp_path / "empty.md"
        plan.write_text("# Just a title\n\nSome content.\n")
        result = validate_plan(plan)
        assert result.valid is False
        assert len(result.missing_sections) == 3

    def test_missing_existing_solutions(self, tmp_path):
        plan = tmp_path / "partial.md"
        plan.write_text(
            "# Plan\n\n"
            "## WHY + SCOPE\nReasons.\n\n"
            "## Minimal Path\nDo stuff.\n"
        )
        result = validate_plan(plan)
        assert result.valid is False
        assert "## Existing Solutions" in result.missing_sections

    def test_nonexistent_file(self, tmp_path):
        plan = tmp_path / "does_not_exist.md"
        result = validate_plan(plan)
        assert result.valid is False
        assert len(result.missing_sections) == 3

    def test_extra_sections_still_valid(self, tmp_path):
        plan = tmp_path / "extra.md"
        plan.write_text(
            "# Plan\n\n"
            "## WHY + SCOPE\nReasons.\n\n"
            "## Existing Solutions\nNone found.\n\n"
            "## Minimal Path\nSmall change.\n\n"
            "## Extra Section\nBonus content.\n\n"
            "## Another Section\nMore content.\n"
        )
        result = validate_plan(plan)
        assert result.valid is True

    def test_plan_age_calculation(self, tmp_path):
        plan = tmp_path / "aged.md"
        self._write_valid_plan(plan)
        result = validate_plan(plan)
        # Plan was just created, should be very young
        assert result.age_hours < 1.0
        assert result.expired is False

    def test_expired_plan_detection(self, tmp_path):
        plan = tmp_path / "old.md"
        self._write_valid_plan(plan)
        # Set mtime to 73 hours ago
        import os
        old_time = time.time() - (73 * 3600)
        os.utime(plan, (old_time, old_time))
        result = validate_plan(plan)
        assert result.valid is True  # expired plans are still valid
        assert result.expired is True
        assert result.age_hours > 72

    def test_case_insensitive_section_matching(self, tmp_path):
        plan = tmp_path / "case.md"
        plan.write_text(
            "# Plan\n\n"
            "## why + scope\nReasons.\n\n"
            "## existing solutions\nNone found.\n\n"
            "## minimal path\nSmall change.\n"
        )
        result = validate_plan(plan)
        assert result.valid is True

    def test_h3_sections_also_match(self, tmp_path):
        plan = tmp_path / "h3.md"
        plan.write_text(
            "# Plan\n\n"
            "### WHY + SCOPE\nReasons.\n\n"
            "### Existing Solutions\nNone found.\n\n"
            "### Minimal Path\nSmall change.\n"
        )
        result = validate_plan(plan)
        assert result.valid is True

    def test_empty_file(self, tmp_path):
        plan = tmp_path / "empty.md"
        plan.write_text("")
        result = validate_plan(plan)
        assert result.valid is False
        assert len(result.missing_sections) == 3


class TestRequiredSections:
    """Tests for the REQUIRED_SECTIONS constant."""

    def test_has_three_required_sections(self):
        assert len(REQUIRED_SECTIONS) == 3

    def test_contains_why_scope(self):
        assert any("WHY" in s and "SCOPE" in s for s in REQUIRED_SECTIONS)

    def test_contains_existing_solutions(self):
        assert any("Existing Solutions" in s for s in REQUIRED_SECTIONS)

    def test_contains_minimal_path(self):
        assert any("Minimal Path" in s for s in REQUIRED_SECTIONS)
