"""Acceptance tests for Issue #810: Prompt integrity calibration.

Static tests (no LLM calls) verifying the acceptance criteria:

1. seed_baselines_from_templates() is a no-op that returns {} and writes nothing.
2. First observation becomes the baseline (observation-based seeding).
3. Genuine shrinkage (>threshold) is still caught and blocked.
4. Absolute floor (MIN_CRITICAL_AGENT_PROMPT_WORDS) is still enforced.
5. implement-batch.md no longer references seed_baselines_from_templates() as active.
6. 280-word prompt with 300-word baseline passes (no false positive).
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


class TestAcceptance810PromptIntegrityCalibration:
    """Acceptance tests for Issue #810."""

    def test_no_systematic_blocks_on_well_formed_prompts(self, tmp_path: Path) -> None:
        """A 280-word prompt with a 300-word baseline passes without false positive.

        Before Issue #810: template-seeded baseline (~700 words) would block this prompt
        with ~60% apparent shrinkage. After the fix: observation-based 300-word baseline
        means only 6.7% shrinkage — well within the 15% threshold.
        """
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Observation-based baseline: 300 words
        record_prompt_baseline("reviewer", issue_number=1, word_count=300, state_dir=state_dir)
        baseline = get_prompt_baseline("reviewer", state_dir=state_dir)

        # 280-word prompt: 6.7% shrinkage, should pass
        prompt = " ".join(["word"] * 280)
        result = validate_prompt_word_count("reviewer", prompt, baseline)

        assert result.passed is True, (
            f"Expected 280-word prompt to pass against 300-word baseline (6.7% shrinkage), "
            f"but got passed={result.passed}, shrinkage={result.shrinkage_pct:.1f}%. "
            f"This is the false positive scenario eliminated by Issue #810."
        )

    def test_first_observation_becomes_baseline(self, tmp_path: Path) -> None:
        """Baseline starts as None; first observation sets it via record_prompt_baseline()."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # No baseline before first observation
        assert get_prompt_baseline("implementer", state_dir=state_dir) is None

        # First observation
        record_prompt_baseline("implementer", issue_number=7, word_count=320, state_dir=state_dir)
        baseline = get_prompt_baseline("implementer", state_dir=state_dir)

        assert baseline == 320, f"Expected baseline=320 from first observation, got {baseline}"

    def test_genuine_shrinkage_still_caught(self, tmp_path: Path) -> None:
        """A >50% drop from the observation-based baseline is blocked."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        record_prompt_baseline("security-auditor", issue_number=1, word_count=350, state_dir=state_dir)
        baseline = get_prompt_baseline("security-auditor", state_dir=state_dir)

        # 150 words from 350-word baseline = ~57% shrinkage
        short_prompt = " ".join(["word"] * 150)
        result = validate_prompt_word_count("security-auditor", short_prompt, baseline, max_shrinkage=0.25)

        assert result.passed is False, (
            f"Expected genuine shrinkage ({result.shrinkage_pct:.1f}%) to be blocked."
        )
        assert result.should_reload is True
        assert result.shrinkage_pct > 50.0

    def test_seed_baselines_from_templates_is_noop(self, tmp_path: Path) -> None:
        """seed_baselines_from_templates() returns {} and writes no baselines (Issue #810)."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "implementer.md").write_text(" ".join(["word"] * 800))
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        result = seed_baselines_from_templates(agents_dir=agents_dir, state_dir=state_dir)

        assert result == {}, f"Expected {{}} (no-op), got {result}"
        assert get_prompt_baseline("implementer", state_dir=state_dir) is None, (
            "seed_baselines_from_templates() must not write any baseline (Issue #810)"
        )

    def test_implement_batch_md_updated(self) -> None:
        """implement-batch.md no longer calls seed_baselines_from_templates() at batch start.

        The instruction must now say to call only clear_prompt_baselines(), and must
        note that seed_baselines_from_templates() is deprecated.
        """
        batch_md = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"
        assert batch_md.exists(), f"implement-batch.md not found at {batch_md}"

        content = batch_md.read_text(encoding="utf-8")

        # Must not instruct calling seed_baselines_from_templates() as an active step
        # (it may appear in a "deprecated" note, which is fine)
        assert "seed_baselines_from_templates()" not in content or "deprecated" in content, (
            "implement-batch.md still instructs calling seed_baselines_from_templates() "
            "as an active step. It must be removed or marked deprecated (Issue #810)."
        )

        # Must mention clear_prompt_baselines() as the reset call
        assert "clear_prompt_baselines()" in content, (
            "implement-batch.md must instruct calling clear_prompt_baselines() at batch start."
        )

    def test_absolute_floor_still_enforced(self, tmp_path: Path) -> None:
        """A 50-word prompt for a critical agent is blocked regardless of baseline.

        The absolute floor must survive the observation-based transition.
        """
        # No baseline needed — absolute floor check is independent
        prompt = " ".join(["word"] * 50)
        result = validate_prompt_word_count("security-auditor", prompt)

        assert result.passed is False, (
            f"Expected 50-word prompt for critical agent to fail absolute floor check, "
            f"but got passed=True. MIN_CRITICAL_AGENT_PROMPT_WORDS={MIN_CRITICAL_AGENT_PROMPT_WORDS}"
        )
        assert result.should_reload is True
        assert "minimum" in result.reason.lower()
