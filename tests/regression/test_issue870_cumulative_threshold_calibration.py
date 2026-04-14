"""Regression test: Issue #870 — Cumulative prompt drift threshold (15%) fires too aggressively.

Bug: MAX_CUMULATIVE_SHRINKAGE was 0.15 (15%), set in Issue #812 to catch progressive 3-5%
per-iteration compression. But real-world batch variance across issues is 15-25%, causing
the threshold to fire 4 times across a 3-issue batch on benign inter-issue variance.

Fix: Raised MAX_CUMULATIVE_SHRINKAGE from 0.15 to 0.30 (30%). This still catches the 55%
shrinkage case from #867 while stopping false positives on normal 15-25% inter-issue variance.
The per-issue check (20% threshold, cross-issue aware via #867) catches individual issue
compression; the cumulative check catches gradual drift that per-issue checks miss.
"""

import sys
from pathlib import Path

import pytest

# Path depth: tests/regression/ -> parents[2] for project root
REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from prompt_integrity import (
    MAX_CUMULATIVE_SHRINKAGE,
    get_cumulative_shrinkage,
    record_batch_observation,
)


class TestIssue870CumulativeThresholdCalibration:
    """Regression tests for Issue #870: cumulative threshold raised from 15% to 30%."""

    def test_threshold_is_030(self) -> None:
        """MAX_CUMULATIVE_SHRINKAGE must be 0.30 (30%) after Issue #870."""
        assert MAX_CUMULATIVE_SHRINKAGE == 0.30, (
            f"Expected MAX_CUMULATIVE_SHRINKAGE=0.30, got {MAX_CUMULATIVE_SHRINKAGE}. "
            f"Issue #870 raised from 0.15 to 0.30."
        )

    def test_25pct_cumulative_drift_does_not_block(self, tmp_path: Path) -> None:
        """25% cumulative drift must NOT trigger block (was blocked at 15%, passes at 30%).

        This is the core regression: normal inter-issue variance of 15-25% was causing
        false positive blocks with the old 15% threshold.
        """
        # 200->150 = 25.0% cumulative shrinkage
        record_batch_observation("implementer", 1, 200, state_dir=tmp_path)
        record_batch_observation("implementer", 2, 150, state_dir=tmp_path)

        cumulative = get_cumulative_shrinkage("implementer", state_dir=tmp_path)
        assert cumulative is not None
        assert cumulative == 25.0

        # With old 15% threshold, this would be blocked. With 30%, it passes.
        assert cumulative < MAX_CUMULATIVE_SHRINKAGE * 100, (
            f"25% cumulative drift should be < threshold {MAX_CUMULATIVE_SHRINKAGE * 100}%. "
            f"Issue #870 raised threshold to prevent false positives on normal variance."
        )

    def test_35pct_cumulative_drift_triggers_block(self, tmp_path: Path) -> None:
        """35% cumulative drift DOES trigger block (above 30% threshold)."""
        # 200->130 = 35.0% cumulative shrinkage
        record_batch_observation("implementer", 1, 200, state_dir=tmp_path)
        record_batch_observation("implementer", 2, 130, state_dir=tmp_path)

        cumulative = get_cumulative_shrinkage("implementer", state_dir=tmp_path)
        assert cumulative is not None
        assert cumulative == 35.0

        assert cumulative >= MAX_CUMULATIVE_SHRINKAGE * 100, (
            f"35% cumulative drift should be >= threshold {MAX_CUMULATIVE_SHRINKAGE * 100}%"
        )

    def test_55pct_cumulative_drift_triggers_block(self, tmp_path: Path) -> None:
        """55% cumulative drift DOES trigger block (the #867 case, well above 30%)."""
        # 200->90 = 55.0% cumulative shrinkage
        record_batch_observation("reviewer", 1, 200, state_dir=tmp_path)
        record_batch_observation("reviewer", 2, 90, state_dir=tmp_path)

        cumulative = get_cumulative_shrinkage("reviewer", state_dir=tmp_path)
        assert cumulative is not None
        assert cumulative == 55.0

        assert cumulative >= MAX_CUMULATIVE_SHRINKAGE * 100, (
            f"55% cumulative drift should be >= threshold {MAX_CUMULATIVE_SHRINKAGE * 100}%"
        )

    def test_21pct_drift_reported_in_issue_not_blocked(self, tmp_path: Path) -> None:
        """21.7% drift (reported in Issue #870) must NOT block with new 30% threshold.

        This was the first of 4 false-positive blocks reported in the issue.
        """
        # Simulate ~21.7% drift
        record_batch_observation("implementer", 1, 491, state_dir=tmp_path)
        record_batch_observation("implementer", 2, 384, state_dir=tmp_path)

        cumulative = get_cumulative_shrinkage("implementer", state_dir=tmp_path)
        assert cumulative is not None
        # (491 - 384) / 491 * 100 = 21.8% (approximately 21.7%)
        assert 21.0 < cumulative < 22.0, f"Expected ~21.7% drift, got {cumulative}%"

        assert cumulative < MAX_CUMULATIVE_SHRINKAGE * 100, (
            f"21.7% cumulative drift should NOT block with 30% threshold. "
            f"This was a false positive with the old 15% threshold."
        )

    def test_27pct_drift_reported_in_issue_not_blocked(self, tmp_path: Path) -> None:
        """27.6% drift (reported in Issue #870) must NOT block with new 30% threshold.

        This was the second false-positive block reported in the issue.
        """
        # Simulate ~27.6% drift
        record_batch_observation("reviewer", 1, 500, state_dir=tmp_path)
        record_batch_observation("reviewer", 2, 362, state_dir=tmp_path)

        cumulative = get_cumulative_shrinkage("reviewer", state_dir=tmp_path)
        assert cumulative is not None
        # (500 - 362) / 500 * 100 = 27.6%
        assert 27.0 < cumulative < 28.0, f"Expected ~27.6% drift, got {cumulative}%"

        assert cumulative < MAX_CUMULATIVE_SHRINKAGE * 100, (
            f"27.6% cumulative drift should NOT block with 30% threshold."
        )
