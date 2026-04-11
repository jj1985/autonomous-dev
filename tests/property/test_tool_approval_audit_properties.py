"""Property-based tests for tool_approval_audit.py sanitization functions.

Tests invariants:
- sanitize_log_input removes all control characters (except tab)
- sanitize_log_input removes ANSI escape sequences
- sanitize_log_input never crashes on any string input
- AuditLogEntry.to_dict excludes None values
"""

import re

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from tool_approval_audit import (
    INJECTION_CHARS,
    AuditLogEntry,
    sanitize_log_input,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Arbitrary strings for crash testing
arbitrary_string = st.text(min_size=0, max_size=1000)

# Strings with control characters
control_char = st.sampled_from(INJECTION_CHARS)

string_with_injection = st.builds(
    lambda prefix, cc, suffix: prefix + cc + suffix,
    st.text(min_size=0, max_size=50, alphabet=st.characters(whitelist_categories=("L",))),
    control_char,
    st.text(min_size=0, max_size=50, alphabet=st.characters(whitelist_categories=("L",))),
)

# Strings with ANSI escape sequences
ansi_escape = st.builds(
    lambda code: f"\x1b[{code}m",
    st.from_regex(r"[0-9;]{1,5}", fullmatch=True),
)

string_with_ansi = st.builds(
    lambda prefix, esc, suffix: prefix + esc + suffix,
    st.text(min_size=0, max_size=30, alphabet=st.characters(whitelist_categories=("L",))),
    ansi_escape,
    st.text(min_size=0, max_size=30, alphabet=st.characters(whitelist_categories=("L",))),
)

# Clean text without any injection chars or ANSI escapes
clean_text = arbitrary_string.filter(
    lambda s: not any(c in s for c in INJECTION_CHARS) and "\x1b" not in s
)

# Audit log entry strategies
timestamp_str = st.from_regex(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", fullmatch=True)
event_type = st.sampled_from(["approval", "denial", "circuit_breaker_trip"])
agent_name = st.from_regex(r"[a-zA-Z_-]{1,30}", fullmatch=True)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestSanitizeLogInputRemovesControlChars:
    """sanitize_log_input must remove all injection characters."""

    @example(text="test\x00injection")
    @example(text="newline\ninjection")
    @given(text=string_with_injection)
    def test_no_control_chars_in_output(self, text: str) -> None:
        """Output contains no injection characters (except tab)."""
        result = sanitize_log_input(text)
        for char in INJECTION_CHARS:
            assert char not in result


class TestSanitizeLogInputRemovesAnsi:
    """sanitize_log_input must remove ANSI escape sequences."""

    @example(text="normal\x1b[31mred\x1b[0m")
    @example(text="\x1b[1;32mbold green\x1b[0m")
    @given(text=string_with_ansi)
    def test_no_ansi_in_output(self, text: str) -> None:
        """Output contains no ANSI escape sequences."""
        result = sanitize_log_input(text)
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
        assert not ansi_pattern.search(result)


class TestSanitizeLogInputNeverCrashes:
    """sanitize_log_input must handle any string without crashing."""

    @example(text="")
    @example(text="normal text")
    @example(text="\x00\x01\x02\x03")
    @given(text=arbitrary_string)
    def test_never_crashes(self, text: str) -> None:
        """Any string input returns a string result."""
        result = sanitize_log_input(text)
        assert isinstance(result, str)


class TestSanitizeLogInputPreservesCleanText:
    """sanitize_log_input must not alter already-clean text."""

    @example(text="hello world")
    @example(text="pytest tests/ --verbose")
    @given(text=clean_text)
    def test_clean_text_preserved(self, text: str) -> None:
        """Text without injection chars passes through unchanged."""
        result = sanitize_log_input(text)
        assert result == text


class TestAuditLogEntryToDictExcludesNone:
    """AuditLogEntry.to_dict must exclude None values."""

    @example(ts="2025-01-01T00:00:00Z", event="approval", agent="test")
    @example(ts="2025-01-01T00:00:00Z", event="denial", agent="reviewer")
    @given(ts=timestamp_str, event=event_type, agent=agent_name)
    def test_no_none_values_in_dict(self, ts: str, event: str, agent: str) -> None:
        """to_dict output has no None values."""
        entry = AuditLogEntry(timestamp=ts, event=event, agent=agent)
        result = entry.to_dict()
        for key, value in result.items():
            assert value is not None
        # Required fields are always present
        assert "timestamp" in result
        assert "event" in result
        assert "agent" in result
