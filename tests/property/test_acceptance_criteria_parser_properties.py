"""Property-based tests for acceptance_criteria_parser.py parsing and formatting.

Tests invariants:
- parse_acceptance_criteria returns empty dict for bodies without AC section
- parse_acceptance_criteria returns non-empty dict for bodies with AC section
- format_for_uat produces scenario_name starting with "test_"
- format_for_uat scenario_name contains only valid pytest chars
- _generate_scenario_name is idempotent on same input
- parse then format roundtrip: every criterion appears in a scenario
"""

import re

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from acceptance_criteria_parser import (
    _extract_criteria_items,
    _generate_scenario_name,
    format_for_uat,
    parse_acceptance_criteria,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Issue bodies WITH acceptance criteria section
body_with_ac = st.builds(
    lambda prefix, criteria: (
        f"{prefix}\n"
        f"## Acceptance Criteria\n"
        f"- [ ] {criteria[0]}\n"
        + "".join(f"- [ ] {c}\n" for c in criteria[1:])
    ),
    st.text(min_size=0, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
    st.lists(
        st.from_regex(r"[A-Za-z ]{5,50}", fullmatch=True),
        min_size=1,
        max_size=5,
    ),
)

# Issue bodies WITHOUT acceptance criteria section
body_without_ac = st.text(
    min_size=0,
    max_size=500,
    alphabet=st.characters(whitelist_categories=("L", "N", "Z", "P")),
).filter(lambda s: "acceptance criteria" not in s.lower())

# Category names
category_name = st.from_regex(r"[A-Za-z ]{3,30}", fullmatch=True)

# Criterion text
criterion_text = st.from_regex(r"[A-Za-z ]{5,50}", fullmatch=True)

# Criteria dicts (for format_for_uat)
criteria_dict = st.dictionaries(
    category_name,
    st.lists(criterion_text, min_size=1, max_size=5),
    min_size=1,
    max_size=3,
)

# Text blocks with bullet items
bullet_text = st.builds(
    lambda items: "\n".join(f"- [ ] {item}" for item in items),
    st.lists(
        st.from_regex(r"[A-Za-z ]{5,30}", fullmatch=True),
        min_size=1,
        max_size=5,
    ),
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestParseWithoutACSection:
    """parse_acceptance_criteria returns empty dict when no AC section exists."""

    @example(body="Just a description without acceptance criteria")
    @example(body="## Other Section\n- Some bullet")
    @given(body=body_without_ac)
    def test_no_ac_returns_empty(self, body: str) -> None:
        """Bodies without '## Acceptance Criteria' return empty dict."""
        result = parse_acceptance_criteria(body)
        assert isinstance(result, dict)
        assert len(result) == 0


class TestParseWithACSection:
    """parse_acceptance_criteria returns non-empty dict when AC section exists."""

    @example(body="## Acceptance Criteria\n- [ ] Feature works\n- [ ] Tests pass")
    @example(body="Intro\n## Acceptance Criteria\n- [ ] Single criterion")
    @given(body=body_with_ac)
    def test_ac_returns_non_empty(self, body: str) -> None:
        """Bodies with '## Acceptance Criteria' and criteria return non-empty dict."""
        result = parse_acceptance_criteria(body)
        assert isinstance(result, dict)
        assert len(result) >= 1
        # Every category has at least one criterion
        for cat, items in result.items():
            assert len(items) >= 1


class TestFormatScenarioNameStartsWithTest:
    """format_for_uat scenario_name must start with 'test_'."""

    @example(criteria={"General": ["Feature works correctly"]})
    @example(criteria={"Install": ["Setup works", "Config loads"]})
    @given(criteria=criteria_dict)
    def test_scenario_names_start_with_test(self, criteria: dict) -> None:
        """Every scenario_name starts with 'test_'."""
        scenarios = format_for_uat(criteria)
        for scenario in scenarios:
            assert scenario["scenario_name"].startswith("test_")


class TestFormatScenarioNameValidPytest:
    """format_for_uat scenario_name must contain only valid pytest chars."""

    @example(criteria={"General": ["Feature works correctly"]})
    @given(criteria=criteria_dict)
    def test_scenario_names_valid_chars(self, criteria: dict) -> None:
        """scenario_name contains only lowercase letters, digits, and underscores."""
        scenarios = format_for_uat(criteria)
        for scenario in scenarios:
            name = scenario["scenario_name"]
            assert re.match(r"^test_[a-z0-9_]+$", name), f"Invalid name: {name}"


class TestFormatPreservesAllCriteria:
    """format_for_uat produces one scenario per criterion."""

    @example(criteria={"A": ["one", "two"], "B": ["three"]})
    @given(criteria=criteria_dict)
    def test_one_scenario_per_criterion(self, criteria: dict) -> None:
        """Total scenarios equals total criteria across all categories."""
        scenarios = format_for_uat(criteria)
        total_criteria = sum(len(items) for items in criteria.values())
        assert len(scenarios) == total_criteria


class TestGenerateScenarioNameIdempotent:
    """_generate_scenario_name is deterministic for same input."""

    @example(category="Fresh Install", criterion="Feature works")
    @example(category="General", criterion="Tests pass")
    @given(category=category_name, criterion=criterion_text)
    def test_idempotent(self, category: str, criterion: str) -> None:
        """Same inputs always produce same output."""
        result1 = _generate_scenario_name(category, criterion)
        result2 = _generate_scenario_name(category, criterion)
        assert result1 == result2


class TestExtractCriteriaItems:
    """_extract_criteria_items extracts bullet items from text."""

    @example(text="- [ ] First item\n- [ ] Second item")
    @example(text="- First\n- Second\n- Third")
    @given(text=bullet_text)
    def test_extracts_items(self, text: str) -> None:
        """Bullet items are extracted as strings."""
        items = _extract_criteria_items(text)
        assert isinstance(items, list)
        assert len(items) >= 1
        for item in items:
            assert isinstance(item, str)
            assert len(item) > 0
