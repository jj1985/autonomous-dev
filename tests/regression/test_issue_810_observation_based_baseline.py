"""Regression test: Issue #810 — observation-based baseline seeding.

seed_baselines_from_templates() was seeding baselines at 0.70x template word count
(477-1877 words), but actual task-specific prompts are 200-600 words. This caused a
systematic 25-50% false positive block rate in batch mode.

Fix: seed_baselines_from_templates() is now a no-op (returns {}). The hook's else-branch
seeds from the first observed prompt for each agent per issue, which is the correct path.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_lib_path = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
if str(_lib_path) not in sys.path:
    sys.path.insert(0, str(_lib_path))

from prompt_integrity import (
    MIN_CRITICAL_AGENT_PROMPT_WORDS,
    clear_prompt_baselines,
    get_prompt_baseline,
    record_prompt_baseline,
    seed_baselines_from_templates,
    validate_prompt_word_count,
)


class TestIssue810ObservationBasedBaseline:
    """Regression tests for Issue #810: observation-based baseline seeding."""

    def test_seed_baselines_from_templates_is_noop(self, tmp_path: Path) -> None:
        """seed_baselines_from_templates() returns {} and writes no baselines.

        Before the fix: function seeded baselines at 0.70x template word count,
        producing ~700-1750 word baselines that blocked legitimate 200-600 word prompts.
        After the fix: function is a no-op, observation-based path handles seeding.
        """
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "reviewer.md").write_text(" ".join(["word"] * 1000))
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        result = seed_baselines_from_templates(agents_dir=agents_dir, state_dir=state_dir)

        assert result == {}, f"Expected empty dict, got {result}"
        assert get_prompt_baseline("reviewer", state_dir=state_dir) is None

    def test_first_observation_becomes_baseline(self, tmp_path: Path) -> None:
        """Recording the first prompt for an agent sets the baseline.

        After clear_prompt_baselines(), no baseline exists. When the hook records
        the first observation for issue #100, it becomes the baseline.
        """
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        clear_prompt_baselines(state_dir=state_dir)
        assert get_prompt_baseline("implementer", state_dir=state_dir) is None

        # First observation for issue #100
        record_prompt_baseline("implementer", issue_number=100, word_count=300, state_dir=state_dir)
        baseline = get_prompt_baseline("implementer", state_dir=state_dir)
        assert baseline == 300

        # Second observation for issue #101 — baseline stays at 300 (lowest issue wins)
        record_prompt_baseline("implementer", issue_number=101, word_count=290, state_dir=state_dir)
        baseline_after = get_prompt_baseline("implementer", state_dir=state_dir)
        assert baseline_after == 300

    def test_batch_mode_no_template_preemption(self, tmp_path: Path) -> None:
        """After clear_prompt_baselines(), baseline is None; first observation seeds correctly.

        This is the core regression: template seeding pre-empted the observation-based path.
        After the fix, clear_prompt_baselines() leaves no baseline, and the first real
        prompt becomes the baseline — not an inflated template-derived value.
        """
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        clear_prompt_baselines(state_dir=state_dir)
        assert get_prompt_baseline("reviewer", state_dir=state_dir) is None

        # First real prompt is 280 words — this should become the baseline
        observed_words = 280
        record_prompt_baseline("reviewer", issue_number=1, word_count=observed_words, state_dir=state_dir)
        baseline = get_prompt_baseline("reviewer", state_dir=state_dir)

        assert baseline == observed_words, (
            f"Expected baseline of {observed_words} (first observation) but got {baseline}. "
            f"Template-seeded value would have been ~700+ words."
        )

    def test_genuine_shrinkage_still_caught(self, tmp_path: Path) -> None:
        """A 50%+ drop from the first observation triggers a block.

        The fix removes false positives but must not remove true positives.
        A genuine compression from 300 words to 140 words (>53% drop) must still fail.
        """
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Establish observation-based baseline at 300 words
        record_prompt_baseline("reviewer", issue_number=1, word_count=300, state_dir=state_dir)
        baseline = get_prompt_baseline("reviewer", state_dir=state_dir)

        # Compressed prompt: 140 words (~53% shrinkage from 300-word baseline)
        compressed_prompt = " ".join(["word"] * 140)
        result = validate_prompt_word_count("reviewer", compressed_prompt, baseline, max_shrinkage=0.25)

        assert result.passed is False, (
            f"Expected genuine shrinkage to be blocked but result.passed={result.passed}. "
            f"Shrinkage was {result.shrinkage_pct:.1f}%."
        )
        assert result.should_reload is True
        assert result.shrinkage_pct > 50.0

    def test_absolute_floor_still_enforced(self, tmp_path: Path) -> None:
        """A 50-word prompt for a critical agent is blocked regardless of baseline state.

        The absolute floor (MIN_CRITICAL_AGENT_PROMPT_WORDS) is independent of baseline
        seeding strategy. It must still block dangerously short prompts.
        """
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # No baseline — purely testing the absolute floor
        prompt = " ".join(["word"] * 50)
        result = validate_prompt_word_count("security-auditor", prompt)

        assert result.passed is False
        assert result.should_reload is True
        assert "minimum" in result.reason.lower()

    def test_cumulative_drift_still_tracked(self, tmp_path: Path) -> None:
        """Multiple observations with gradual shrinkage accumulate correctly.

        Baseline is established at issue #1 (300 words). Subsequent shrinkage
        below threshold individually but checked against the original baseline
        must still be caught when it exceeds the threshold.
        """
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Issue 1: baseline established at 300 words
        record_prompt_baseline("implementer", issue_number=1, word_count=300, state_dir=state_dir)
        baseline = get_prompt_baseline("implementer", state_dir=state_dir)
        assert baseline == 300

        # Issue 2: 270 words — 10% shrinkage, passes
        prompt_2 = " ".join(["word"] * 270)
        result_2 = validate_prompt_word_count("implementer", prompt_2, baseline)
        assert result_2.passed is True
        assert result_2.shrinkage_pct == pytest.approx(10.0, abs=0.1)

        # Issue 5: 200 words — 33% shrinkage from 300-word baseline, fails
        prompt_5 = " ".join(["word"] * 200)
        result_5 = validate_prompt_word_count("implementer", prompt_5, baseline, max_shrinkage=0.25)
        assert result_5.passed is False
        assert result_5.shrinkage_pct > 25.0
