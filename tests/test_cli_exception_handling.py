"""
Tests for CLI exception handling -- int() conversions and argument parsing.

Extracted from test_sync_dev_security.py (which tested archived sync_to_installed hook).
These tests validate pr_automation.py extract_issue_numbers() error handling.

Test Coverage:
- Non-numeric issue numbers
- Float issue numbers
- Very large numbers
- Negative numbers
- Empty references
- Mixed valid/invalid references
- Edge case formats
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# Load pr_automation directly since autonomous-dev (hyphen) is not a valid Python package name
_lib_dir = Path(__file__).parent.parent / "plugins" / "autonomous-dev" / "lib"
_spec = importlib.util.spec_from_file_location(
    "pr_automation", str(_lib_dir / "pr_automation.py")
)
_pr_automation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pr_automation)
extract_issue_numbers = _pr_automation.extract_issue_numbers


class TestCLIExceptionHandling:
    """Test CLI exception handling for int() conversions and argument parsing."""

    def test_handles_invalid_issue_number_non_numeric(self):
        """Test handling of non-numeric issue numbers in CLI."""
        invalid_messages = [
            "Fix bug #abc",  # Non-numeric
            "Resolve #12.5",  # Float
            "Close #",  # Empty
            "Fix ##123",  # Double hash
        ]

        for message in invalid_messages:
            try:
                result = extract_issue_numbers([message])
                assert isinstance(result, list), "Should return list"
                for num in result:
                    assert isinstance(num, int), "Should only contain integers"
            except ValueError as e:
                pytest.fail(f"Should not raise ValueError for '{message}': {e}")

    def test_handles_float_issue_numbers(self):
        """Test that float issue numbers are handled (edge case)."""
        message = "Fix #42.5"

        result = extract_issue_numbers([message])

        assert isinstance(result, list)
        if result:
            assert all(isinstance(n, int) for n in result)

    def test_handles_very_large_issue_numbers(self):
        """Test handling of extremely large issue numbers."""
        message = f"Fix #{2**63}"

        try:
            result = extract_issue_numbers([message])
            assert isinstance(result, list)
        except (ValueError, OverflowError) as e:
            pytest.fail(f"Should handle large numbers gracefully: {e}")

    def test_handles_negative_issue_numbers(self):
        """Test handling of negative issue numbers (invalid but should not crash)."""
        message = "Fix #-42"

        result = extract_issue_numbers([message])

        assert isinstance(result, list)
        assert all(n > 0 for n in result), "Should only return positive issue numbers"

    def test_handles_empty_issue_references(self):
        """Test handling of empty # references."""
        test_cases = [
            "Fix #",  # Just hash, no number
            "Resolve ##",  # Double hash
            "Close # ",  # Hash with space
        ]

        for message in test_cases:
            result = extract_issue_numbers([message])
            assert isinstance(result, list)

    def test_handles_mixed_valid_and_invalid(self):
        """Test handling of messages with both valid and invalid issue refs."""
        result = extract_issue_numbers(["Fix #123 and something else"])
        assert isinstance(result, list)
        assert 123 in result

    def test_handles_edge_case_formats(self):
        """Test handling of edge case issue reference formats."""
        test_cases = [
            "Fix #0",  # Zero
            "Fix #00042",  # Leading zeros
            "Fix #1e5",  # Scientific notation
        ]

        for message in test_cases:
            result = extract_issue_numbers([message])
            assert isinstance(result, list)
