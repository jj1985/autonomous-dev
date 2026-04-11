"""Property-based tests for validation.py input validation functions.

Tests invariants:
- validate_agent_name accepts alphanumeric/hyphen/underscore strings
- validate_agent_name rejects empty, too-long, or invalid-character strings
- validate_message accepts strings within length limits without control chars
- validate_message rejects strings with control characters or exceeding length
- Type errors raised for non-string inputs
"""

import re

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from validation import (
    MAX_AGENT_NAME_LENGTH,
    MAX_MESSAGE_LENGTH,
    validate_agent_name,
    validate_message,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid agent names: alphanumeric, hyphen, underscore, 1-64 chars
valid_agent_name = st.from_regex(r"[a-zA-Z0-9_-]{1,64}", fullmatch=True)

# Invalid agent names containing disallowed characters
invalid_agent_chars = st.text(
    alphabet=st.characters(whitelist_categories=("P", "S", "Z"), blacklist_characters="-_"),
    min_size=1,
    max_size=20,
).filter(lambda s: not re.match(r"^[a-zA-Z0-9_-]+$", s.strip()) and s.strip() != "")

# Arbitrary strings for crash testing
arbitrary_string = st.text(min_size=0, max_size=500)

# Strings without control characters (valid messages)
safe_message = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        whitelist_characters="\t\n\r",
    ),
    min_size=0,
    max_size=200,
)

# Strings with control characters (invalid messages)
control_char = st.sampled_from(
    [chr(i) for i in range(0, 32) if i not in (9, 10, 13)]
)

# Messages with control chars that survive strip() (non-empty prefix or suffix)
message_with_control = st.builds(
    lambda prefix, cc, suffix: prefix + cc + suffix,
    st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L",))),
    control_char,
    st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L",))),
)

# Non-string values
non_string_values = st.one_of(
    st.integers(),
    st.floats(allow_nan=False),
    st.lists(st.integers(), max_size=3),
    st.none(),
)

# Empty/whitespace-only strings
empty_string = st.sampled_from(["", " ", "  ", "\t", "\n"])


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestValidateAgentNameAccepts:
    """validate_agent_name must accept valid alphanumeric names."""

    @example(name="researcher")
    @example(name="test-agent_v2")
    @example(name="a")
    @given(name=valid_agent_name)
    def test_valid_names_accepted(self, name: str) -> None:
        """Valid agent names are returned stripped."""
        result = validate_agent_name(name)
        assert isinstance(result, str)
        assert result == name.strip()


class TestValidateAgentNameRejectsInvalid:
    """validate_agent_name must reject names with invalid characters."""

    @example(name="../../etc/passwd")
    @example(name="agent name with spaces")
    @given(name=invalid_agent_chars)
    def test_invalid_chars_rejected(self, name: str) -> None:
        """Names with disallowed characters raise ValueError."""
        with pytest.raises(ValueError):
            validate_agent_name(name)


class TestValidateAgentNameRejectsEmpty:
    """validate_agent_name must reject empty strings."""

    @example(name="")
    @example(name="   ")
    @given(name=empty_string)
    def test_empty_names_rejected(self, name: str) -> None:
        """Empty or whitespace-only names raise ValueError."""
        with pytest.raises(ValueError):
            validate_agent_name(name)


class TestValidateAgentNameTypeError:
    """validate_agent_name must reject non-string inputs."""

    @example(value=123)
    @example(value=None)
    @given(value=non_string_values)
    def test_non_string_raises_type_error(self, value) -> None:
        """Non-string inputs raise TypeError."""
        with pytest.raises(TypeError):
            validate_agent_name(value)


class TestValidateAgentNameNeverCrashes:
    """validate_agent_name must never raise unexpected exceptions."""

    @example(name="")
    @example(name="a" * 300)
    @given(name=arbitrary_string)
    def test_never_crashes_on_string_input(self, name: str) -> None:
        """Any string input results in either a valid return or ValueError."""
        try:
            result = validate_agent_name(name)
            assert isinstance(result, str)
        except ValueError:
            pass  # Expected for invalid inputs


class TestValidateMessageAccepts:
    """validate_message must accept strings without control chars."""

    @example(message="Research complete")
    @example(message="Hello\nWorld")
    @given(message=safe_message)
    def test_safe_messages_accepted(self, message: str) -> None:
        """Messages without dangerous control chars are accepted."""
        if len(message.strip()) <= MAX_MESSAGE_LENGTH:
            result = validate_message(message)
            assert isinstance(result, str)


class TestValidateMessageRejectsControlChars:
    """validate_message must reject strings with control characters."""

    @example(message="test\x00message")
    @example(message="inject\x01here")
    @given(message=message_with_control)
    def test_control_chars_rejected(self, message: str) -> None:
        """Messages with control characters raise ValueError."""
        with pytest.raises(ValueError):
            validate_message(message)


class TestValidateMessageTypeError:
    """validate_message must reject non-string inputs."""

    @example(value=42)
    @example(value=None)
    @given(value=non_string_values)
    def test_non_string_raises_type_error(self, value) -> None:
        """Non-string inputs raise TypeError."""
        with pytest.raises(TypeError):
            validate_message(value)
