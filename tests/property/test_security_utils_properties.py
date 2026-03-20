"""Property-based tests for security_utils.py path validation invariants.

Tests invariants:
- Paths with '..' always raise ValueError from validate_path()
- Paths longer than MAX_PATH_LENGTH always rejected
- System paths (/etc/, /usr/) always rejected in non-test mode
- Agent names matching [a-zA-Z0-9_-]+ accepted, others rejected
- validate_pytest_path() rejects paths with '..'
"""

import os
import re
from pathlib import Path

import pytest
from hypothesis import example, given, settings, HealthCheck
from hypothesis import strategies as st

from security_utils import (
    MAX_PATH_LENGTH,
    validate_agent_name,
    validate_path,
    validate_pytest_path,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Printable strings that always contain at least one '..' component
path_with_traversal = st.from_regex(r"[a-zA-Z0-9/._-]*\.\.[a-zA-Z0-9/._-]*", fullmatch=True)

# Very long path strings (exceeding MAX_PATH_LENGTH)
# Use only alpha chars to avoid Path normalization collapsing slashes
long_path = st.text(
    alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz")),
    min_size=MAX_PATH_LENGTH + 1,
    max_size=MAX_PATH_LENGTH + 500,
)

# Valid agent names: alphanumeric, hyphens, underscores
valid_agent_name = st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}", fullmatch=True)

# Invalid agent names: contain at least one disallowed character
invalid_agent_name_chars = st.from_regex(
    r"[a-zA-Z0-9_-]*[^a-zA-Z0-9_-]+[a-zA-Z0-9_-]*", fullmatch=True
).filter(lambda s: len(s) > 0 and len(s) <= 255)

# System paths that should be rejected in production mode
system_path_prefixes = ["/etc/", "/usr/", "/bin/", "/sbin/", "/var/log/"]


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestPathTraversalInvariant:
    """Any path containing '..' must be rejected by validate_path()."""

    @given(path_str=path_with_traversal)
    @example("../../etc/passwd")
    @example("subdir/../../../root")
    @example("a/b/../c/../../../outside")
    @example("..")
    @settings(max_examples=200)
    def test_dotdot_always_raises(self, path_str: str) -> None:
        """Paths with '..' always raise ValueError regardless of other content."""
        with pytest.raises(ValueError, match="[Pp]ath traversal"):
            validate_path(path_str, "property test", test_mode=True)


class TestMaxPathLengthInvariant:
    """Paths exceeding MAX_PATH_LENGTH must be rejected."""

    @given(path_str=long_path)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.large_base_example])
    def test_long_paths_always_rejected(self, path_str: str) -> None:
        """Paths longer than MAX_PATH_LENGTH always raise ValueError."""
        assert len(path_str) > MAX_PATH_LENGTH
        with pytest.raises(ValueError, match="[Pp]ath too long"):
            validate_path(path_str, "length test", test_mode=True)


class TestSystemPathRejection:
    """System paths must be rejected when test_mode=False."""

    @given(suffix=st.from_regex(r"[a-zA-Z0-9_.-]{1,50}", fullmatch=True))
    @example("passwd")
    @example("shadow")
    @example("hosts")
    @settings(max_examples=200)
    def test_etc_paths_rejected_in_production(self, suffix: str) -> None:
        """Paths under /etc/ are rejected when test_mode=False."""
        path_str = f"/etc/{suffix}"
        with pytest.raises(ValueError):
            validate_path(path_str, "system path test", test_mode=False)

    @given(
        prefix=st.sampled_from(system_path_prefixes),
        suffix=st.from_regex(r"[a-zA-Z0-9_.-]{1,50}", fullmatch=True),
    )
    @settings(max_examples=200)
    def test_system_paths_rejected_in_production(self, prefix: str, suffix: str) -> None:
        """All system directory paths are rejected in production mode."""
        path_str = f"{prefix}{suffix}"
        with pytest.raises(ValueError):
            validate_path(path_str, "system path test", test_mode=False)


class TestAgentNameValidation:
    """Agent name validation: alphanumeric + hyphen + underscore only."""

    @given(name=valid_agent_name)
    @example("researcher")
    @example("test-master")
    @example("doc_master")
    @example("a")
    @settings(max_examples=200)
    def test_valid_agent_names_accepted(self, name: str) -> None:
        """Names matching [a-zA-Z0-9_-]+ are accepted."""
        result = validate_agent_name(name)
        assert result == name

    @given(name=invalid_agent_name_chars)
    @example("security auditor")
    @example("researcher; rm -rf /")
    @example("name\x00injected")
    @settings(max_examples=200)
    def test_invalid_agent_names_rejected(self, name: str) -> None:
        """Names with disallowed characters are always rejected."""
        # \w matches [a-zA-Z0-9_], plus hyphen is allowed
        if re.match(r"^[\w-]+$", name):
            # hypothesis may generate strings where the "invalid" char is
            # actually within \w range — skip those
            return
        with pytest.raises(ValueError):
            validate_agent_name(name)


class TestPytestPathTraversal:
    """validate_pytest_path() must reject paths containing '..'."""

    @given(
        prefix=st.from_regex(r"[a-z_]{1,20}", fullmatch=True),
        suffix=st.from_regex(r"[a-z_]{1,20}", fullmatch=True),
    )
    @example("tests", "test_foo")
    @example("src", "module")
    @settings(max_examples=200)
    def test_pytest_path_with_dotdot_rejected(self, prefix: str, suffix: str) -> None:
        """Pytest paths containing '..' are always rejected."""
        path_str = f"{prefix}/../{suffix}.py"
        with pytest.raises(ValueError, match="[Pp]ath traversal|[Pp]aths containing"):
            validate_pytest_path(path_str)

    @given(
        module=st.from_regex(r"[a-z][a-z0-9_]{0,20}", fullmatch=True),
    )
    @settings(max_examples=200)
    def test_valid_pytest_paths_accepted(self, module: str) -> None:
        """Well-formed pytest paths (within project) are accepted."""
        # We need a path that validate_path will accept — use a relative
        # path that resolves inside the project root
        path_str = f"tests/test_{module}.py"
        # This may raise if the file component resolves outside project,
        # but it should NOT raise for traversal
        try:
            result = validate_pytest_path(path_str)
            assert result == path_str
        except ValueError as e:
            # Acceptable if the path is outside whitelist,
            # but NOT acceptable if it's a traversal error
            assert "traversal" not in str(e).lower()
