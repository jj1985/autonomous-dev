"""
Spec validation tests for Issue #764: Fix progressive prompt shrinkage in batch mode.

Acceptance criteria:
1. Per-issue baseline isolation works (issue 1 baseline doesn't block issue 2)
2. Within-issue shrinkage is still detected
3. Backward compatibility when PIPELINE_ISSUE_NUMBER is not set
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


class TestSpecIssue764PerIssueBaseline:
    """Spec validation: per-issue baseline isolation for batch mode."""

    def test_spec_764_1_issue2_falls_back_to_lowest_issue_baseline(
        self, tmp_path: Path
    ) -> None:
        """Criterion 1 (updated by Issue #867): When baselines are recorded
        per-issue, looking up the baseline for issue 2 falls back to the
        lowest-issue baseline (issue 1) for cross-issue shrinkage detection.
        This prevents undetected 55% prompt shrinkage across batch issues."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        clear_prompt_baselines(state_dir=state_dir)

        # Record a large baseline for issue 1
        record_prompt_baseline(
            "implementer", issue_number=1, word_count=500, state_dir=state_dir
        )

        # Look up baseline for issue 2 -- should fall back to issue 1's baseline
        baseline_issue2 = get_prompt_baseline(
            "implementer", issue_number=2, state_dir=state_dir
        )
        assert baseline_issue2 == 500, (
            f"Expected fallback to issue 1 baseline (500), got {baseline_issue2}. "
            f"Issue #867: cross-issue shrinkage detection requires fallback."
        )

    def test_spec_764_2_within_issue_shrinkage_detected(
        self, tmp_path: Path
    ) -> None:
        """Criterion 2: Shrinkage within the same issue is still detected.
        Recording a baseline for issue 5 and then validating a much smaller
        prompt against that baseline should fail."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        clear_prompt_baselines(state_dir=state_dir)

        # Record baseline for issue 5
        baseline_wc = 400
        record_prompt_baseline(
            "reviewer", issue_number=5, word_count=baseline_wc, state_dir=state_dir
        )

        # Retrieve the baseline for the same issue
        baseline = get_prompt_baseline(
            "reviewer", issue_number=5, state_dir=state_dir
        )
        assert baseline == baseline_wc, (
            f"Expected baseline {baseline_wc} for issue 5, got {baseline}"
        )

        # Validate a prompt that is 50% smaller -- should be caught
        small_prompt = " ".join(["word"] * 200)
        result = validate_prompt_word_count(
            "reviewer", small_prompt, baseline, max_shrinkage=0.15
        )
        assert result.passed is False, (
            "Expected shrinkage detection within the same issue to fail the check"
        )
        assert result.should_reload is True
        assert result.shrinkage_pct > 40.0

    def test_spec_764_3_backward_compat_no_issue_number(
        self, tmp_path: Path
    ) -> None:
        """Criterion 3: When issue_number is not provided to get_prompt_baseline,
        it falls back to returning the baseline from the lowest-numbered issue
        (backward compatibility with pre-#764 behavior)."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        clear_prompt_baselines(state_dir=state_dir)

        # Record baselines for multiple issues
        record_prompt_baseline(
            "implementer", issue_number=10, word_count=300, state_dir=state_dir
        )
        record_prompt_baseline(
            "implementer", issue_number=3, word_count=450, state_dir=state_dir
        )
        record_prompt_baseline(
            "implementer", issue_number=7, word_count=350, state_dir=state_dir
        )

        # Without issue_number, should return the lowest issue's baseline (issue 3 = 450)
        baseline = get_prompt_baseline("implementer", state_dir=state_dir)
        assert baseline == 450, (
            f"Expected backward-compat baseline of 450 (from lowest issue #3), "
            f"got {baseline}"
        )

    def test_spec_764_4_multiple_agents_isolated_per_issue(
        self, tmp_path: Path
    ) -> None:
        """Criterion 1 extended: Per-issue isolation works across different agents.
        Issue 1's reviewer baseline must not affect issue 2's reviewer lookup."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        clear_prompt_baselines(state_dir=state_dir)

        # Record baselines for issue 1 across two agents
        record_prompt_baseline(
            "reviewer", issue_number=1, word_count=600, state_dir=state_dir
        )
        record_prompt_baseline(
            "implementer", issue_number=1, word_count=500, state_dir=state_dir
        )

        # Issue 2 should fall back to issue 1's baseline (Issue #867: cross-issue detection)
        assert get_prompt_baseline("reviewer", issue_number=2, state_dir=state_dir) == 600
        assert get_prompt_baseline("implementer", issue_number=2, state_dir=state_dir) == 500

        # But issue 1 baselines are still retrievable
        assert get_prompt_baseline("reviewer", issue_number=1, state_dir=state_dir) == 600
        assert get_prompt_baseline("implementer", issue_number=1, state_dir=state_dir) == 500

    def test_spec_764_5_batch_scenario_cross_issue_shrinkage_detected(
        self, tmp_path: Path
    ) -> None:
        """Criterion 1 end-to-end (updated by Issue #867): Simulates a real
        batch scenario where issue 1 has a large prompt and issue 2 has a much
        smaller prompt. With cross-issue fallback, the shrinkage IS detected."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        clear_prompt_baselines(state_dir=state_dir)

        # Issue 1: large implementer prompt, establish baseline
        record_prompt_baseline(
            "implementer", issue_number=1, word_count=800, state_dir=state_dir
        )

        # Issue 2: much smaller prompt (62.5% shrinkage from 800 to 300)
        issue2_prompt = " ".join(["word"] * 300)

        # Per-issue lookup: issue 2 falls back to issue 1's baseline (Issue #867)
        baseline_for_issue2 = get_prompt_baseline(
            "implementer", issue_number=2, state_dir=state_dir
        )
        assert baseline_for_issue2 == 800, (
            f"Expected fallback to issue 1 baseline (800), got {baseline_for_issue2}"
        )

        # With the fallback baseline, the 62.5% shrinkage IS detected
        result = validate_prompt_word_count(
            "implementer", issue2_prompt, baseline_for_issue2, max_shrinkage=0.15
        )
        assert result.passed is False, (
            f"Issue 2's 62.5% prompt shrinkage should be detected via cross-issue fallback. "
            f"Decision: passed={result.passed}, reason={result.reason}"
        )
