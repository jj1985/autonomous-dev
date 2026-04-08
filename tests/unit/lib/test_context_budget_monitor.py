"""Unit tests for context_budget_monitor module."""

import sys
from pathlib import Path

# Add lib directory to path for direct imports
lib_path = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(lib_path))

from context_budget_monitor import (
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_TAIL_CHARS,
    check_context_budget,
    estimate_tokens,
    truncate_output,
)


class TestTruncateOutput:
    """Tests for truncate_output function."""

    def test_truncate_output_under_limit_unchanged(self):
        """Text under the limit is returned unchanged."""
        text = "a" * 100
        result = truncate_output(text, max_chars=200)
        assert result == text

    def test_truncate_output_at_limit_unchanged(self):
        """Text exactly at the limit is returned unchanged."""
        text = "a" * 200
        result = truncate_output(text, max_chars=200)
        assert result == text

    def test_truncate_output_over_limit_has_marker(self):
        """Text exceeding the limit contains the TRUNCATED marker."""
        text = "a" * 1500
        result = truncate_output(text, max_chars=1000, tail_chars=100)
        assert "[TRUNCATED:" in result

    def test_truncate_output_preserves_head_and_tail(self):
        """The head and tail of the original text are preserved."""
        head_content = "HEAD_CONTENT"
        tail_content = "TAIL_CONTENT"
        padding = "x" * 2000
        text = head_content + padding + tail_content

        result = truncate_output(text, max_chars=500, tail_chars=len(tail_content))

        assert result.startswith(head_content)
        assert result.endswith(tail_content)

    def test_truncate_output_marker_reports_correct_removal_count(self):
        """The marker accurately reports how many chars were removed."""
        total = 2000
        max_chars = 1000
        tail_chars = 100
        text = "a" * total

        result = truncate_output(text, max_chars=max_chars, tail_chars=tail_chars)

        removed = total - max_chars
        assert f"{removed} chars removed" in result

    def test_truncate_output_custom_limits(self):
        """Custom max_chars and tail_chars are respected."""
        text = "a" * 300
        result = truncate_output(text, max_chars=200, tail_chars=50)
        # The output should be shorter than the original
        assert len(result) < len(text) or "[TRUNCATED:" in result

    def test_truncate_output_empty_string(self):
        """Empty string is returned unchanged."""
        result = truncate_output("", max_chars=100)
        assert result == ""

    def test_truncate_output_tail_larger_than_max(self):
        """When tail_chars >= max_chars, only show head with simplified marker."""
        text = "a" * 500
        result = truncate_output(text, max_chars=100, tail_chars=150)
        # Should include head only (simplified marker, no tail section)
        assert "[TRUNCATED:" in result
        # Should not show "last X chars" format with a tail (tail >= max)
        assert result.startswith("a" * 100)


class TestCheckContextBudget:
    """Tests for check_context_budget function."""

    def test_check_budget_under_warn_returns_none(self):
        """Usage below warn threshold returns None."""
        result = check_context_budget(70000, 100000)
        assert result is None

    def test_check_budget_at_warn_returns_advisory(self):
        """Usage at the warn threshold returns an advisory message."""
        result = check_context_budget(80000, 100000)
        assert result is not None
        assert "CONTEXT NOTE" in result
        assert "80%" in result

    def test_check_budget_at_critical_returns_critical(self):
        """Usage at the critical threshold returns a critical warning."""
        result = check_context_budget(95000, 100000)
        assert result is not None
        assert "CONTEXT WARNING" in result
        assert "95%" in result

    def test_check_budget_over_100_returns_critical(self):
        """Usage over 100% still returns a critical warning."""
        result = check_context_budget(110000, 100000)
        assert result is not None
        assert "CONTEXT WARNING" in result

    def test_check_budget_custom_thresholds(self):
        """Custom warn and critical thresholds are used correctly."""
        # With warn=0.5, 60% usage should trigger advisory
        result = check_context_budget(60000, 100000, warn_threshold=0.5, critical_threshold=0.9)
        assert result is not None
        assert "CONTEXT NOTE" in result

        # With critical=0.9, 95% usage should trigger critical
        result = check_context_budget(95000, 100000, warn_threshold=0.5, critical_threshold=0.9)
        assert result is not None
        assert "CONTEXT WARNING" in result

    def test_check_budget_zero_max_tokens(self):
        """Zero max_tokens returns a critical warning to avoid division by zero."""
        result = check_context_budget(1000, 0)
        assert result is not None
        assert "CONTEXT WARNING" in result

    def test_check_budget_negative_current_tokens(self):
        """Negative current_tokens is treated as 0 (below warn threshold)."""
        result = check_context_budget(-100, 100000)
        assert result is None

    def test_check_budget_between_warn_and_critical(self):
        """Usage strictly between warn and critical thresholds is advisory only."""
        result = check_context_budget(87000, 100000)
        assert result is not None
        assert "CONTEXT NOTE" in result
        assert "CONTEXT WARNING" not in result


class TestEstimateTokens:
    """Tests for estimate_tokens function."""

    def test_estimate_tokens_empty(self):
        """Empty string returns 0."""
        assert estimate_tokens("") == 0

    def test_estimate_tokens_approximation(self):
        """Non-empty text returns a positive integer approximation."""
        # 10 words * 1.3 = 13 tokens
        text = "one two three four five six seven eight nine ten"
        result = estimate_tokens(text)
        assert isinstance(result, int)
        assert result > 0
        # Should be approximately 13 (10 words * 1.3)
        assert result == 13

    def test_estimate_tokens_single_word(self):
        """Single word returns non-zero estimate."""
        result = estimate_tokens("hello")
        assert result >= 1

    def test_estimate_tokens_non_string_returns_zero(self):
        """Non-string input returns 0."""
        assert estimate_tokens(None) == 0  # type: ignore[arg-type]
        assert estimate_tokens(42) == 0  # type: ignore[arg-type]
        assert estimate_tokens([]) == 0  # type: ignore[arg-type]
