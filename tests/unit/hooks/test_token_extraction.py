#!/usr/bin/env python3
"""
Tests for token extraction from Agent tool usage blocks (Issue #704).

Validates _extract_usage_from_result and the token-aware _add_result_word_count.
"""

import sys
from pathlib import Path

import pytest

# Portable project root detection
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "hooks"))

from session_activity_logger import _extract_usage_from_result, _add_result_word_count


class TestExtractUsageFromResult:
    """Tests for _extract_usage_from_result helper."""

    def test_extract_usage_block_present(self):
        """Parse valid usage block returns correct values."""
        output = (
            "Some agent output text here.\n"
            "<usage>total_tokens: 27169\n"
            "tool_uses: 2\n"
            "duration_ms: 18677</usage>\n"
        )
        result = _extract_usage_from_result(output)
        assert result["total_tokens"] == 27169
        assert result["tool_uses"] == 2
        assert result["duration_ms"] == 18677

    def test_extract_usage_block_missing(self):
        """No usage block returns empty dict."""
        output = "Just some plain agent output with no usage block."
        result = _extract_usage_from_result(output)
        assert result == {}

    def test_extract_usage_block_partial(self):
        """Usage block with only some fields returns partial extraction."""
        output = "<usage>total_tokens: 5000\nduration_ms: 12000</usage>"
        result = _extract_usage_from_result(output)
        assert result["total_tokens"] == 5000
        assert result["duration_ms"] == 12000
        assert "tool_uses" not in result

    def test_extract_usage_empty_string(self):
        """Empty string returns empty dict."""
        assert _extract_usage_from_result("") == {}

    def test_extract_usage_none_input(self):
        """None input returns empty dict."""
        assert _extract_usage_from_result(None) == {}

    def test_extract_usage_non_string_input(self):
        """Non-string input returns empty dict."""
        assert _extract_usage_from_result(12345) == {}


class TestAddResultWordCountWithTokens:
    """Tests for _add_result_word_count with token extraction."""

    def test_add_result_word_count_with_tokens(self):
        """Agent output with usage block populates token fields in summary."""
        tool_output = {
            "output": (
                "Here is the analysis result with some words.\n"
                "<usage>total_tokens: 15000\n"
                "tool_uses: 3\n"
                "duration_ms: 9500</usage>"
            )
        }
        summary: dict = {}
        result = _add_result_word_count("Agent", tool_output, summary)
        assert result["total_tokens"] == 15000
        assert result["tool_uses"] == 3
        assert result["agent_duration_ms"] == 9500
        assert result["result_word_count"] > 0

    def test_add_result_word_count_without_tokens(self):
        """Agent output without usage block has 0 for token fields."""
        tool_output = {"output": "Simple output with no usage block."}
        summary: dict = {}
        result = _add_result_word_count("Agent", tool_output, summary)
        assert result["total_tokens"] == 0
        assert result["tool_uses"] == 0
        assert result["agent_duration_ms"] == 0
        assert result["result_word_count"] > 0

    def test_non_agent_tool_skips_tokens(self):
        """Non-Agent tools do not get token fields added."""
        tool_output = {"output": "some output"}
        summary: dict = {}
        result = _add_result_word_count("Bash", tool_output, summary)
        assert "total_tokens" not in result
        assert "result_word_count" not in result
