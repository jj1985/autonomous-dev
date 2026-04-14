"""
Regression tests for Issue #867: Cross-issue prompt shrinkage goes undetected.

Bug: get_prompt_baseline() returns None when looking up a per-issue baseline
that doesn't exist, instead of falling back to the lowest-issue baseline.
This means 55% cross-issue prompt shrinkage in batch mode is invisible.

Fix: When issue_number is provided but no per-issue baseline exists, fall back
to the lowest-issue baseline for cross-issue shrinkage detection.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from prompt_integrity import (
    clear_prompt_baselines,
    get_prompt_baseline,
    record_prompt_baseline,
    validate_prompt_word_count,
)


class TestIssue867CrossIssueBaselineFallback:
    """Regression: cross-issue baseline fallback prevents undetected shrinkage."""

    def test_per_issue_baseline_returned_when_exists(self, tmp_path: Path) -> None:
        """get_prompt_baseline returns the per-issue baseline when it exists."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        clear_prompt_baselines(state_dir=state_dir)

        record_prompt_baseline(
            "implementer", issue_number=5, word_count=400, state_dir=state_dir
        )

        baseline = get_prompt_baseline(
            "implementer", issue_number=5, state_dir=state_dir
        )
        assert baseline == 400

    def test_fallback_to_lowest_issue_when_no_per_issue_baseline(
        self, tmp_path: Path
    ) -> None:
        """get_prompt_baseline falls back to the lowest-issue baseline when
        no per-issue baseline exists. This is the core #867 fix."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        clear_prompt_baselines(state_dir=state_dir)

        # Record baseline for issue 851 (first issue in batch)
        record_prompt_baseline(
            "security-auditor", issue_number=851, word_count=284, state_dir=state_dir
        )

        # Look up baseline for issue 860 (later issue, no own baseline)
        baseline = get_prompt_baseline(
            "security-auditor", issue_number=860, state_dir=state_dir
        )
        assert baseline == 284, (
            f"Expected fallback to issue 851 baseline (284), got {baseline}. "
            f"Without this fallback, cross-issue shrinkage is invisible."
        )

    def test_returns_none_when_no_baselines_exist(self, tmp_path: Path) -> None:
        """get_prompt_baseline returns None when no baselines exist at all."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        clear_prompt_baselines(state_dir=state_dir)

        baseline = get_prompt_baseline(
            "implementer", issue_number=1, state_dir=state_dir
        )
        assert baseline is None

    def test_cross_issue_shrinkage_detected_end_to_end(
        self, tmp_path: Path
    ) -> None:
        """End-to-end: record baseline for issue #1 at 300 words, then
        validate_prompt_word_count for issue #2 at 130 words detects shrinkage."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        clear_prompt_baselines(state_dir=state_dir)

        # Issue 1: establish baseline at 300 words
        record_prompt_baseline(
            "security-auditor", issue_number=1, word_count=300, state_dir=state_dir
        )

        # Issue 2: get fallback baseline (should be 300 from issue 1)
        baseline = get_prompt_baseline(
            "security-auditor", issue_number=2, state_dir=state_dir
        )
        assert baseline == 300

        # Issue 2: validate a 130-word prompt against the 300-word baseline
        # This is ~57% shrinkage -- should be detected
        small_prompt = " ".join(["word"] * 130)
        result = validate_prompt_word_count(
            "security-auditor", small_prompt, baseline, max_shrinkage=0.15
        )
        assert result.passed is False, (
            f"Expected 57% cross-issue shrinkage to be detected, but validation passed. "
            f"shrinkage_pct={result.shrinkage_pct}"
        )
        assert result.shrinkage_pct > 50.0

    def test_fallback_selects_lowest_issue_number(self, tmp_path: Path) -> None:
        """When multiple issues have baselines, fallback uses the lowest-numbered
        issue (the first issue in the batch)."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        clear_prompt_baselines(state_dir=state_dir)

        # Record baselines for issues 10, 3, and 7
        record_prompt_baseline(
            "implementer", issue_number=10, word_count=200, state_dir=state_dir
        )
        record_prompt_baseline(
            "implementer", issue_number=3, word_count=450, state_dir=state_dir
        )
        record_prompt_baseline(
            "implementer", issue_number=7, word_count=350, state_dir=state_dir
        )

        # Issue 99 should fall back to issue 3 (lowest)
        baseline = get_prompt_baseline(
            "implementer", issue_number=99, state_dir=state_dir
        )
        assert baseline == 450, (
            f"Expected fallback to lowest issue #3 baseline (450), got {baseline}"
        )

    def test_per_issue_baseline_preferred_over_fallback(
        self, tmp_path: Path
    ) -> None:
        """When a per-issue baseline exists, it is returned instead of the
        lowest-issue fallback."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        clear_prompt_baselines(state_dir=state_dir)

        record_prompt_baseline(
            "implementer", issue_number=1, word_count=500, state_dir=state_dir
        )
        record_prompt_baseline(
            "implementer", issue_number=2, word_count=300, state_dir=state_dir
        )

        # Issue 2 has its own baseline -- should return 300, not 500
        baseline = get_prompt_baseline(
            "implementer", issue_number=2, state_dir=state_dir
        )
        assert baseline == 300
