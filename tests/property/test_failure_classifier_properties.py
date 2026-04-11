"""Property-based tests for failure_classifier.py classification and sanitization.

Tests invariants:
- classify_failure always returns a FailureType enum value
- Transient patterns always classify as TRANSIENT
- Permanent patterns always classify as PERMANENT
- None/empty always classify as PERMANENT (safe default)
- sanitize_error_message never contains newlines
- sanitize_error_message respects MAX_ERROR_MESSAGE_LENGTH
- sanitize_feature_name removes path traversal sequences
"""

import re

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from failure_classifier import (
    MAX_ERROR_MESSAGE_LENGTH,
    FailureType,
    classify_failure,
    is_permanent_error,
    is_transient_error,
    sanitize_error_message,
    sanitize_feature_name,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Known transient error prefixes
transient_prefix = st.sampled_from([
    "ConnectionError", "TimeoutError", "RateLimitError",
    "NetworkError", "TemporaryFailure",
])

# Known permanent error prefixes
permanent_prefix = st.sampled_from([
    "SyntaxError", "ImportError", "TypeError",
    "NameError", "AttributeError", "ValueError",
])

# Error message suffix
error_suffix = st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")))

# Transient error messages
transient_message = st.builds(
    lambda prefix, suffix: f"{prefix}: {suffix}",
    transient_prefix,
    error_suffix,
)

# Permanent error messages
permanent_message = st.builds(
    lambda prefix, suffix: f"{prefix}: {suffix}",
    permanent_prefix,
    error_suffix,
)

# Arbitrary strings for crash testing
arbitrary_string = st.text(min_size=0, max_size=2000)

# Strings with newlines (for sanitization testing)
string_with_newlines = st.builds(
    lambda parts: "\n".join(parts),
    st.lists(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L",))), min_size=2, max_size=5),
)

# Strings with path traversal
path_traversal_string = st.builds(
    lambda prefix, suffix: f"{prefix}../{suffix}",
    st.text(min_size=0, max_size=20, alphabet=st.characters(whitelist_categories=("L",))),
    st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))),
)

# None or empty strategy
none_or_empty = st.one_of(st.none(), st.just(""))


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestClassifyFailureTransient:
    """Transient errors must always classify as TRANSIENT."""

    @example(msg="ConnectionError: Failed to connect")
    @example(msg="TimeoutError: Request timed out")
    @given(msg=transient_message)
    def test_transient_classified_correctly(self, msg: str) -> None:
        """Known transient patterns always return TRANSIENT."""
        result = classify_failure(msg)
        assert result == FailureType.TRANSIENT


class TestClassifyFailurePermanent:
    """Permanent errors must always classify as PERMANENT."""

    @example(msg="SyntaxError: invalid syntax")
    @example(msg="ImportError: No module named 'foo'")
    @given(msg=permanent_message)
    def test_permanent_classified_correctly(self, msg: str) -> None:
        """Known permanent patterns always return PERMANENT."""
        result = classify_failure(msg)
        assert result == FailureType.PERMANENT


class TestClassifyFailureSafeDefault:
    """None/empty inputs must default to PERMANENT (safe default)."""

    @example(msg=None)
    @example(msg="")
    @given(msg=none_or_empty)
    def test_none_or_empty_defaults_permanent(self, msg) -> None:
        """None or empty string always returns PERMANENT."""
        result = classify_failure(msg)
        assert result == FailureType.PERMANENT


class TestClassifyFailureAlwaysReturnsEnum:
    """classify_failure must always return a FailureType enum value."""

    @example(msg="WeirdUnknownError: something happened")
    @example(msg="just some random text")
    @given(msg=arbitrary_string)
    def test_always_returns_failure_type(self, msg: str) -> None:
        """Any string input returns a valid FailureType."""
        result = classify_failure(msg)
        assert isinstance(result, FailureType)
        assert result in (FailureType.TRANSIENT, FailureType.PERMANENT)


class TestSanitizeErrorMessageNoNewlines:
    """sanitize_error_message must remove all newlines."""

    @example(msg="Error\nFAKE LOG: Admin access")
    @example(msg="line1\r\nline2")
    @given(msg=string_with_newlines)
    def test_no_newlines_in_output(self, msg: str) -> None:
        """Output never contains newline or carriage return characters."""
        result = sanitize_error_message(msg)
        assert "\n" not in result
        assert "\r" not in result


class TestSanitizeErrorMessageLength:
    """sanitize_error_message must respect MAX_ERROR_MESSAGE_LENGTH."""

    @example(msg="X" * 2000)
    @example(msg="short")
    @given(msg=arbitrary_string)
    def test_output_length_bounded(self, msg: str) -> None:
        """Output is never longer than MAX_ERROR_MESSAGE_LENGTH."""
        result = sanitize_error_message(msg)
        assert len(result) <= MAX_ERROR_MESSAGE_LENGTH


class TestSanitizeErrorMessageNone:
    """sanitize_error_message must return empty string for None/empty."""

    @example(msg=None)
    @example(msg="")
    @given(msg=none_or_empty)
    def test_none_returns_empty(self, msg) -> None:
        """None or empty input returns empty string."""
        result = sanitize_error_message(msg)
        assert result == ""


class TestSanitizeFeatureNameTraversal:
    """sanitize_feature_name must remove path traversal sequences."""

    @example(name="../../etc/passwd")
    @example(name="normal../sneaky")
    @given(name=path_traversal_string)
    def test_traversal_removed(self, name: str) -> None:
        """Path traversal sequences are stripped from output."""
        result = sanitize_feature_name(name)
        assert "../" not in result


class TestIsTransientAndPermanentMutualExclusivity:
    """is_transient_error and is_permanent_error should be consistent with classify."""

    @example(msg="ConnectionError: test")
    @example(msg="SyntaxError: test")
    @given(msg=arbitrary_string)
    def test_classify_consistent_with_helpers(self, msg: str) -> None:
        """If is_transient_error is True, classify must return TRANSIENT."""
        if is_transient_error(msg):
            assert classify_failure(msg) == FailureType.TRANSIENT
        elif is_permanent_error(msg):
            assert classify_failure(msg) == FailureType.PERMANENT
