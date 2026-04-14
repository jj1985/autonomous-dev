"""Regression tests for Issue #812: Implementer prompt progressively compressed 25-27% across batch issues.

Bug: The hook-level max_shrinkage was 0.25 (25%) and the cumulative drift threshold was 0.20 (20%),
both using strict `>` comparisons. A 27.3% shrinkage (491→357 words) passed individual checks, and
the cumulative gate had insufficient sensitivity to catch gradual 3-5% per-iteration compression.

Fix:
- Hook max_shrinkage tightened from 0.25 to 0.20 (Issue #812)
- MAX_CUMULATIVE_SHRINKAGE tightened from 0.20 to 0.15 (Issue #812)
- Both comparisons changed from `>` to `>=` so the boundary is inclusive (block AT threshold, not only above)
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Path depth: tests/regression/ → tests → repo root = parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
HOOK_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(LIB_DIR))
sys.path.insert(0, str(HOOK_DIR))

from prompt_integrity import (
    MAX_CUMULATIVE_SHRINKAGE,
    PromptIntegrityResult,
    clear_batch_observations,
    get_cumulative_shrinkage,
    record_batch_observation,
    validate_prompt_word_count,
)


class TestIssue812PromptShrinkageBoundary:
    """Regression tests for Issue #812: tightened shrinkage thresholds."""

    # -- Per-issue shrinkage tests (validate_prompt_word_count) --

    def test_exactly_20pct_shrinkage_blocked(self) -> None:
        """Exactly 20% shrinkage must FAIL validation (>= boundary, not just >).

        Before fix: `> 0.20 * 100` would allow exactly 20.0%.
        After fix: `>= 0.20 * 100` blocks at exactly 20.0%.
        """
        # 100-word baseline, 80-word current = exactly 20.0% shrinkage
        prompt = " ".join(["word"] * 80)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=100, max_shrinkage=0.20
        )
        assert result.passed is False, (
            f"Exactly 20% shrinkage should be blocked (>= threshold). "
            f"Got passed={result.passed}, shrinkage={result.shrinkage_pct:.1f}%"
        )
        assert result.should_reload is True

    def test_19pct_shrinkage_passes(self) -> None:
        """19% shrinkage is under the 20% hook threshold and must PASS.

        100-word baseline, 81-word current = 19.0% shrinkage.
        """
        prompt = " ".join(["word"] * 81)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=100, max_shrinkage=0.20
        )
        assert result.passed is True, (
            f"19% shrinkage should pass 20% threshold. "
            f"Got passed={result.passed}, shrinkage={result.shrinkage_pct:.1f}%"
        )

    def test_25pct_shrinkage_blocked(self) -> None:
        """25% shrinkage must be blocked by new 20% threshold.

        Before fix: hook used 25% threshold, so 25% would slip through.
        After fix: hook uses 20% threshold, so 25% is clearly blocked.
        """
        # 200-word baseline, 150-word current = 25.0% shrinkage
        prompt = " ".join(["word"] * 150)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=200, max_shrinkage=0.20
        )
        assert result.passed is False, (
            f"25% shrinkage must be blocked by 20% threshold. "
            f"Got passed={result.passed}, shrinkage={result.shrinkage_pct:.1f}%"
        )

    def test_27pct_shrinkage_blocked(self) -> None:
        """27% shrinkage (the reported scenario) must be blocked.

        The issue reported 25-27% shrinkage passing without block.
        After fix with 20% threshold, 27% is clearly blocked.
        """
        # 200-word baseline, 146-word current = 27.0% shrinkage
        prompt = " ".join(["word"] * 146)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=200, max_shrinkage=0.20
        )
        assert result.passed is False, (
            f"27% shrinkage must be blocked by 20% threshold. "
            f"Got passed={result.passed}, shrinkage={result.shrinkage_pct:.1f}%"
        )

    def test_issue_scenario_491_to_357(self) -> None:
        """Exact issue scenario: implementer prompt 491→357 words (27.3% shrinkage) must BLOCK.

        This is the exact word count progression reported in Issue #812.
        With old 25% threshold: allowed (27.3% > 25% only if comparison was strict >).
        With new 20% threshold: clearly blocked (27.3% >= 20%).
        """
        prompt = " ".join(["word"] * 357)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=491, max_shrinkage=0.20
        )
        shrinkage = (1.0 - 357 / 491) * 100
        assert result.passed is False, (
            f"491→357 word scenario ({shrinkage:.1f}% shrinkage) must be blocked. "
            f"Got passed={result.passed}"
        )

    def test_issue_scenario_491_to_367(self) -> None:
        """Exact issue scenario: implementer prompt 491→367 words (25.3% shrinkage) must BLOCK.

        Before fix: hook threshold was 25%, so 25.3% just barely exceeded it with strict `>`.
        After fix: hook threshold is 20%, so 25.3% is blocked with clear margin.
        """
        prompt = " ".join(["word"] * 367)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=491, max_shrinkage=0.20
        )
        shrinkage = (1.0 - 367 / 491) * 100
        assert result.passed is False, (
            f"491→367 word scenario ({shrinkage:.1f}% shrinkage) must be blocked. "
            f"Got passed={result.passed}"
        )

    # -- Cumulative drift tests (MAX_CUMULATIVE_SHRINKAGE) --

    def test_cumulative_15pct_drift_blocked(self, tmp_path: Path) -> None:
        """Exactly 15% cumulative drift must be blocked (>= boundary).

        Before fix: MAX_CUMULATIVE_SHRINKAGE=0.20 with `>`, so 15% passed easily.
        After fix: MAX_CUMULATIVE_SHRINKAGE=0.15 with `>=`, so 15% is blocked.
        """
        # 200→170 = 15.0% cumulative shrinkage
        record_batch_observation("implementer", 1, 200, state_dir=tmp_path)
        record_batch_observation("implementer", 2, 170, state_dir=tmp_path)

        cumulative = get_cumulative_shrinkage("implementer", state_dir=tmp_path)
        assert cumulative is not None
        assert cumulative == 15.0

        # Verify this is at or above the threshold (should be blocked)
        assert cumulative >= MAX_CUMULATIVE_SHRINKAGE * 100, (
            f"15.0% cumulative drift should be >= threshold {MAX_CUMULATIVE_SHRINKAGE * 100}%"
        )

    def test_cumulative_14pct_drift_passes(self, tmp_path: Path) -> None:
        """14% cumulative drift is under the 15% threshold and must PASS.

        200→172 = 14.0% cumulative shrinkage — just under the new 15% threshold.
        """
        record_batch_observation("implementer", 1, 200, state_dir=tmp_path)
        record_batch_observation("implementer", 2, 172, state_dir=tmp_path)

        cumulative = get_cumulative_shrinkage("implementer", state_dir=tmp_path)
        assert cumulative is not None
        assert cumulative == 14.0

        # Verify this is below the threshold (should pass)
        assert cumulative < MAX_CUMULATIVE_SHRINKAGE * 100, (
            f"14.0% cumulative drift should be < threshold {MAX_CUMULATIVE_SHRINKAGE * 100}%"
        )

    def test_reinvocation_context_relaxes_threshold(self) -> None:
        """Remediation mode doubles the threshold, so 20% shrinkage passes at the library level.

        When invocation_context='remediation', effective_max_shrinkage = 0.15 * 2 = 0.30.
        20% shrinkage < 30% relaxed threshold → should PASS.
        """
        # 100-word baseline, 80-word current = exactly 20.0% shrinkage
        prompt = " ".join(["word"] * 80)
        result = validate_prompt_word_count(
            "implementer",
            prompt,
            baseline_word_count=100,
            max_shrinkage=0.15,
            invocation_context="remediation",
        )
        # Relaxed threshold = 0.15 * 2 = 0.30 = 30%, so 20% should pass
        assert result.passed is True, (
            f"Remediation context should relax threshold to 30%, allowing 20% shrinkage. "
            f"Got passed={result.passed}, shrinkage={result.shrinkage_pct:.1f}%"
        )

    def test_max_cumulative_shrinkage_is_015(self) -> None:
        """Verify MAX_CUMULATIVE_SHRINKAGE is 0.15 (15%) after Issue #812 tightening."""
        assert MAX_CUMULATIVE_SHRINKAGE == 0.15, (
            f"Expected MAX_CUMULATIVE_SHRINKAGE=0.15, got {MAX_CUMULATIVE_SHRINKAGE}. "
            f"Issue #812 tightened from 0.20 to 0.15."
        )

    def test_hook_blocks_at_20pct_shrinkage(self) -> None:
        """Integration: hook denies when prompt shrinks exactly 20% from baseline.

        Uses mocks to isolate the hook-level threshold enforcement.
        """
        import unified_pre_tool as hook

        prompt = " ".join(f"word{i}" for i in range(160))  # 160 words

        # Mock: 200-word baseline, 160-word current = 20.0% shrinkage
        failing_result = PromptIntegrityResult(
            agent_type="implementer",
            word_count=160,
            baseline_word_count=200,
            shrinkage_pct=20.0,
            passed=False,
            reason="Prompt for implementer shrank 20.0% from baseline (200 -> 160 words, threshold: 20%).",
            should_reload=True,
        )

        with (
            patch("prompt_integrity.get_prompt_baseline", return_value=200),
            patch("prompt_integrity.validate_prompt_word_count", return_value=failing_result),
            patch("prompt_integrity.record_batch_observation"),
            patch("prompt_integrity.get_cumulative_shrinkage", return_value=5.0),
            patch("prompt_integrity.MAX_CUMULATIVE_SHRINKAGE", 0.15),
        ):
            decision, reason = hook.validate_prompt_integrity(
                "Agent",
                {"subagent_type": "implementer", "prompt": prompt},
            )

        assert decision == "deny", (
            f"Hook must block when validate_prompt_word_count returns passed=False. "
            f"Got decision={decision!r}"
        )
        assert "BLOCKED" in reason
        assert "20.0%" in reason
        assert "threshold: 20%" in reason
