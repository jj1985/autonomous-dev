"""Unit tests for improve_reviewer.py script.

Tests apply_improvement, check_regression, and revert_reviewer functions.

GitHub Issue: #578
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import pytest

# Add scripts and lib to path
_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
_LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_LIB_DIR))

from improve_reviewer import apply_improvement, check_regression, revert_reviewer


@dataclass
class FakeScoringReport:
    """Minimal ScoringReport stub for testing."""

    balanced_accuracy: float = 0.85
    per_defect_category: Dict[str, Dict[str, Any]] = field(default_factory=dict)


SAMPLE_REVIEWER_MD = """\
---
name: reviewer
description: Code quality gate
---

You are the **reviewer** agent.

## What to Check

1. Code Quality
2. Tests

## Learned Patterns

<!-- Old patterns here -->

## Checkpoint Integration

After completing review, save a checkpoint.
"""

SAMPLE_REVIEWER_NO_LEARNED = """\
---
name: reviewer
description: Code quality gate
---

You are the **reviewer** agent.

## What to Check

1. Code Quality
2. Tests

## Checkpoint Integration

After completing review, save a checkpoint.
"""

SAMPLE_REVIEWER_NO_CHECKPOINT = """\
---
name: reviewer
description: Code quality gate
---

You are the **reviewer** agent.

## What to Check

1. Code Quality
2. Tests
"""


class TestApplyImprovement:
    """Tests for the apply_improvement function."""

    def test_updates_existing_section(self, tmp_path: Path) -> None:
        """Replaces content of existing ## Learned Patterns section."""
        reviewer_path = tmp_path / "reviewer.md"
        reviewer_path.write_text(SAMPLE_REVIEWER_MD)

        instructions = ["Check for error swallowing.", "Verify race conditions."]
        result = apply_improvement(reviewer_path, instructions, content=SAMPLE_REVIEWER_MD)

        assert "## Learned Patterns" in result
        assert "Check for error swallowing." in result
        assert "Verify race conditions." in result
        assert "Old patterns here" not in result
        # Checkpoint section preserved
        assert "## Checkpoint Integration" in result

    def test_adds_section_before_checkpoint(self, tmp_path: Path) -> None:
        """Adds Learned Patterns section before Checkpoint Integration."""
        reviewer_path = tmp_path / "reviewer.md"
        reviewer_path.write_text(SAMPLE_REVIEWER_NO_LEARNED)

        instructions = ["New instruction here."]
        result = apply_improvement(
            reviewer_path, instructions, content=SAMPLE_REVIEWER_NO_LEARNED
        )

        assert "## Learned Patterns" in result
        assert "New instruction here." in result
        # Learned Patterns appears before Checkpoint Integration
        lp_idx = result.index("## Learned Patterns")
        ci_idx = result.index("## Checkpoint Integration")
        assert lp_idx < ci_idx

    def test_adds_section_at_end(self, tmp_path: Path) -> None:
        """Adds Learned Patterns at end if no Checkpoint Integration exists."""
        reviewer_path = tmp_path / "reviewer.md"
        reviewer_path.write_text(SAMPLE_REVIEWER_NO_CHECKPOINT)

        instructions = ["Appended instruction."]
        result = apply_improvement(
            reviewer_path, instructions, content=SAMPLE_REVIEWER_NO_CHECKPOINT
        )

        assert "## Learned Patterns" in result
        assert "Appended instruction." in result

    def test_preserves_frontmatter(self, tmp_path: Path) -> None:
        """YAML frontmatter is preserved after improvement."""
        reviewer_path = tmp_path / "reviewer.md"
        reviewer_path.write_text(SAMPLE_REVIEWER_MD)

        instructions = ["Test instruction."]
        result = apply_improvement(reviewer_path, instructions, content=SAMPLE_REVIEWER_MD)

        assert result.startswith("---\nname: reviewer")

    def test_numbering(self, tmp_path: Path) -> None:
        """Instructions are numbered in the output."""
        reviewer_path = tmp_path / "reviewer.md"
        reviewer_path.write_text(SAMPLE_REVIEWER_MD)

        instructions = ["First.", "Second.", "Third."]
        result = apply_improvement(reviewer_path, instructions, content=SAMPLE_REVIEWER_MD)

        assert "1. First." in result
        assert "2. Second." in result
        assert "3. Third." in result


