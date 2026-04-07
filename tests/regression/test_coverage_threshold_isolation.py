"""Regression test for Issue #699: Coverage threshold breaks single-file test runs.

When running ``pytest tests/unit/hooks/test_gh_issue_create_block.py -q``, all tests
pass but the process exits non-zero because ``--cov-fail-under=4`` (from pytest.ini)
is unreachable when only one file's worth of source is exercised.

The fix in ``tests/conftest.py`` detects partial runs and suppresses the threshold.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_single_file_run_no_coverage_failure():
    """Issue #699: Individual test files should not fail on coverage threshold."""
    target = "tests/unit/hooks/test_gh_issue_create_block.py"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"Single file run failed (exit {result.returncode}).\n"
        f"STDOUT (last 2000 chars):\n{result.stdout[-2000:]}\n"
        f"STDERR:\n{result.stderr[-1000:]}"
    )
    # Verify coverage report did NOT contain the fail-under message
    assert "FAIL Required test coverage" not in result.stdout, (
        "Coverage fail-under threshold was enforced on a single-file run"
    )


def test_single_file_with_nodeids_no_coverage_failure():
    """Issue #699: Running specific test nodes should not fail on coverage threshold."""
    target = "tests/unit/hooks/test_gh_issue_create_block.py::TestGhIssueCreateBlocking"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"Node-id run failed (exit {result.returncode}).\n"
        f"STDOUT (last 2000 chars):\n{result.stdout[-2000:]}\n"
        f"STDERR:\n{result.stderr[-1000:]}"
    )
    assert "FAIL Required test coverage" not in result.stdout


def test_partial_run_detection_helper():
    """Unit test for _is_partial_test_run detection logic."""
    from tests.conftest import _is_partial_test_run

    class FakeOption:
        pass

    class FakeConfig:
        def __init__(self, args, k="", m=""):
            self.args = args
            self._k = k
            self._m = m

        def getoption(self, name, default=""):
            if name == "-k":
                return self._k
            if name == "-m":
                return self._m
            return default

    # Full suite: no args -> not partial
    assert not _is_partial_test_run(FakeConfig([]))
    # Full suite: directory arg -> not partial
    assert not _is_partial_test_run(FakeConfig(["tests/"]))
    assert not _is_partial_test_run(FakeConfig(["tests"]))
    # Partial: specific .py file
    assert _is_partial_test_run(FakeConfig(["tests/unit/test_foo.py"]))
    # Partial: nodeid with ::
    assert _is_partial_test_run(FakeConfig(["tests/unit/test_foo.py::test_bar"]))
    # Partial: -k filter
    assert _is_partial_test_run(FakeConfig([], k="test_something"))
    # Partial: -m filter
    assert _is_partial_test_run(FakeConfig([], m="hooks"))
