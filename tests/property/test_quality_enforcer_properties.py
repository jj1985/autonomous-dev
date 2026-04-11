"""Property-based tests for quality_persistence_enforcer.py enforcement logic.

Tests invariants:
- enforce_completion_gate passes when failed=0 and coverage >= 80
- enforce_completion_gate fails when failed > 0
- enforce_completion_gate fails when coverage < 80
- enforce_completion_gate raises QualityGateError when attempt > MAX_RETRY_ATTEMPTS
- retry_with_different_approach returns None when attempt > MAX_RETRY_ATTEMPTS
- retry_with_different_approach returns RetryStrategy for valid attempts
- should_close_issue returns True only when completed AND quality_gate_passed
- EnforcementResult.to_dict roundtrip preserves all fields
"""

import json

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from quality_persistence_enforcer import (
    COVERAGE_THRESHOLD,
    MAX_RETRY_ATTEMPTS,
    CompletionSummary,
    EnforcementResult,
    QualityGateError,
    RetryStrategy,
    enforce_completion_gate,
    retry_with_different_approach,
    should_close_issue,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Feature indices
feature_index = st.integers(min_value=0, max_value=100)

# Valid attempt numbers (1 to MAX_RETRY_ATTEMPTS)
valid_attempt = st.integers(min_value=1, max_value=MAX_RETRY_ATTEMPTS)

# Invalid attempt numbers (beyond max)
invalid_attempt = st.integers(min_value=MAX_RETRY_ATTEMPTS + 1, max_value=MAX_RETRY_ATTEMPTS + 10)

# Passing test results (all pass, good coverage)
passing_test_results = st.builds(
    lambda total, coverage: {
        "total": total,
        "passed": total,
        "failed": 0,
        "skipped": 0,
        "coverage": coverage,
    },
    st.integers(min_value=1, max_value=500),
    st.floats(min_value=COVERAGE_THRESHOLD, max_value=100.0),
)

# Failing test results (some failures)
failing_test_results = st.builds(
    lambda total, failed, coverage: {
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "skipped": 0,
        "coverage": coverage,
    },
    st.integers(min_value=2, max_value=500),
    st.integers(min_value=1, max_value=100),
    st.floats(min_value=0.0, max_value=100.0),
)

# Low coverage test results (pass but low coverage)
low_coverage_results = st.builds(
    lambda total, coverage: {
        "total": total,
        "passed": total,
        "failed": 0,
        "skipped": 0,
        "coverage": coverage,
    },
    st.integers(min_value=1, max_value=500),
    st.floats(min_value=0.0, max_value=COVERAGE_THRESHOLD - 0.01),
)

# Error messages for retry
error_message = st.text(min_size=1, max_size=200, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")))

# Feature status for close decision
completed_passed_status = st.fixed_dictionaries({
    "completed": st.just(True),
    "failed": st.just(False),
    "skipped": st.just(False),
    "quality_gate_passed": st.just(True),
})

not_completed_status = st.fixed_dictionaries({
    "completed": st.just(False),
    "failed": st.booleans(),
    "skipped": st.booleans(),
    "quality_gate_passed": st.just(False),
})

# Strategies for roundtrip test
bool_value = st.booleans()
short_text = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L",)))
small_int = st.integers(min_value=0, max_value=100)
coverage_float = st.floats(min_value=0.0, max_value=100.0)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestEnforceCompletionGatePasses:
    """Gate passes when all tests pass and coverage is sufficient."""

    @example(idx=0, results={"total": 10, "passed": 10, "failed": 0, "skipped": 0, "coverage": 85.0})
    @example(idx=5, results={"total": 1, "passed": 1, "failed": 0, "skipped": 0, "coverage": 80.0})
    @given(idx=feature_index, results=passing_test_results)
    def test_passes_when_all_good(self, idx: int, results: dict) -> None:
        """100% pass rate + sufficient coverage = gate passes."""
        result = enforce_completion_gate(idx, results)
        assert result.passed is True
        assert result.reason == "all_tests_passed"


class TestEnforceCompletionGateFailsOnTestFailures:
    """Gate fails when any test fails."""

    @example(idx=0, results={"total": 10, "passed": 8, "failed": 2, "skipped": 0, "coverage": 90.0})
    @example(idx=0, results={"total": 5, "passed": 4, "failed": 1, "skipped": 0, "coverage": 85.0})
    @given(idx=feature_index, results=failing_test_results)
    def test_fails_on_test_failures(self, idx: int, results: dict) -> None:
        """Any test failure causes gate to fail."""
        result = enforce_completion_gate(idx, results)
        assert result.passed is False
        assert result.reason == "test_failures"
        assert result.test_failures == results["failed"]


class TestEnforceCompletionGateFailsOnLowCoverage:
    """Gate fails when coverage is below threshold."""

    @example(idx=0, results={"total": 10, "passed": 10, "failed": 0, "skipped": 0, "coverage": 50.0})
    @example(idx=0, results={"total": 5, "passed": 5, "failed": 0, "skipped": 0, "coverage": 0.0})
    @given(idx=feature_index, results=low_coverage_results)
    def test_fails_on_low_coverage(self, idx: int, results: dict) -> None:
        """Coverage below threshold causes gate to fail."""
        result = enforce_completion_gate(idx, results)
        assert result.passed is False
        assert result.reason == "low_coverage"


class TestEnforceCompletionGateExceedsMaxRetries:
    """Gate raises QualityGateError when attempt exceeds MAX_RETRY_ATTEMPTS."""

    @example(idx=0, attempt=4)
    @example(idx=0, attempt=10)
    @given(idx=feature_index, attempt=invalid_attempt)
    def test_raises_on_max_retries(self, idx: int, attempt: int) -> None:
        """Exceeding max retries raises QualityGateError."""
        results = {"total": 10, "passed": 10, "failed": 0, "skipped": 0, "coverage": 90.0}
        with pytest.raises(QualityGateError):
            enforce_completion_gate(idx, results, attempt_number=attempt)


class TestRetryWithDifferentApproach:
    """retry_with_different_approach returns strategy for valid attempts, None for invalid."""

    @example(idx=0, attempt=1, err="Tests failed")
    @example(idx=0, attempt=3, err="Tests failed")
    @given(idx=feature_index, attempt=valid_attempt, err=error_message)
    def test_valid_attempt_returns_strategy(self, idx: int, attempt: int, err: str) -> None:
        """Valid attempts return a RetryStrategy."""
        result = retry_with_different_approach(idx, attempt, err)
        assert isinstance(result, RetryStrategy)
        assert result.attempt_number == attempt

    @example(idx=0, attempt=4, err="Tests failed")
    @example(idx=0, attempt=100, err="Tests failed")
    @given(idx=feature_index, attempt=invalid_attempt, err=error_message)
    def test_invalid_attempt_returns_none(self, idx: int, attempt: int, err: str) -> None:
        """Attempts beyond max return None."""
        result = retry_with_different_approach(idx, attempt, err)
        assert result is None


class TestShouldCloseIssue:
    """should_close_issue returns True only when completed AND quality_gate_passed."""

    @example(status={"completed": True, "failed": False, "skipped": False, "quality_gate_passed": True})
    @given(status=completed_passed_status)
    def test_close_when_completed_and_passed(self, status: dict) -> None:
        """Completed + quality passed = close."""
        assert should_close_issue(status) is True

    @example(status={"completed": False, "failed": True, "skipped": False, "quality_gate_passed": False})
    @given(status=not_completed_status)
    def test_no_close_when_not_completed(self, status: dict) -> None:
        """Not completed = don't close."""
        assert should_close_issue(status) is False


class TestEnforcementResultRoundtrip:
    """EnforcementResult.to_dict should be JSON-serializable."""

    @example(passed=True, reason="all_tests_passed", failures=0, coverage=90.0)
    @example(passed=False, reason="test_failures", failures=3, coverage=50.0)
    @given(
        passed=bool_value,
        reason=short_text,
        failures=small_int,
        coverage=coverage_float,
    )
    def test_to_dict_json_roundtrip(self, passed: bool, reason: str, failures: int, coverage: float) -> None:
        """to_dict output is JSON-serializable and preserves fields."""
        result = EnforcementResult(
            passed=passed, reason=reason, test_failures=failures, coverage=coverage
        )
        d = result.to_dict()
        json_str = json.dumps(d)
        loaded = json.loads(json_str)
        assert loaded["passed"] == passed
        assert loaded["reason"] == reason
        assert loaded["test_failures"] == failures
