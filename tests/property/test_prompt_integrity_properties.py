"""Property-based tests for prompt_integrity.py word count validation.

Tests invariants:
- validate_prompt_word_count always returns a PromptIntegrityResult
- Empty prompts always fail validation
- Critical agents below minimum word count always fail
- Non-critical agents with sufficient words always pass (no baseline)
- Shrinkage percentage is correctly computed
- Word count matches prompt.split() length
"""

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from prompt_integrity import (
    COMPRESSION_CRITICAL_AGENTS,
    MIN_CRITICAL_AGENT_PROMPT_WORDS,
    PromptIntegrityResult,
    validate_prompt_word_count,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Critical agent names
critical_agent = st.sampled_from(sorted(COMPRESSION_CRITICAL_AGENTS))

# Non-critical agent names
non_critical_agent = st.sampled_from(["test-agent", "custom-bot", "helper", "analyzer"])

# Prompts with many words (above minimum)
long_prompt = st.builds(
    lambda words: " ".join(words),
    st.lists(
        st.from_regex(r"[a-zA-Z]{3,10}", fullmatch=True),
        min_size=MIN_CRITICAL_AGENT_PROMPT_WORDS + 10,
        max_size=MIN_CRITICAL_AGENT_PROMPT_WORDS + 50,
    ),
)

# Prompts with few words (below minimum for critical agents)
short_prompt = st.builds(
    lambda words: " ".join(words),
    st.lists(
        st.from_regex(r"[a-zA-Z]{3,10}", fullmatch=True),
        min_size=1,
        max_size=MIN_CRITICAL_AGENT_PROMPT_WORDS - 1,
    ),
)

# Arbitrary non-empty prompts
arbitrary_prompt = st.text(min_size=1, max_size=500, alphabet=st.characters(whitelist_categories=("L", "N", "Z")))

# Baseline word counts
positive_int = st.integers(min_value=1, max_value=10000)

# Shrinkage factor (0.0 to 1.0)
max_shrinkage = st.floats(min_value=0.01, max_value=0.99)

# Agent name (short text for return type test)
short_agent_name = st.text(min_size=1, max_size=30)

# Arbitrary agent for empty prompt test
any_agent_name = st.text(min_size=1, max_size=30)

# Agent name for word count test
agent_for_count = st.text(min_size=1, max_size=20)

# Large baseline integers
large_baseline = st.integers(min_value=500, max_value=5000)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestAlwaysReturnsResult:
    """validate_prompt_word_count must always return PromptIntegrityResult."""

    @example(agent="reviewer", prompt="some words here for testing purposes")
    @example(agent="custom-agent", prompt="short")
    @given(agent=short_agent_name, prompt=arbitrary_prompt)
    def test_return_type(self, agent: str, prompt: str) -> None:
        """Any input combination returns PromptIntegrityResult."""
        result = validate_prompt_word_count(agent, prompt)
        assert isinstance(result, PromptIntegrityResult)
        assert isinstance(result.passed, bool)
        assert isinstance(result.word_count, int)


class TestEmptyPromptAlwaysFails:
    """Empty prompts must always fail validation."""

    @example(agent="reviewer")
    @example(agent="custom-agent")
    @given(agent=any_agent_name)
    def test_empty_prompt_fails(self, agent: str) -> None:
        """An empty prompt always fails with should_reload=True."""
        result = validate_prompt_word_count(agent, "")
        assert result.passed is False
        assert result.word_count == 0
        assert result.should_reload is True


class TestCriticalAgentBelowMinimum:
    """Critical agents below MIN_CRITICAL_AGENT_PROMPT_WORDS must fail."""

    @example(agent="reviewer", prompt="too short")
    @example(agent="implementer", prompt="only a few words")
    @given(agent=critical_agent, prompt=short_prompt)
    def test_critical_below_minimum_fails(self, agent: str, prompt: str) -> None:
        """Critical agents with too few words fail validation."""
        result = validate_prompt_word_count(agent, prompt)
        assert result.passed is False
        assert result.should_reload is True


class TestCriticalAgentAboveMinimum:
    """Critical agents above MIN_CRITICAL_AGENT_PROMPT_WORDS must pass (no baseline)."""

    @example(agent="reviewer", prompt=" ".join(["word"] * 100))
    @example(agent="implementer", prompt=" ".join(["word"] * 100))
    @given(agent=critical_agent, prompt=long_prompt)
    def test_critical_above_minimum_passes(self, agent: str, prompt: str) -> None:
        """Critical agents with enough words pass when no baseline set."""
        result = validate_prompt_word_count(agent, prompt)
        assert result.passed is True
        assert result.should_reload is False


class TestNonCriticalAgentAlwaysPasses:
    """Non-critical agents with non-empty prompts pass (no baseline)."""

    @example(agent="custom-agent", prompt="just a few words")
    @example(agent="helper", prompt="one")
    @given(agent=non_critical_agent, prompt=arbitrary_prompt)
    def test_non_critical_passes(self, agent: str, prompt: str) -> None:
        """Non-critical agents pass validation when prompt is non-empty."""
        # Only test without baseline - non-critical agents have no minimum word count
        prompt_stripped = prompt.strip()
        if len(prompt_stripped.split()) > 0:
            result = validate_prompt_word_count(agent, prompt_stripped)
            assert result.passed is True


class TestWordCountMatchesSplit:
    """word_count in result must match len(prompt.split())."""

    @example(agent="test", prompt="hello world foo bar")
    @example(agent="test", prompt="   spaced   out   ")
    @given(agent=agent_for_count, prompt=arbitrary_prompt)
    def test_word_count_correct(self, agent: str, prompt: str) -> None:
        """word_count equals len(prompt.split())."""
        result = validate_prompt_word_count(agent, prompt)
        assert result.word_count == len(prompt.split())


class TestShrinkageDetection:
    """Excessive shrinkage from baseline must fail validation."""

    @example(agent="reviewer", prompt=" ".join(["w"] * 85), baseline=1000)
    @example(agent="test", prompt=" ".join(["w"] * 50), baseline=1000)
    @given(
        agent=non_critical_agent,
        prompt=long_prompt,
        baseline=large_baseline,
    )
    def test_large_shrinkage_detected(self, agent: str, prompt: str, baseline: int) -> None:
        """If prompt shrunk more than max_shrinkage, validation fails."""
        word_count = len(prompt.split())
        shrinkage = 1.0 - word_count / baseline
        result = validate_prompt_word_count(agent, prompt, baseline_word_count=baseline)
        if shrinkage > 0.15:
            assert result.passed is False
            assert result.should_reload is True
