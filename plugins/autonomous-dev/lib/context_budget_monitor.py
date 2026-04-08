"""Context budget monitor for inline truncation warnings and token budget tracking.

This module provides utilities for:
- Truncating long outputs with visible markers so downstream agents know content was cut
- Checking token budget usage and generating advisory/critical warnings
- Estimating token counts from text

Usage:
    from plugins.autonomous_dev.lib.context_budget_monitor import (
        truncate_output,
        check_context_budget,
        estimate_tokens,
    )
"""

from typing import Optional

# Default limits for output truncation
DEFAULT_MAX_OUTPUT_CHARS: int = 12000
DEFAULT_TAIL_CHARS: int = 500

# Thresholds for context budget warnings
WARN_THRESHOLD: float = 0.80
CRITICAL_THRESHOLD: float = 0.95


def truncate_output(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    tail_chars: int = DEFAULT_TAIL_CHARS,
) -> str:
    """Truncate long output with a visible marker indicating removed content.

    If the text is within max_chars, it is returned unchanged. If it exceeds
    max_chars, the output shows the head and tail of the original text with an
    inline marker at the truncation point so downstream agents know content was cut.

    The marker format is:
        [TRUNCATED: N chars removed. Showing first K + last T chars]

    Args:
        text: The text to potentially truncate.
        max_chars: Maximum number of characters to allow before truncating.
            Defaults to DEFAULT_MAX_OUTPUT_CHARS (12000).
        tail_chars: Number of characters to preserve from the end of the text.
            Defaults to DEFAULT_TAIL_CHARS (500). If tail_chars >= max_chars,
            no tail is shown and the text is front-truncated only.

    Returns:
        Original text if within limit, otherwise truncated text with marker.

    Example:
        >>> result = truncate_output("x" * 15000)
        >>> "[TRUNCATED:" in result
        True
    """
    if len(text) <= max_chars:
        return text

    total_chars = len(text)

    # Edge case: tail_chars >= max_chars — no room for tail, just show head
    if tail_chars >= max_chars:
        head = text[:max_chars]
        removed = total_chars - max_chars
        marker = f"\n\n[TRUNCATED: {removed} chars removed. Showing first {max_chars} chars]\n\n"
        return head + marker

    head_chars = max_chars - tail_chars
    head = text[:head_chars]
    tail = text[total_chars - tail_chars:]
    removed = total_chars - max_chars

    marker = (
        f"\n\n[TRUNCATED: {removed} chars removed. "
        f"Showing first {head_chars} + last {tail_chars} chars]\n\n"
    )
    return head + marker + tail


def check_context_budget(
    current_tokens: int,
    max_tokens: int,
    *,
    warn_threshold: float = WARN_THRESHOLD,
    critical_threshold: float = CRITICAL_THRESHOLD,
) -> Optional[str]:
    """Check the current token usage against the budget and return a warning if needed.

    Returns None if usage is below the warn threshold. Returns an advisory string
    if usage is between warn and critical thresholds, and a critical string if
    usage is at or above the critical threshold.

    Args:
        current_tokens: Number of tokens currently used. Negative values are
            treated as 0.
        max_tokens: Maximum token budget. If <= 0, returns a critical warning.
        warn_threshold: Fraction at which to start advisory warnings (default: 0.80).
        critical_threshold: Fraction at which to issue critical warnings (default: 0.95).

    Returns:
        None if under warn_threshold, advisory string if between warn and critical,
        or critical string if at or above critical threshold.

    Example:
        >>> check_context_budget(85000, 100000)
        '[CONTEXT NOTE: 85% of token budget used. Prioritize completing current task over exploration.]'
        >>> check_context_budget(50000, 100000) is None
        True
    """
    # Guard against invalid max_tokens
    if max_tokens <= 0:
        return (
            f"[CONTEXT WARNING: 100% of token budget used "
            f"({current_tokens}/{max_tokens}). Complete current step only.]"
        )

    # Clamp current_tokens to non-negative
    effective_current = max(0, current_tokens)
    ratio = effective_current / max_tokens
    pct = int(ratio * 100)

    if ratio >= critical_threshold:
        return (
            f"[CONTEXT WARNING: {pct}% of token budget used "
            f"({effective_current}/{max_tokens}). Complete current step only.]"
        )

    if ratio >= warn_threshold:
        return (
            f"[CONTEXT NOTE: {pct}% of token budget used. "
            f"Prioritize completing current task over exploration.]"
        )

    return None


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text string.

    Uses a simple word-count approximation: token_count ≈ word_count * 1.3.
    This is a rough estimate; actual tokenization depends on the model.

    Args:
        text: The text to estimate token count for. Non-string or empty
            values return 0.

    Returns:
        Estimated number of tokens as an integer. Returns 0 for empty or
        non-string input.

    Example:
        >>> estimate_tokens("hello world")
        2
        >>> estimate_tokens("")
        0
    """
    if not isinstance(text, str) or not text:
        return 0

    word_count = len(text.split())
    return int(word_count * 1.3)
