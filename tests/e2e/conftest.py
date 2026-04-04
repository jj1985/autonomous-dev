"""E2E test configuration for Playwright MCP browser tests.

This conftest registers the @pytest.mark.e2e marker and provides
shared fixtures for E2E test files.
"""

import pytest
from pathlib import Path


# Project root for E2E test file references
PROJECT_ROOT = Path(__file__).parent.parent.parent


def pytest_configure(config):
    """Register custom markers for E2E tests."""
    config.addinivalue_line(
        "markers",
        "e2e: End-to-end browser tests using Playwright MCP tools (slow)",
    )


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture
def e2e_test_dir() -> Path:
    """Return the E2E test directory."""
    return PROJECT_ROOT / "tests" / "e2e"
