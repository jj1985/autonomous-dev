"""Regression test: Issue #794 — progressive compression detection across batch iterations.

The fix adds cumulative drift tracking via record_batch_observation() and
get_cumulative_shrinkage() so that progressive 3-5% per-iteration compression
that individually passes the 25% per-issue threshold is detected when it
accumulates beyond 20% total.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Path depth: tests/regression/ -> parents[2] for project root
REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
HOOK_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(LIB_DIR))
sys.path.insert(0, str(HOOK_DIR))

from prompt_integrity import (
    MAX_CUMULATIVE_SHRINKAGE,
    clear_batch_observations,
    get_cumulative_shrinkage,
    record_batch_observation,
)


class TestCumulativeDriftTracking:
    """Tests for cumulative drift detection across batch iterations."""

    def test_cumulative_shrinkage_detected_across_issues(self, tmp_path: Path) -> None:
        """Simulate 250->230->210->190->170->150->120 progression.

        Each step is <25% from previous, but 250->120 = 52% total drift.
        """
        observations = [250, 230, 210, 190, 170, 150, 120]
        for i, wc in enumerate(observations):
            record_batch_observation("reviewer", issue_number=i + 1, word_count=wc, state_dir=tmp_path)

        result = get_cumulative_shrinkage("reviewer", state_dir=tmp_path)
        assert result is not None
        assert result == 52.0  # (250 - 120) / 250 * 100

    def test_cumulative_below_threshold_passes(self, tmp_path: Path) -> None:
        """250->240->230->220 (~12%). Below 20% threshold."""
        for i, wc in enumerate([250, 240, 230, 220]):
            record_batch_observation("reviewer", issue_number=i + 1, word_count=wc, state_dir=tmp_path)

        result = get_cumulative_shrinkage("reviewer", state_dir=tmp_path)
        assert result is not None
        assert result == 12.0  # (250 - 220) / 250 * 100
        assert result < MAX_CUMULATIVE_SHRINKAGE * 100

    def test_cumulative_at_threshold_boundary(self, tmp_path: Path) -> None:
        """250->212 exactly (~15.2%). Test boundary behavior — just over 15% is blocked (Issue #812)."""
        record_batch_observation("reviewer", 1, 250, state_dir=tmp_path)
        record_batch_observation("reviewer", 2, 212, state_dir=tmp_path)

        result = get_cumulative_shrinkage("reviewer", state_dir=tmp_path)
        assert result == 15.2  # Just over threshold (tightened to 15% in Issue #812)

    def test_single_observation_returns_none(self, tmp_path: Path) -> None:
        """Only 1 observation recorded. Returns None (no drift calculable)."""
        record_batch_observation("reviewer", 1, 250, state_dir=tmp_path)

        result = get_cumulative_shrinkage("reviewer", state_dir=tmp_path)
        assert result is None

    def test_clear_batch_observations_resets(self, tmp_path: Path) -> None:
        """Record observations, clear, verify get_cumulative_shrinkage returns None."""
        record_batch_observation("reviewer", 1, 250, state_dir=tmp_path)
        record_batch_observation("reviewer", 2, 200, state_dir=tmp_path)

        # Verify observations exist
        assert get_cumulative_shrinkage("reviewer", state_dir=tmp_path) is not None

        # Clear and verify reset
        clear_batch_observations(state_dir=tmp_path)
        assert get_cumulative_shrinkage("reviewer", state_dir=tmp_path) is None

    def test_nonexistent_agent_returns_none(self, tmp_path: Path) -> None:
        """get_cumulative_shrinkage for unknown agent returns None gracefully."""
        result = get_cumulative_shrinkage("nonexistent-agent", state_dir=tmp_path)
        assert result is None

    def test_growth_returns_zero(self, tmp_path: Path) -> None:
        """If prompt grows rather than shrinks, returns 0.0 not negative."""
        record_batch_observation("reviewer", 1, 200, state_dir=tmp_path)
        record_batch_observation("reviewer", 2, 250, state_dir=tmp_path)

        result = get_cumulative_shrinkage("reviewer", state_dir=tmp_path)
        assert result == 0.0

    def test_hook_blocks_on_cumulative_drift(self, tmp_path: Path) -> None:
        """Integration test: hook returns deny when cumulative exceeds 20%."""
        import unified_pre_tool as hook

        prompt = " ".join(f"word{i}" for i in range(150))  # 150 words, above minimum

        # Mock so per-issue baseline check passes but cumulative drift exceeds threshold
        passing_result = type("Result", (), {
            "passed": True, "shrinkage_pct": 5.0, "word_count": 150,
            "baseline_word_count": 160, "reason": "OK", "should_reload": False,
            "agent_type": "reviewer",
        })()

        with (
            patch("prompt_integrity.get_prompt_baseline", return_value=160),
            patch("prompt_integrity.validate_prompt_word_count", return_value=passing_result),
            patch("prompt_integrity.record_batch_observation"),
            patch("prompt_integrity.get_cumulative_shrinkage", return_value=25.0),
            patch("prompt_integrity.MAX_CUMULATIVE_SHRINKAGE", 0.20),
        ):
            decision, reason = hook.validate_prompt_integrity(
                "Agent",
                {"subagent_type": "reviewer", "prompt": prompt},
            )

        assert decision == "deny"
        assert "Cumulative" in reason
        assert "25.0%" in reason
        assert "REQUIRED NEXT ACTION" in reason

    def test_max_cumulative_shrinkage_constant(self) -> None:
        """Verify MAX_CUMULATIVE_SHRINKAGE is 0.15 (15%) — tightened in Issue #812."""
        assert MAX_CUMULATIVE_SHRINKAGE == 0.15

    def test_observations_persisted_to_json(self, tmp_path: Path) -> None:
        """Verify observations file is valid JSON with expected structure."""
        record_batch_observation("reviewer", 1, 250, state_dir=tmp_path)
        record_batch_observation("reviewer", 2, 230, state_dir=tmp_path)

        obs_path = tmp_path / "prompt_batch_observations.json"
        assert obs_path.exists()

        data = json.loads(obs_path.read_text())
        assert "reviewer" in data
        assert len(data["reviewer"]) == 2
        assert data["reviewer"][0] == {"issue": 1, "word_count": 250}
        assert data["reviewer"][1] == {"issue": 2, "word_count": 230}
