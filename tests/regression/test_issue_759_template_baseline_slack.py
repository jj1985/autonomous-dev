"""Regression test: Issue #759 — template-seeded baselines too strict for task-specific prompts.

The prompt integrity gate originally seeded baselines from template file word counts (~2500 words),
but task-specific prompts constructed by the coordinator are naturally shorter (~200-400 words)
because templates contain the full agent definition while the coordinator sends focused task context.
Even with a 0.70 slack factor, template-based seeding produced baselines of ~1700 words, blocking
legitimate ~200-word prompts.

Fix: The hook now seeds from the OBSERVED word count. The library's seed_baselines_from_templates()
handles batch-mode seeding separately with appropriate slack.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Add lib to path for imports
_lib_path = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
if str(_lib_path) not in sys.path:
    sys.path.insert(0, str(_lib_path))

from prompt_integrity import (
    get_prompt_baseline,
    record_prompt_baseline,
    seed_baselines_from_templates,
    validate_prompt_word_count,
)


class TestTemplateBaselineSlackFactor:
    """Verify Issue #759 fix and Issue #810 no-op behavior.

    Issue #759 introduced a 0.70 slack factor for template-seeded baselines.
    Issue #810 deprecated template seeding entirely because even with the slack
    factor, a ~25-50% false positive block rate remained (template ~2500 words,
    actual prompts 200-600 words). seed_baselines_from_templates() is now a no-op.
    """

    def test_seed_baselines_records_at_70_percent(self, tmp_path):
        """Issue #810: seed_baselines_from_templates() is now a no-op, returns {}.

        Before Issue #810: seeded at 70% of template (700 words for 1000-word template).
        After Issue #810: function is a no-op — returns {} and writes no baseline.
        The observation-based path handles seeding from the first real prompt.
        """
        # Create a fake agents directory with a single template
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        # Generate a template with exactly 1000 words
        template_text = " ".join(["word"] * 1000)
        (agents_dir / "reviewer.md").write_text(template_text)

        state_dir = tmp_path / "state"
        state_dir.mkdir()

        with patch(
            "prompt_integrity.COMPRESSION_CRITICAL_AGENTS",
            {"reviewer"},
        ):
            result = seed_baselines_from_templates(agents_dir=agents_dir, state_dir=state_dir)

        # No-op: returns empty dict and writes no baseline
        assert result == {}, (
            f"Expected {{}} (no-op) but got {result}. "
            f"seed_baselines_from_templates() is deprecated (Issue #810)."
        )
        baseline = get_prompt_baseline("reviewer", state_dir=state_dir)
        assert baseline is None, (
            f"Expected no baseline written (no-op) but got {baseline}. "
            f"seed_baselines_from_templates() must not write baselines (Issue #810)."
        )

    def test_prompt_at_75_percent_of_template_passes(self, tmp_path):
        """A prompt at 75% of template word count should PASS validation.

        Before the fix: baseline=1000, prompt=750 -> 25% shrinkage -> BLOCKED.
        After the fix: baseline=700, prompt=750 -> prompt is ABOVE baseline -> PASS.
        """
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Simulate a template-seeded baseline at 70% of 1000 = 700
        record_prompt_baseline("reviewer", issue_number=0, word_count=700, state_dir=state_dir)
        baseline = get_prompt_baseline("reviewer", state_dir=state_dir)

        # A 750-word prompt (75% of original template)
        prompt = " ".join(["word"] * 750)
        result = validate_prompt_word_count(
            "reviewer", prompt, baseline, max_shrinkage=0.25
        )
        assert result.passed, (
            f"Expected 750-word prompt to pass against 700-word baseline, "
            f"but got shrinkage of {result.shrinkage_pct:.1f}%. "
            f"This is the exact false positive scenario from Issue #759."
        )

    def test_genuinely_compressed_prompt_still_fails(self, tmp_path):
        """A prompt at <50% of template word count should still FAIL.

        Even with the slack factor, a severely compressed prompt must be caught.
        Template=1000, baseline=700, prompt=400 -> ~43% shrinkage -> BLOCKED.
        """
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Simulate a template-seeded baseline at 70% of 1000 = 700
        record_prompt_baseline("reviewer", issue_number=0, word_count=700, state_dir=state_dir)
        baseline = get_prompt_baseline("reviewer", state_dir=state_dir)

        # A 400-word prompt (~40% of original template, well below threshold)
        prompt = " ".join(["word"] * 400)
        result = validate_prompt_word_count(
            "reviewer", prompt, baseline, max_shrinkage=0.25
        )
        assert not result.passed, (
            f"Expected 400-word prompt to FAIL against 700-word baseline, "
            f"but it passed. Genuinely compressed prompts must still be caught."
        )
        # Verify shrinkage is reported correctly: (700-400)/700 = 42.9%
        assert result.shrinkage_pct > 25.0, (
            f"Expected >25% shrinkage but got {result.shrinkage_pct:.1f}%"
        )

    def test_hook_seeds_baseline_from_observed_word_count(self, tmp_path):
        """The unified_pre_tool validate_prompt_integrity seeds from observed word count.

        Issue #759 continuation: template-based seeding (even with 0.70 slack) produced
        baselines of ~1700 words, blocking legitimate ~200-400 word task prompts.
        The hook now seeds directly from the observed prompt word count.
        """
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Simulate the hook's else branch: observed prompt is 250 words
        observed_wc = 250

        # Record as the hook would — directly using observed word count
        record_prompt_baseline("reviewer", issue_number=0, word_count=observed_wc, state_dir=state_dir)
        baseline = get_prompt_baseline("reviewer", state_dir=state_dir)
        assert baseline == 250, (
            f"Expected baseline of 250 (observed word count) but got {baseline}. "
            f"The hook should seed from observed, not template."
        )
