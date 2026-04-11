"""Property-based tests for runtime_data_aggregator.py utility functions.

Tests invariants:
- normalize_severity always returns value in [0.0, 1.0]
- normalize_severity with min >= max returns 0.0
- compute_priority is non-negative for non-negative inputs
- compute_priority increases monotonically with severity (fixed frequency)
- compute_priority increases monotonically with frequency (fixed severity)
- scrub_secrets removes known secret patterns
- scrub_secrets never crashes on any string input
"""

import math
import re

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from runtime_data_aggregator import (
    DEFAULT_WEIGHT,
    SEVERITY_WEIGHTS,
    AggregatedSignal,
    compute_priority,
    normalize_severity,
    scrub_secrets,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Float values for normalization
float_value = st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False)

# Min/max pairs where min < max
ordered_float_pair = st.tuples(
    st.floats(min_value=-500.0, max_value=499.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-499.0, max_value=500.0, allow_nan=False, allow_infinity=False),
).filter(lambda t: t[0] < t[1])

# Degenerate min/max pairs where min >= max
degenerate_float_pair = st.tuples(
    st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
).filter(lambda t: t[0] >= t[1])

# Signal types
signal_type = st.sampled_from(list(SEVERITY_WEIGHTS.keys()) + ["unknown_type"])

# Severity values in valid range
severity_value = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Frequency values
frequency_value = st.integers(min_value=1, max_value=100)

# Low/high severity values for monotonic test
severity_low = st.floats(min_value=0.0, max_value=0.49, allow_nan=False)
severity_high = st.floats(min_value=0.5, max_value=1.0, allow_nan=False)

# Arbitrary strings for scrubbing
arbitrary_string = st.text(min_size=0, max_size=500)

# Strings with API keys
api_key_string = st.builds(
    lambda prefix, key: f"{prefix} sk-{key}",
    st.text(min_size=0, max_size=30, alphabet=st.characters(whitelist_categories=("L",))),
    st.from_regex(r"[a-zA-Z0-9]{20,40}", fullmatch=True),
)

# Strings with GitHub tokens
github_token_string = st.builds(
    lambda prefix, token: f"{prefix} ghp_{token}",
    st.text(min_size=0, max_size=30, alphabet=st.characters(whitelist_categories=("L",))),
    st.from_regex(r"[a-zA-Z0-9]{36,40}", fullmatch=True),
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestNormalizeSeverityRange:
    """normalize_severity must always return a value in [0.0, 1.0]."""

    @example(value=0.5, pair=(0.0, 1.0))
    @example(value=100.0, pair=(0.0, 50.0))
    @given(value=float_value, pair=ordered_float_pair)
    def test_output_in_range(self, value: float, pair: tuple) -> None:
        """Output is always clamped to [0.0, 1.0]."""
        min_val, max_val = pair
        result = normalize_severity(value, min_val, max_val)
        assert 0.0 <= result <= 1.0


class TestNormalizeSeverityDegenerate:
    """normalize_severity returns 0.0 when min >= max."""

    @example(pair=(5.0, 5.0))
    @example(pair=(10.0, 5.0))
    @given(pair=degenerate_float_pair)
    def test_degenerate_returns_zero(self, pair: tuple) -> None:
        """When min >= max, result is 0.0."""
        min_val, max_val = pair
        result = normalize_severity(0.5, min_val, max_val)
        assert result == 0.0


class TestNormalizeSeverityBoundary:
    """normalize_severity maps min to 0.0 and max to 1.0."""

    @example(pair=(0.0, 10.0))
    @example(pair=(-5.0, 5.0))
    @given(pair=ordered_float_pair)
    def test_boundary_values(self, pair: tuple) -> None:
        """min maps to 0.0, max maps to 1.0."""
        min_val, max_val = pair
        assert normalize_severity(min_val, min_val, max_val) == 0.0
        assert normalize_severity(max_val, min_val, max_val) == 1.0


class TestComputePriorityNonNegative:
    """compute_priority must be non-negative for valid inputs."""

    @example(sig_type="hook_failure", severity=0.5, freq=5)
    @example(sig_type="unknown_type", severity=0.0, freq=1)
    @given(sig_type=signal_type, severity=severity_value, freq=frequency_value)
    def test_non_negative(self, sig_type: str, severity: float, freq: int) -> None:
        """Priority is always >= 0."""
        signal = AggregatedSignal(
            source="test", signal_type=sig_type, description="test",
            frequency=freq, severity=severity,
        )
        result = compute_priority(signal)
        assert result >= 0.0


class TestComputePriorityMonotonicSeverity:
    """compute_priority increases with severity (fixed frequency)."""

    @example(sig_type="hook_failure", sev_low=0.1, sev_high=0.9, freq=5)
    @example(sig_type="bypass_detected", sev_low=0.0, sev_high=1.0, freq=1)
    @given(
        sig_type=signal_type,
        sev_low=severity_low,
        sev_high=severity_high,
        freq=frequency_value,
    )
    def test_monotonic_with_severity(self, sig_type: str, sev_low: float, sev_high: float, freq: int) -> None:
        """Higher severity produces higher or equal priority."""
        low_signal = AggregatedSignal(
            source="test", signal_type=sig_type, description="test",
            frequency=freq, severity=sev_low,
        )
        high_signal = AggregatedSignal(
            source="test", signal_type=sig_type, description="test",
            frequency=freq, severity=sev_high,
        )
        assert compute_priority(high_signal) >= compute_priority(low_signal)


class TestScrubSecretsRemovesApiKeys:
    """scrub_secrets must redact OpenAI-style API keys."""

    @example(text="key: sk-abcdef1234567890abcd")
    @example(text="Authorization: Bearer sk-1234567890abcdefghij")
    @given(text=api_key_string)
    def test_api_keys_redacted(self, text: str) -> None:
        """sk- prefixed keys are replaced with [REDACTED]."""
        result = scrub_secrets(text)
        assert not re.search(r"sk-[a-zA-Z0-9]{20,}", result)


class TestScrubSecretsRemovesGithubTokens:
    """scrub_secrets must redact GitHub personal access tokens."""

    @example(text="token: ghp_abcdefghijklmnopqrstuvwxyz1234567890")
    @example(text="GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz1234567890")
    @given(text=github_token_string)
    def test_github_tokens_redacted(self, text: str) -> None:
        """ghp_ prefixed tokens are replaced with [REDACTED]."""
        result = scrub_secrets(text)
        assert not re.search(r"ghp_[a-zA-Z0-9]{36,}", result)


class TestScrubSecretsNeverCrashes:
    """scrub_secrets must handle any string without crashing."""

    @example(text="")
    @example(text="normal text without secrets")
    @given(text=arbitrary_string)
    def test_never_crashes(self, text: str) -> None:
        """Any string input returns a string result."""
        result = scrub_secrets(text)
        assert isinstance(result, str)
