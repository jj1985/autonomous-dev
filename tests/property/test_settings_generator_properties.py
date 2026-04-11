"""Property-based tests for settings_generator.py validation and fixing functions.

Tests invariants:
- validate_permission_patterns detects Bash(*) wildcards
- validate_permission_patterns detects missing/empty deny lists
- validate_permission_patterns returns valid=True for clean settings
- detect_outdated_patterns identifies patterns not in SAFE_COMMAND_PATTERNS
- detect_outdated_patterns returns empty list for all-safe patterns
- fix_permission_patterns removes wildcards
- Roundtrip: fix then validate produces valid result
"""

import json

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from settings_generator import (
    DEFAULT_DENY_LIST,
    SAFE_COMMAND_PATTERNS,
    ValidationResult,
    detect_outdated_patterns,
    fix_permission_patterns,
    validate_permission_patterns,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe patterns (subset from SAFE_COMMAND_PATTERNS)
safe_pattern = st.sampled_from(SAFE_COMMAND_PATTERNS)

# Unsafe wildcard patterns
wildcard_pattern = st.sampled_from(["Bash(*)", "Bash(:*)"])

# Outdated/unknown patterns
outdated_pattern = st.from_regex(r"Bash\([a-z]{3,10}:\*\)", fullmatch=True).filter(
    lambda p: p not in SAFE_COMMAND_PATTERNS
)

# Valid settings with proper deny list
valid_settings = st.builds(
    lambda patterns: {
        "permissions": {
            "allow": patterns,
            "deny": DEFAULT_DENY_LIST[:5],
        }
    },
    st.lists(safe_pattern, min_size=1, max_size=10),
)

# Settings with wildcards (invalid)
wildcard_settings = st.builds(
    lambda patterns, wc: {
        "permissions": {
            "allow": patterns + [wc],
            "deny": DEFAULT_DENY_LIST[:5],
        }
    },
    st.lists(safe_pattern, min_size=0, max_size=5),
    wildcard_pattern,
)

# Settings with missing deny list
no_deny_settings = st.builds(
    lambda patterns: {
        "permissions": {
            "allow": patterns,
        }
    },
    st.lists(safe_pattern, min_size=1, max_size=5),
)

# Settings with empty deny list
empty_deny_settings = st.builds(
    lambda patterns: {
        "permissions": {
            "allow": patterns,
            "deny": [],
        }
    },
    st.lists(safe_pattern, min_size=1, max_size=5),
)

# Settings with only outdated patterns
outdated_settings = st.builds(
    lambda patterns: {"permissions": {"allow": patterns}},
    st.lists(outdated_pattern, min_size=1, max_size=5),
)

# Non-dict inputs
non_dict_input = st.one_of(st.none(), st.just("string"), st.just(42), st.just([]))


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestValidateCleanSettings:
    """validate_permission_patterns must pass for clean settings."""

    @example(settings_dict={"permissions": {"allow": ["Read", "Write"], "deny": ["Bash(rm:-rf*)"]}})
    @given(settings_dict=valid_settings)
    def test_valid_settings_pass(self, settings_dict: dict) -> None:
        """Settings with safe patterns and deny list are valid."""
        result = validate_permission_patterns(settings_dict)
        assert result.valid is True
        assert len(result.issues) == 0


class TestValidateDetectsWildcards:
    """validate_permission_patterns must detect Bash(*) wildcards."""

    @example(settings_dict={"permissions": {"allow": ["Bash(*)"], "deny": ["Bash(rm:-rf*)"]}})
    @example(settings_dict={"permissions": {"allow": ["Bash(:*)"], "deny": ["Bash(rm:-rf*)"]}})
    @given(settings_dict=wildcard_settings)
    def test_wildcards_detected(self, settings_dict: dict) -> None:
        """Wildcard patterns cause validation to fail."""
        result = validate_permission_patterns(settings_dict)
        assert result.valid is False
        wildcard_issues = [i for i in result.issues if i.issue_type == "wildcard_pattern"]
        assert len(wildcard_issues) >= 1


class TestValidateDetectsMissingDenyList:
    """validate_permission_patterns must detect missing deny list."""

    @example(settings_dict={"permissions": {"allow": ["Read"]}})
    @given(settings_dict=no_deny_settings)
    def test_missing_deny_detected(self, settings_dict: dict) -> None:
        """Missing deny list causes validation to fail."""
        result = validate_permission_patterns(settings_dict)
        assert result.valid is False
        deny_issues = [i for i in result.issues if i.issue_type == "missing_deny_list"]
        assert len(deny_issues) == 1


class TestValidateDetectsEmptyDenyList:
    """validate_permission_patterns must detect empty deny list."""

    @example(settings_dict={"permissions": {"allow": ["Read"], "deny": []}})
    @given(settings_dict=empty_deny_settings)
    def test_empty_deny_detected(self, settings_dict: dict) -> None:
        """Empty deny list causes validation to fail."""
        result = validate_permission_patterns(settings_dict)
        assert result.valid is False
        deny_issues = [i for i in result.issues if i.issue_type == "empty_deny_list"]
        assert len(deny_issues) == 1


class TestValidateRejectsNonDict:
    """validate_permission_patterns must handle non-dict inputs."""

    @example(value=None)
    @example(value="not a dict")
    @given(value=non_dict_input)
    def test_non_dict_invalid(self, value) -> None:
        """Non-dict inputs return invalid result."""
        result = validate_permission_patterns(value)
        assert result.valid is False
        assert result.needs_fix is True


class TestDetectOutdatedPatterns:
    """detect_outdated_patterns must identify non-safe patterns."""

    @example(settings_dict={"permissions": {"allow": ["Bash(obsolete:*)"]}})
    @given(settings_dict=outdated_settings)
    def test_outdated_detected(self, settings_dict: dict) -> None:
        """Patterns not in SAFE_COMMAND_PATTERNS are detected."""
        result = detect_outdated_patterns(settings_dict)
        assert len(result) >= 1
        for pattern in result:
            assert pattern not in SAFE_COMMAND_PATTERNS


class TestDetectOutdatedPatternsClean:
    """detect_outdated_patterns returns empty list for all-safe patterns."""

    @example(settings_dict={"permissions": {"allow": ["Read", "Write"]}})
    @given(settings_dict=valid_settings)
    def test_clean_settings_no_outdated(self, settings_dict: dict) -> None:
        """All-safe patterns produce empty outdated list."""
        result = detect_outdated_patterns(settings_dict)
        assert len(result) == 0


class TestFixThenValidateRoundtrip:
    """fix_permission_patterns followed by validate should produce valid result."""

    @example(settings_dict={"permissions": {"allow": ["Bash(*)"], "deny": ["Bash(rm:-rf*)"]}})
    @example(settings_dict={"permissions": {"allow": ["Read"], "deny": []}})
    @given(settings_dict=wildcard_settings)
    def test_fix_then_validate(self, settings_dict: dict) -> None:
        """Fixing then validating produces a valid result."""
        fixed = fix_permission_patterns(settings_dict)
        result = validate_permission_patterns(fixed)
        assert result.valid is True
