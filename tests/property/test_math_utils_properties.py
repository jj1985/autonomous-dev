"""Property-based tests for math_utils.py Fibonacci calculator.

Tests invariants:
- F(0) = 0, F(1) = 1 for all methods
- F(n) = F(n-1) + F(n-2) for n >= 2 (recurrence relation)
- All three methods produce identical results
- Negative inputs raise InvalidInputError
- Inputs > MAX_FIBONACCI_INPUT raise InvalidInputError
- Non-integer inputs raise TypeError
- Invalid method names raise MethodNotSupportedError
"""

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from math_utils import (
    MAX_FIBONACCI_INPUT,
    VALID_METHODS,
    FibonacciError,
    InvalidInputError,
    MethodNotSupportedError,
    calculate_fibonacci,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Small non-negative integers (fast computation)
small_n = st.integers(min_value=0, max_value=30)

# Recurrence-testable integers (need n >= 2)
recurrence_n = st.integers(min_value=2, max_value=30)

# Valid method names
valid_method = st.sampled_from(sorted(VALID_METHODS))

# Invalid method names
invalid_method = st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))).filter(
    lambda s: s not in VALID_METHODS
)

# Negative integers
negative_int = st.integers(min_value=-10000, max_value=-1)

# Integers above maximum
above_max = st.integers(min_value=MAX_FIBONACCI_INPUT + 1, max_value=MAX_FIBONACCI_INPUT + 100)

# Non-integer values
non_integer = st.one_of(
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(min_size=1, max_size=10),
    st.none(),
)

# Integers >= 1 for monotonic test
positive_n = st.integers(min_value=1, max_value=30)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestBaseCases:
    """F(0) = 0 and F(1) = 1 for all methods."""

    @example(method="iterative")
    @example(method="recursive")
    @example(method="matrix")
    @given(method=valid_method)
    def test_f0_is_zero(self, method: str) -> None:
        """F(0) = 0 regardless of method."""
        assert calculate_fibonacci(0, method=method) == 0

    @example(method="iterative")
    @example(method="matrix")
    @given(method=valid_method)
    def test_f1_is_one(self, method: str) -> None:
        """F(1) = 1 regardless of method."""
        assert calculate_fibonacci(1, method=method) == 1


class TestRecurrenceRelation:
    """F(n) = F(n-1) + F(n-2) for all n >= 2 and all methods."""

    @example(n=2, method="iterative")
    @example(n=10, method="matrix")
    @given(n=recurrence_n, method=valid_method)
    def test_recurrence_holds(self, n: int, method: str) -> None:
        """The Fibonacci recurrence relation holds."""
        fn = calculate_fibonacci(n, method=method)
        fn1 = calculate_fibonacci(n - 1, method=method)
        fn2 = calculate_fibonacci(n - 2, method=method)
        assert fn == fn1 + fn2


class TestAllMethodsAgree:
    """All three methods must produce identical results."""

    @example(n=0)
    @example(n=10)
    @example(n=20)
    @given(n=small_n)
    def test_methods_agree(self, n: int) -> None:
        """iterative, recursive, and matrix all return the same value."""
        iterative = calculate_fibonacci(n, method="iterative")
        recursive = calculate_fibonacci(n, method="recursive")
        matrix = calculate_fibonacci(n, method="matrix")
        assert iterative == recursive == matrix


class TestNegativeInputRejected:
    """Negative inputs must raise InvalidInputError."""

    @example(n=-1)
    @example(n=-100)
    @given(n=negative_int)
    def test_negative_rejected(self, n: int) -> None:
        """Negative inputs raise InvalidInputError."""
        with pytest.raises(InvalidInputError):
            calculate_fibonacci(n)


class TestAboveMaxRejected:
    """Inputs above MAX_FIBONACCI_INPUT must raise InvalidInputError."""

    @example(n=MAX_FIBONACCI_INPUT + 1)
    @example(n=MAX_FIBONACCI_INPUT + 100)
    @given(n=above_max)
    def test_above_max_rejected(self, n: int) -> None:
        """Inputs exceeding maximum raise InvalidInputError."""
        with pytest.raises(InvalidInputError):
            calculate_fibonacci(n)


class TestNonIntegerRejected:
    """Non-integer inputs must raise TypeError."""

    @example(value=3.14)
    @example(value="ten")
    @given(value=non_integer)
    def test_non_integer_rejected(self, value) -> None:
        """Non-integer inputs raise TypeError."""
        with pytest.raises(TypeError):
            calculate_fibonacci(value)


class TestInvalidMethodRejected:
    """Invalid method names must raise MethodNotSupportedError."""

    @example(method="fast")
    @example(method="dynamic")
    @given(method=invalid_method)
    def test_invalid_method_rejected(self, method: str) -> None:
        """Invalid method names raise MethodNotSupportedError."""
        with pytest.raises(MethodNotSupportedError):
            calculate_fibonacci(5, method=method)


class TestFibonacciNonNegative:
    """Fibonacci numbers are always non-negative."""

    @example(n=0)
    @example(n=15)
    @given(n=small_n)
    def test_result_non_negative(self, n: int) -> None:
        """F(n) >= 0 for all valid n."""
        result = calculate_fibonacci(n)
        assert result >= 0


class TestFibonacciMonotonic:
    """Fibonacci sequence is non-decreasing."""

    @example(n=5)
    @example(n=20)
    @given(n=positive_n)
    def test_monotonic(self, n: int) -> None:
        """F(n) >= F(n-1) for all n >= 1."""
        assert calculate_fibonacci(n) >= calculate_fibonacci(n - 1)
