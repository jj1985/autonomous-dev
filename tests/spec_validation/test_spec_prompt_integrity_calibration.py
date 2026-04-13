"""Spec validation tests for Issue #810: Prompt integrity calibration.

Tests observable behavior against acceptance criteria ONLY.
Each test maps to a specific acceptance criterion.
"""

import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Add lib to path so we can import prompt_integrity
_lib_path = str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib")
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)

import prompt_integrity  # noqa: E402


class TestSpec810PromptIntegrityCalibration:
    """Spec validation for Issue #810 acceptance criteria."""

    # -- Criterion 1: No systematic blocks on well-formed agent prompts --

    def test_spec_810_1_well_formed_prompts_not_blocked(self):
        """Well-formed agent prompts (200-600 words) must not be systematically
        blocked when baselines are set from first observation."""
        # Simulate a batch: first prompt sets baseline, subsequent prompts
        # of similar size should pass
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)

            agents = ["reviewer", "implementer", "planner", "security-auditor"]
            blocked_count = 0
            total_checks = 0

            for agent in agents:
                # First observation: 400 words (typical task-specific prompt)
                first_prompt = " ".join(["word"] * 400)
                prompt_integrity.record_prompt_baseline(
                    agent, issue_number=1, word_count=400, state_dir=state_dir
                )

                # Subsequent prompts: 350-450 words (normal variation)
                for issue_num, wc in [(2, 350), (3, 380), (4, 420), (5, 450)]:
                    baseline = prompt_integrity.get_prompt_baseline(
                        agent, state_dir=state_dir
                    )
                    prompt = " ".join(["word"] * wc)
                    result = prompt_integrity.validate_prompt_word_count(
                        agent, prompt, baseline
                    )
                    total_checks += 1
                    if not result.passed:
                        blocked_count += 1

            # Less than 5% of checks should be blocked
            block_rate = blocked_count / total_checks
            assert block_rate < 0.05, (
                f"Block rate {block_rate:.1%} exceeds 5% threshold. "
                f"{blocked_count}/{total_checks} prompts were blocked."
            )

    # -- Criterion 2: Baselines use first observation, not templates --

    def test_spec_810_2_seed_baselines_from_templates_is_noop(self):
        """seed_baselines_from_templates() must be a no-op that returns empty dict
        and writes no baselines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)

            result = prompt_integrity.seed_baselines_from_templates(
                state_dir=state_dir
            )

            # Must return empty dict
            assert result == {}, (
                f"seed_baselines_from_templates() returned {result}, expected empty dict"
            )

            # Must not have written any baselines file
            baselines_file = state_dir / "prompt_baselines.json"
            assert not baselines_file.exists(), (
                "seed_baselines_from_templates() wrote a baselines file but should be a no-op"
            )

    def test_spec_810_2_first_observation_sets_baseline(self):
        """Baselines should be established from the first real prompt observation,
        not from template word counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)

            # Record a first observation at 350 words (realistic task prompt)
            prompt_integrity.record_prompt_baseline(
                "reviewer", issue_number=1, word_count=350, state_dir=state_dir
            )

            baseline = prompt_integrity.get_prompt_baseline(
                "reviewer", state_dir=state_dir
            )

            # Baseline should be 350 (first observation), not template size (681-2682)
            assert baseline == 350, (
                f"Baseline is {baseline}, expected 350 from first observation"
            )

    # -- Criterion 3: Block rate <5% for normal batch operations --

    def test_spec_810_3_block_rate_under_5_percent(self):
        """Running 20 normal-sized prompts through integrity checking must result
        in <5% block rate when baselines come from first observation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)

            # Simulate realistic batch: first prompt is baseline, rest are
            # normal variation (within 15% of baseline)
            first_wc = 400
            prompt_integrity.record_prompt_baseline(
                "implementer", issue_number=1, word_count=first_wc,
                state_dir=state_dir,
            )

            blocked = 0
            total = 20
            # Word counts representing normal batch variation
            word_counts = [
                390, 410, 380, 395, 405, 370, 415, 385, 400, 375,
                395, 410, 360, 405, 390, 380, 395, 415, 370, 400,
            ]

            for i, wc in enumerate(word_counts):
                baseline = prompt_integrity.get_prompt_baseline(
                    "implementer", state_dir=state_dir
                )
                prompt = " ".join(["word"] * wc)
                result = prompt_integrity.validate_prompt_word_count(
                    "implementer", prompt, baseline
                )
                if not result.passed:
                    blocked += 1

            block_rate = blocked / total
            assert block_rate < 0.05, (
                f"Block rate {block_rate:.1%} ({blocked}/{total}) exceeds 5% threshold"
            )

    # -- Criterion 4: Still catches genuine shrinkage (>50% drop) --

    def test_spec_810_4_genuine_shrinkage_detected(self):
        """A prompt that shrinks >50% from the first observation must be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)

            # First observation: 400 words
            first_wc = 400
            prompt_integrity.record_prompt_baseline(
                "reviewer", issue_number=1, word_count=first_wc,
                state_dir=state_dir,
            )

            baseline = prompt_integrity.get_prompt_baseline(
                "reviewer", state_dir=state_dir
            )

            # Prompt shrunk to 150 words (62.5% shrinkage)
            shrunken_prompt = " ".join(["word"] * 150)
            result = prompt_integrity.validate_prompt_word_count(
                "reviewer", shrunken_prompt, baseline
            )

            assert not result.passed, (
                "Prompt with 62.5% shrinkage should be blocked but passed"
            )
            assert result.should_reload, (
                "Result should indicate prompt reload needed"
            )

    def test_spec_810_4_moderate_shrinkage_still_caught(self):
        """A prompt that shrinks ~25% from first observation (exceeding the 15%
        default threshold) should still be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)

            first_wc = 400
            prompt_integrity.record_prompt_baseline(
                "planner", issue_number=1, word_count=first_wc,
                state_dir=state_dir,
            )

            baseline = prompt_integrity.get_prompt_baseline(
                "planner", state_dir=state_dir
            )

            # 25% shrinkage: 400 -> 300
            prompt = " ".join(["word"] * 300)
            result = prompt_integrity.validate_prompt_word_count(
                "planner", prompt, baseline
            )

            assert not result.passed, (
                "Prompt with 25% shrinkage should be blocked (threshold is 15%)"
            )

    # -- Criterion 5: Regression test for baseline seeding strategy --

    def test_spec_810_5_template_baselines_not_used_for_validation(self):
        """Template word counts (681-2682) must not be used as baselines.
        A 400-word prompt validated against a template baseline would show
        ~40-85% shrinkage and be wrongly blocked."""
        # Compute what template baselines would be (for reference)
        template_baselines = prompt_integrity.compute_template_baselines()

        # Verify templates are significantly larger than typical task prompts
        if template_baselines:
            min_template = min(template_baselines.values())
            assert min_template > 500, (
                f"Smallest template is only {min_template} words - "
                f"expected >500 to confirm the mismatch with task prompts"
            )

        # Now verify that seed_baselines_from_templates does NOT set these
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            result = prompt_integrity.seed_baselines_from_templates(
                state_dir=state_dir
            )
            assert result == {}, "seed_baselines_from_templates must return empty dict"

            # After calling seed, there should be no baseline for any agent
            for agent in ["reviewer", "implementer", "planner"]:
                baseline = prompt_integrity.get_prompt_baseline(
                    agent, state_dir=state_dir
                )
                assert baseline is None, (
                    f"Agent {agent} has baseline {baseline} after seed_baselines_from_templates, "
                    f"expected None"
                )

    # -- Criterion 6: implement-batch.md updated to use new seeding strategy --

    def test_spec_810_6_implement_batch_references_observation_seeding(self):
        """implement-batch.md must reference observation-based seeding and
        deprecate template-based seeding."""
        batch_md = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"
        )
        assert batch_md.exists(), f"implement-batch.md not found at {batch_md}"

        content = batch_md.read_text(encoding="utf-8")

        # Must mention first observed prompt / observation-based seeding
        assert "first observed" in content.lower() or "observation" in content.lower(), (
            "implement-batch.md does not mention observation-based seeding"
        )

        # Must deprecate or warn against seed_baselines_from_templates
        assert "seed_baselines_from_templates" in content, (
            "implement-batch.md should reference seed_baselines_from_templates "
            "(to mark it as deprecated)"
        )

        # Must indicate the old approach is deprecated or should not be used
        content_lower = content.lower()
        assert "deprecated" in content_lower or "do not call" in content_lower or "do not" in content_lower, (
            "implement-batch.md should indicate template seeding is deprecated"
        )
