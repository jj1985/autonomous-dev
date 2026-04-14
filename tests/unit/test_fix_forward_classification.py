"""Unit tests for fix_forward classification library.

Tests parse_failing_tests, classify_failures, and format_issue_body from
the fix_forward module (Issue #860).
"""

import sys
from pathlib import Path

# Repo root is two levels up from tests/unit/
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib"))

from fix_forward import classify_failures, format_issue_body, parse_failing_tests


class TestParseFailingTests:
    """Tests for parse_failing_tests()."""

    def test_parse_failing_tests_empty_output(self):
        """No failures returns empty set."""
        assert parse_failing_tests("") == set()

    def test_parse_failing_tests_no_failures(self):
        """Output with only passing tests returns empty set."""
        output = "10 passed in 1.23s\n"
        assert parse_failing_tests(output) == set()

    def test_parse_failing_tests_multiple_failures(self):
        """Parses N test IDs correctly from pytest output."""
        output = (
            "tests/unit/test_a.py::test_one FAILED\n"
            "tests/unit/test_b.py::test_two FAILED\n"
            "tests/unit/test_c.py::test_three FAILED\n"
            "3 failed in 0.5s\n"
        )
        result = parse_failing_tests(output)
        assert result == {
            "tests/unit/test_a.py::test_one",
            "tests/unit/test_b.py::test_two",
            "tests/unit/test_c.py::test_three",
        }

    def test_parse_failing_tests_with_percentage_line(self):
        """Handles pytest summary lines (e.g., '= 5 failed in 2.3s =')."""
        output = (
            "tests/unit/test_a.py::test_one FAILED\n"
            "= 1 failed, 10 passed in 2.3s =\n"
        )
        result = parse_failing_tests(output)
        assert result == {"tests/unit/test_a.py::test_one"}
        # Summary line should NOT be parsed as a test ID
        assert not any("failed" in t and "passed" in t for t in result)

    def test_parse_failing_tests_mixed_with_passed(self):
        """Only FAILED lines are captured, not PASSED lines."""
        output = (
            "tests/unit/test_a.py::test_one PASSED\n"
            "tests/unit/test_b.py::test_two FAILED\n"
            "1 failed, 1 passed in 0.3s\n"
        )
        result = parse_failing_tests(output)
        assert result == {"tests/unit/test_b.py::test_two"}


class TestClassifyFailures:
    """Tests for classify_failures()."""

    def test_classify_all_fixed(self):
        """All baseline failures now pass -> all in 'fixed'."""
        baseline = {"test_a", "test_b", "test_c"}
        current: set[str] = set()
        result = classify_failures(baseline, current)
        assert result["fixed"] == {"test_a", "test_b", "test_c"}
        assert result["pre_existing_remaining"] == set()
        assert result["new_failures"] == set()

    def test_classify_new_failures_detected(self):
        """New failure not in baseline -> in 'new_failures'."""
        baseline: set[str] = set()
        current = {"test_new"}
        result = classify_failures(baseline, current)
        assert result["fixed"] == set()
        assert result["pre_existing_remaining"] == set()
        assert result["new_failures"] == {"test_new"}

    def test_classify_mixed(self):
        """Some fixed, some remaining, some new."""
        baseline = {"test_a", "test_b", "test_c"}
        current = {"test_b", "test_d"}
        result = classify_failures(baseline, current)
        assert result["fixed"] == {"test_a", "test_c"}
        assert result["pre_existing_remaining"] == {"test_b"}
        assert result["new_failures"] == {"test_d"}

    def test_classify_no_baseline(self):
        """Empty baseline, current failures = all new."""
        baseline: set[str] = set()
        current = {"test_x", "test_y"}
        result = classify_failures(baseline, current)
        assert result["fixed"] == set()
        assert result["pre_existing_remaining"] == set()
        assert result["new_failures"] == {"test_x", "test_y"}

    def test_classify_no_changes(self):
        """Same failures in baseline and current -> all pre_existing_remaining."""
        baseline = {"test_a", "test_b"}
        current = {"test_a", "test_b"}
        result = classify_failures(baseline, current)
        assert result["fixed"] == set()
        assert result["pre_existing_remaining"] == {"test_a", "test_b"}
        assert result["new_failures"] == set()


class TestFormatIssueBody:
    """Tests for format_issue_body()."""

    def test_format_issue_body_contains_test_id(self):
        """Output contains test ID and context."""
        body = format_issue_body(
            "tests/unit/test_foo.py::test_bar",
            context="Discovered during pipeline run R-001",
        )
        assert "tests/unit/test_foo.py::test_bar" in body
        assert "Discovered during pipeline run R-001" in body
        assert "Pre-Existing Test Failure" in body
        assert "pre-existing-failure" in body

    def test_format_issue_body_without_context(self):
        """Output works without context."""
        body = format_issue_body("tests/unit/test_foo.py::test_bar")
        assert "tests/unit/test_foo.py::test_bar" in body
        assert "Context" not in body

    def test_format_issue_body_includes_run_command(self):
        """Output includes a runnable pytest command."""
        body = format_issue_body("tests/unit/test_foo.py::test_bar")
        assert "pytest tests/unit/test_foo.py::test_bar -xvs" in body
