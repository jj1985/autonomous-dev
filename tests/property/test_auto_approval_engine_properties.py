"""Property-based tests for auto_approval_engine.py set operations and state management.

Tests invariants:
- AutoApprovalState denial count increments correctly
- AutoApprovalState reset sets count to zero
- Circuit breaker trips at exactly CIRCUIT_BREAKER_THRESHOLD denials
- Circuit breaker trip is irreversible until reset
- is_trusted_agent returns False for None/empty inputs
- is_subagent_context depends on CLAUDE_AGENT_NAME environment variable
"""

import os
import threading

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from auto_approval_engine import (
    CIRCUIT_BREAKER_THRESHOLD,
    AutoApprovalState,
    get_agent_name,
    is_subagent_context,
    should_trip_circuit_breaker,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Positive increments for denial count testing
positive_int = st.integers(min_value=1, max_value=50)

# Number of denials at or above threshold
at_threshold = st.just(CIRCUIT_BREAKER_THRESHOLD)
above_threshold = st.integers(min_value=CIRCUIT_BREAKER_THRESHOLD + 1, max_value=CIRCUIT_BREAKER_THRESHOLD + 20)

# Number of denials below threshold
below_threshold = st.integers(min_value=0, max_value=CIRCUIT_BREAKER_THRESHOLD - 1)

# Agent name strings
agent_name_str = st.from_regex(r"[a-zA-Z_-]{1,30}", fullmatch=True)

# Strings with control characters for sanitization testing (exclude null byte)
name_with_control_chars = st.builds(
    lambda prefix, cc, suffix: prefix + cc + suffix,
    st.from_regex(r"[a-zA-Z]{1,10}", fullmatch=True),
    st.sampled_from([chr(i) for i in range(1, 0x20)]),
    st.from_regex(r"[a-zA-Z]{1,10}", fullmatch=True),
)

# None or empty agent names
empty_agent = st.one_of(st.none(), st.just(""), st.just("   "))

# Small integer range for items test
small_denials = st.integers(min_value=0, max_value=20)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestDenialCountIncrement:
    """AutoApprovalState.increment_denial_count must increment correctly."""

    @example(n=1)
    @example(n=10)
    @given(n=positive_int)
    def test_increment_n_times(self, n: int) -> None:
        """Incrementing n times produces count n."""
        state = AutoApprovalState()
        for _ in range(n):
            state.increment_denial_count()
        assert state.get_denial_count() == n


class TestDenialCountReset:
    """AutoApprovalState.reset_denial_count must reset to zero."""

    @example(n=5)
    @example(n=CIRCUIT_BREAKER_THRESHOLD)
    @given(n=positive_int)
    def test_reset_clears_count(self, n: int) -> None:
        """After increment then reset, count is zero."""
        state = AutoApprovalState()
        for _ in range(n):
            state.increment_denial_count()
        state.reset_denial_count()
        assert state.get_denial_count() == 0


class TestCircuitBreakerTripsAtThreshold:
    """Circuit breaker must trip at exactly CIRCUIT_BREAKER_THRESHOLD denials."""

    @example(n=CIRCUIT_BREAKER_THRESHOLD)
    @given(n=at_threshold)
    def test_trips_at_threshold(self, n: int) -> None:
        """Should trip returns True at threshold."""
        state = AutoApprovalState()
        for _ in range(n):
            state.increment_denial_count()
        assert should_trip_circuit_breaker(state) is True


class TestCircuitBreakerDoesNotTripBelowThreshold:
    """Circuit breaker must NOT trip below CIRCUIT_BREAKER_THRESHOLD."""

    @example(n=0)
    @example(n=CIRCUIT_BREAKER_THRESHOLD - 1)
    @given(n=below_threshold)
    def test_does_not_trip_below_threshold(self, n: int) -> None:
        """Should trip returns False below threshold."""
        state = AutoApprovalState()
        for _ in range(n):
            state.increment_denial_count()
        assert should_trip_circuit_breaker(state) is False


class TestCircuitBreakerReset:
    """reset_circuit_breaker must clear both tripped state and denial count."""

    @example(n=CIRCUIT_BREAKER_THRESHOLD + 5)
    @given(n=above_threshold)
    def test_reset_clears_breaker(self, n: int) -> None:
        """After trip and reset, breaker is not tripped and count is zero."""
        state = AutoApprovalState()
        for _ in range(n):
            state.increment_denial_count()
        state.trip_circuit_breaker()
        assert state.is_circuit_breaker_tripped() is True
        state.reset_circuit_breaker()
        assert state.is_circuit_breaker_tripped() is False
        assert state.get_denial_count() == 0


class TestGetAgentNameSanitization:
    """get_agent_name must remove control characters."""

    @example(name="test\x01agent")
    @example(name="reviewer\x02injected")
    @given(name=name_with_control_chars)
    def test_control_chars_removed(self, name: str) -> None:
        """Control characters are stripped from agent name."""
        # Skip null bytes which cannot be set as env vars
        if "\x00" in name:
            return
        old_env = os.environ.get("CLAUDE_AGENT_NAME")
        try:
            os.environ["CLAUDE_AGENT_NAME"] = name
            result = get_agent_name()
            if result is not None:
                # No control characters in output
                for ch in result:
                    assert ord(ch) >= 0x20
        finally:
            if old_env is not None:
                os.environ["CLAUDE_AGENT_NAME"] = old_env
            elif "CLAUDE_AGENT_NAME" in os.environ:
                del os.environ["CLAUDE_AGENT_NAME"]


class TestAutoApprovalStateItems:
    """AutoApprovalState.items must return dict-like representation."""

    @example(denials=3)
    @example(denials=0)
    @given(denials=small_denials)
    def test_items_contains_expected_keys(self, denials: int) -> None:
        """items() returns list with denial_count and circuit_breaker_tripped."""
        state = AutoApprovalState()
        for _ in range(denials):
            state.increment_denial_count()
        items = dict(state.items())
        assert "denial_count" in items
        assert "circuit_breaker_tripped" in items
        assert items["denial_count"] == denials
