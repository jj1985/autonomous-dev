"""Regression test: Issue #791 — remediation loop bypass of prompt integrity checks.

42% of remediation-mode secondary invocations were unblocked because the hook
did not account for the naturally shorter prompts in reinvocations. The fix
adds invocation context detection with relaxed thresholds while still enforcing
minimum word floor and cumulative drift tracking.
"""

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
    MIN_CRITICAL_AGENT_PROMPT_WORDS,
    record_batch_observation,
    get_cumulative_shrinkage,
    validate_prompt_word_count,
)


class TestRemediationBypass:
    """Tests for remediation loop secondary invocations properly validated."""

    def test_implementer_remediation_allowed(self) -> None:
        """43% shrinkage with remediation context allowed (43% < 50% relaxed)."""
        # 350-word baseline, 200-word prompt = 42.9% shrinkage
        prompt = " ".join(["word"] * 200)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=350,
            max_shrinkage=0.25, invocation_context="remediation",
        )
        assert result.passed is True
        assert result.should_reload is False

    def test_remediation_minimum_enforced(self) -> None:
        """Sub-80 word remediation prompt blocked regardless of reinvocation context."""
        prompt = " ".join(["word"] * 50)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=350,
            max_shrinkage=0.25, invocation_context="remediation",
        )
        assert result.passed is False
        assert result.should_reload is True
        assert "minimum" in result.reason

    def test_re_review_allowed(self) -> None:
        """re-review marker detected and allowed at relaxed threshold."""
        # 300-word baseline, 180-word prompt = 40% shrinkage
        prompt = " ".join(["word"] * 180)
        result = validate_prompt_word_count(
            "reviewer", prompt, baseline_word_count=300,
            max_shrinkage=0.25, invocation_context="re-review",
        )
        assert result.passed is True

    def test_without_marker_standard_threshold(self) -> None:
        """Same 43% shrinkage WITHOUT marker is blocked at standard 25% threshold."""
        prompt = " ".join(["word"] * 200)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=350,
            max_shrinkage=0.25, invocation_context=None,
        )
        assert result.passed is False
        assert result.should_reload is True

    def test_cumulative_includes_reinvocations(self, tmp_path: Path) -> None:
        """Remediation invocations still recorded for cumulative drift tracking."""
        # Record a series of observations including a remediation invocation
        record_batch_observation("implementer", 1, 350, state_dir=tmp_path)
        record_batch_observation("implementer", 2, 300, state_dir=tmp_path)
        # Remediation invocation — still recorded
        record_batch_observation("implementer", 2, 200, state_dir=tmp_path)

        result = get_cumulative_shrinkage("implementer", state_dir=tmp_path)
        assert result is not None
        # (350 - 200) / 350 * 100 = 42.9%
        assert result == 42.9

    def test_unknown_context_uses_standard_threshold(self) -> None:
        """Unknown invocation_context string uses standard (not relaxed) threshold."""
        prompt = " ".join(["word"] * 200)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=350,
            max_shrinkage=0.25, invocation_context="some-unknown-context",
        )
        # 42.9% > 25% standard threshold -> blocked
        assert result.passed is False
        assert result.should_reload is True