class TestCheckRegression:
    """Tests for the check_regression function."""

    def test_no_regression(self) -> None:
        """No regression when accuracy stays the same or improves."""
        baseline = FakeScoringReport(
            per_defect_category={
                "cat-a": {"accuracy": 0.80, "total": 5, "correct": 4},
            }
        )
        current = FakeScoringReport(
            per_defect_category={
                "cat-a": {"accuracy": 0.85, "total": 5, "correct": 4},
            }
        )
        regressed, reasons = check_regression(baseline, current)
        assert regressed is False
        assert reasons == []

    def test_regression_detected(self) -> None:
        """Regression when a category drops by more than threshold."""
        baseline = FakeScoringReport(
            per_defect_category={
                "cat-a": {"accuracy": 0.80, "total": 5, "correct": 4},
            }
        )
        current = FakeScoringReport(
            per_defect_category={
                "cat-a": {"accuracy": 0.60, "total": 5, "correct": 3},
            }
        )
        regressed, reasons = check_regression(baseline, current, threshold=0.05)
        assert regressed is True
        assert len(reasons) == 1
        assert "cat-a" in reasons[0]

    def test_small_drop_ok(self) -> None:
        """A drop within threshold is not a regression."""
        baseline = FakeScoringReport(
            per_defect_category={
                "cat-a": {"accuracy": 0.80, "total": 5, "correct": 4},
            }
        )
        current = FakeScoringReport(
            per_defect_category={
                "cat-a": {"accuracy": 0.76, "total": 5, "correct": 3},
            }
        )
        regressed, reasons = check_regression(baseline, current, threshold=0.05)
        assert regressed is False

    def test_ignores_small_categories(self) -> None:
        """Categories with fewer than min_samples are ignored."""
        baseline = FakeScoringReport(
            per_defect_category={
                "cat-a": {"accuracy": 0.80, "total": 2, "correct": 1},
            }
        )
        current = FakeScoringReport(
            per_defect_category={
                "cat-a": {"accuracy": 0.00, "total": 2, "correct": 0},
            }
        )
        regressed, reasons = check_regression(
            baseline, current, threshold=0.05, min_samples=3
        )
        assert regressed is False

    def test_empty_categories(self) -> None:
        """Empty per_defect_category means no regression."""
        baseline = FakeScoringReport(per_defect_category={})
        current = FakeScoringReport(per_defect_category={})
        regressed, reasons = check_regression(baseline, current)
        assert regressed is False


class TestRevertReviewer:
    """Tests for the revert_reviewer function."""

    def test_revert_restores_content(self, tmp_path: Path) -> None:
        """Revert restores the original content."""
        reviewer_path = tmp_path / "reviewer.md"
        original = "# Original Content\n\nSome text here."
        reviewer_path.write_text("# Modified Content\n\nDifferent text.")

        revert_reviewer(reviewer_path, original)

        assert reviewer_path.read_text() == original


class TestDryRunNoChanges:
    """Test that dry-run flow doesn't modify files."""

    def test_apply_improvement_with_content_param(self, tmp_path: Path) -> None:
        """apply_improvement with content= param does not write to disk."""
        reviewer_path = tmp_path / "reviewer.md"
        reviewer_path.write_text(SAMPLE_REVIEWER_MD)

        original_on_disk = reviewer_path.read_text()
        result = apply_improvement(
            reviewer_path,
            ["Dry run instruction."],
            content=SAMPLE_REVIEWER_MD,
        )

        # File on disk unchanged
        assert reviewer_path.read_text() == original_on_disk
        # But returned content has the instruction
        assert "Dry run instruction." in result
