"""Regression test: Issue #789 — doc-master retry with reduced context not falsely blocked.

The fix adds invocation_context parameter to validate_prompt_word_count() and
_detect_invocation_context() to the hook so that legitimate secondary agent
invocations (remediation, re-review, doc-update-retry) use a relaxed shrinkage
threshold while still enforcing the minimum word floor.
"""

import os
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
    REINVOCATION_CONTEXTS,
    validate_prompt_word_count,
)


class TestDocMasterReinvocation:
    """Tests for doc-master retry with reduced context."""

    def test_retry_with_reinvocation_context_allowed(self) -> None:
        """50% shrinkage with doc-update-retry context passes (relaxed threshold = 50%)."""
        # 300-word baseline, 150-word prompt = 50% shrinkage
        # Normal 25% threshold would block, but relaxed to 50%
        prompt = " ".join(["word"] * 150)
        result = validate_prompt_word_count(
            "doc-master", prompt, baseline_word_count=300,
            max_shrinkage=0.25, invocation_context="doc-update-retry",
        )
        assert result.passed is True
        assert result.should_reload is False

    def test_retry_still_blocked_below_minimum(self) -> None:
        """40-word prompt with reinvocation context still blocked by minimum floor."""
        prompt = " ".join(["word"] * 40)
        result = validate_prompt_word_count(
            "doc-master", prompt, baseline_word_count=300,
            max_shrinkage=0.25, invocation_context="doc-update-retry",
        )
        assert result.passed is False
        assert result.should_reload is True
        assert "minimum" in result.reason

    def test_normal_prompt_no_context(self) -> None:
        """Normal prompt without any markers returns None for context."""
        import unified_pre_tool as hook
        result = hook._detect_invocation_context("Implement the feature as described.")
        assert result is None

    def test_relaxed_threshold_bounded(self) -> None:
        """67% shrinkage with reinvocation context still blocked (67% > 50% relaxed)."""
        # 300-word baseline, 100-word prompt = 66.7% shrinkage
        prompt = " ".join(["word"] * 100)
        result = validate_prompt_word_count(
            "doc-master", prompt, baseline_word_count=300,
            max_shrinkage=0.25, invocation_context="doc-update-retry",
        )
        assert result.passed is False
        assert result.should_reload is True
        assert "66.7%" in result.reason

    def test_reinvocation_contexts_set(self) -> None:
        """Verify REINVOCATION_CONTEXTS contains expected values."""
        assert "remediation" in REINVOCATION_CONTEXTS
        assert "re-review" in REINVOCATION_CONTEXTS
        assert "doc-update-retry" in REINVOCATION_CONTEXTS


class TestInvocationContextDetection:
    """Tests for _detect_invocation_context() in the hook."""

    def test_remediation_mode_marker(self) -> None:
        """Detects 'REMEDIATION MODE' in prompt text."""
        import unified_pre_tool as hook
        result = hook._detect_invocation_context(
            "You are in REMEDIATION MODE. Fix the blocking findings."
        )
        assert result == "remediation"

    def test_re_review_marker(self) -> None:
        """Detects 're-review' in prompt text."""
        import unified_pre_tool as hook
        result = hook._detect_invocation_context(
            "Perform a re-review of the implementation."
        )
        assert result == "re-review"

    def test_reduced_context_marker(self) -> None:
        """Detects 'reduced context' in prompt text."""
        import unified_pre_tool as hook
        result = hook._detect_invocation_context(
            "Retry with reduced context for the doc update."
        )
        assert result == "doc-update-retry"

    def test_env_var_takes_precedence(self) -> None:
        """PIPELINE_INVOCATION_CONTEXT env var overrides prompt scan."""
        import unified_pre_tool as hook
        with patch.dict(os.environ, {"PIPELINE_INVOCATION_CONTEXT": "remediation"}):
            result = hook._detect_invocation_context(
                "This is a normal prompt with no markers."
            )
        assert result == "remediation"

    def test_case_insensitive_detection(self) -> None:
        """Markers are detected case-insensitively."""
        import unified_pre_tool as hook
        result = hook._detect_invocation_context("entering remediation mode now")
        assert result == "remediation"
