"""Regression test: Issue #748 — template-based baselines for batch prompt compression.

Bug: Without template-based seeding, the first issue's prompt (which may already
be compressed) becomes the baseline. Subsequent issues are compared against the
already-compressed baseline, masking progressive compression entirely.

The fix ships as:
  - compute_template_baselines() in prompt_integrity.py
  - seed_baselines_from_templates() in prompt_integrity.py
  - Hook fallback in unified_pre_tool.py: seeds from template, not observed wc
  - implement-batch.md updated: seed_baselines_from_templates() call documented

Reproduces the exact bug scenarios described in the issue.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_PATH = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
AGENTS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "agents"
IMPLEMENT_BATCH = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"
HOOK_FILE = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks" / "unified_pre_tool.py"

if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from prompt_integrity import (
    clear_prompt_baselines,
    compute_template_baselines,
    get_prompt_baseline,
    seed_baselines_from_templates,
    validate_prompt_word_count,
)


class TestFirstIssueCompressionCaught:
    """Reproduce exact bug: compressed first-issue prompt bypasses detection.

    Without template seeding:
      - Issue 1 sends a compressed 108-word implementer prompt
      - 108 words recorded as baseline
      - Issue 2 sends 110-word prompt → no shrinkage detected, compression goes unnoticed

    With template seeding:
      - Template has 235 words
      - Issue 1 sends 108-word prompt → 54% shrinkage from template → caught
    """

    def test_first_issue_compressed_implementer_46pct_caught(self, tmp_path: Path) -> None:
        """Template baseline catches compression on the very first implementer invocation.

        Without template seeding the first issue's compressed prompt sets the baseline,
        making all subsequent detections useless.

        Note: seed_baselines_from_templates applies a 0.70 slack factor (Issue #759)
        so the baseline is int(template_words * 0.70), not template_words directly.
        """
        template_words = 235
        expected_baseline = int(template_words * 0.70)  # 164 after slack factor
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "implementer.md").write_text("word " * template_words, encoding="utf-8")
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Batch start: clear then seed from templates
        clear_prompt_baselines(state_dir=state_dir)
        seed_baselines_from_templates(agents_dir=agents_dir, state_dir=state_dir)

        baseline = get_prompt_baseline("implementer", state_dir=state_dir)
        assert baseline == expected_baseline, f"Expected template baseline {expected_baseline} (with 0.70 slack), got {baseline}"

        # First issue prompt is significantly smaller than baseline
        first_issue_words = int(expected_baseline * 0.54)  # ~88 words, ~46% shrinkage from baseline
        compressed_prompt = " ".join(["word"] * first_issue_words)
        result = validate_prompt_word_count(
            "implementer", compressed_prompt, baseline, max_shrinkage=0.25
        )

        assert result.passed is False, "Expected compression to be caught on first issue"
        assert result.should_reload is True
        assert result.shrinkage_pct > 40.0

    def test_first_issue_compressed_security_auditor_49pct_caught(
        self, tmp_path: Path
    ) -> None:
        """Template baseline catches compression on first security-auditor invocation.

        Mirrors the implementer scenario for security-auditor — the other agent
        explicitly mentioned in the issue description.

        Note: seed_baselines_from_templates applies a 0.70 slack factor (Issue #759).
        """
        template_words = 300
        expected_baseline = int(template_words * 0.70)  # 210 after slack factor
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "security-auditor.md").write_text(
            "word " * template_words, encoding="utf-8"
        )
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        clear_prompt_baselines(state_dir=state_dir)
        seed_baselines_from_templates(agents_dir=agents_dir, state_dir=state_dir)

        baseline = get_prompt_baseline("security-auditor", state_dir=state_dir)
        assert baseline == expected_baseline

        # First issue: ~49% shrinkage from the slack-adjusted baseline
        first_issue_words = int(expected_baseline * 0.51)
        compressed_prompt = " ".join(["word"] * first_issue_words)
        result = validate_prompt_word_count(
            "security-auditor", compressed_prompt, baseline, max_shrinkage=0.25
        )

        assert result.passed is False
        assert result.should_reload is True
        assert result.shrinkage_pct > 40.0

    def test_progressive_compression_across_batch(self, tmp_path: Path) -> None:
        """Template baseline prevents progressive compression from going undetected.

        With template seeding (600-word template, 0.70 slack = 420 baseline):
          - Issue 1 at 300 words: 28.6% shrinkage from 420 → caught (>25%)
          - Issue 2 at 280 words: 33.3% shrinkage from 420 → caught
          - Issue 3 at 200 words: 52.4% shrinkage from 420 → caught

        Note: seed_baselines_from_templates applies a 0.70 slack factor (Issue #759).
        """
        template_words = 600
        expected_baseline = int(template_words * 0.70)  # 420 after slack factor
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "reviewer.md").write_text("word " * template_words, encoding="utf-8")
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        clear_prompt_baselines(state_dir=state_dir)
        seed_baselines_from_templates(agents_dir=agents_dir, state_dir=state_dir)

        baseline = get_prompt_baseline("reviewer", state_dir=state_dir)
        assert baseline == expected_baseline

        # Simulate progressive compression across 3 issues
        issue_word_counts = [300, 280, 200]  # Progressive shrinkage

        # All three issues should fail against the 420-word baseline (with slack)
        for issue_num, wc in enumerate(issue_word_counts, start=1):
            prompt = " ".join(["word"] * wc)
            shrinkage = round((1.0 - wc / expected_baseline) * 100, 1)
            result = validate_prompt_word_count(
                "reviewer", prompt, baseline, max_shrinkage=0.25
            )
            # All are >25% smaller than slack-adjusted baseline — all should fail
            if shrinkage > 25.0:
                assert result.passed is False, (
                    f"Issue {issue_num} ({wc} words, {shrinkage:.1f}% shrinkage) "
                    f"should have been caught"
                )

    def test_hook_fallback_seeds_template_not_observed(self, tmp_path: Path) -> None:
        """Verify hook fallback behavior: template word count used, not observed prompt wc.

        The hook's 'no baseline yet' branch must use the template word count so that
        when the first real Agent call is made, its prompt is compared against the
        full template, not itself.
        """
        # Template: 400 words
        template_words = 400
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "implementer.md").write_text("word " * template_words, encoding="utf-8")
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Simulate what the hook does: get_agent_prompt_template → compute wc → record
        from prompt_integrity import get_agent_prompt_template, record_prompt_baseline

        template = get_agent_prompt_template("implementer", agents_dir=agents_dir)
        template_wc = len(template.split())
        record_prompt_baseline("implementer", issue_number=0, word_count=template_wc, state_dir=state_dir)

        baseline = get_prompt_baseline("implementer", state_dir=state_dir)

        # Baseline MUST be the template word count, not the observed prompt word count
        assert baseline == template_words, (
            f"Hook fallback should seed template wc ({template_words}) "
            f"not an observed prompt wc. Got: {baseline}"
        )

        # Now a compressed first-issue prompt is correctly flagged
        compressed = " ".join(["word"] * 200)  # 50% shrinkage
        result = validate_prompt_word_count(
            "implementer", compressed, baseline, max_shrinkage=0.25
        )
        assert result.passed is False
        assert result.shrinkage_pct > 40.0


class TestTemplateSeedingDocumented:
    """Verify the fix is documented in implement-batch.md."""

    def setup_method(self) -> None:
        self.content = IMPLEMENT_BATCH.read_text(encoding="utf-8")

    def test_seed_baselines_from_templates_documented(self) -> None:
        """implement-batch.md must reference seed_baselines_from_templates()."""
        assert "seed_baselines_from_templates" in self.content, (
            "implement-batch.md must document the seed_baselines_from_templates() call "
            "so coordinators know to call it at batch start."
        )

    def test_hook_uses_template_not_observed_wc(self) -> None:
        """unified_pre_tool.py must use get_agent_prompt_template in fallback branch."""
        hook_content = HOOK_FILE.read_text(encoding="utf-8")
        assert "get_agent_prompt_template" in hook_content, (
            "unified_pre_tool.py hook fallback must use get_agent_prompt_template() "
            "to seed template-based baseline, not observed word count."
        )
