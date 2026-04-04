"""Unit tests for E2E test infrastructure.

Validates that the E2E test directory, conftest, and marker
configuration are properly set up.
"""

import sys
from pathlib import Path

import pytest

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Add lib to path for imports
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))


class TestE2EInfrastructure:
    """Tests for E2E test directory and configuration."""

    def test_e2e_conftest_exists(self) -> None:
        """tests/e2e/conftest.py must exist."""
        conftest = PROJECT_ROOT / "tests" / "e2e" / "conftest.py"
        assert conftest.exists(), f"E2E conftest not found: {conftest}"

    def test_e2e_init_exists(self) -> None:
        """tests/e2e/__init__.py must exist for proper package structure."""
        init = PROJECT_ROOT / "tests" / "e2e" / "__init__.py"
        assert init.exists(), f"E2E __init__.py not found: {init}"

    def test_e2e_conftest_registers_marker(self) -> None:
        """E2E conftest must register the 'e2e' pytest marker."""
        conftest = PROJECT_ROOT / "tests" / "e2e" / "conftest.py"
        content = conftest.read_text()
        assert "e2e" in content
        assert "pytest.mark" in content or "markers" in content

    def test_directory_markers_includes_e2e(self) -> None:
        """Root conftest DIRECTORY_MARKERS must include 'e2e/' entry."""
        conftest = PROJECT_ROOT / "tests" / "conftest.py"
        content = conftest.read_text()
        assert '"e2e/"' in content or "'e2e/'" in content

    def test_e2e_marker_maps_to_correct_markers(self) -> None:
        """The e2e directory marker must map to ['e2e', 'slow']."""
        # Import the root conftest module to check DIRECTORY_MARKERS
        conftest = PROJECT_ROOT / "tests" / "conftest.py"
        content = conftest.read_text()
        # Verify both 'e2e' and 'slow' markers are in the e2e entry
        assert '"e2e"' in content or "'e2e'" in content
        # Check the e2e line specifically contains 'slow'
        for line in content.splitlines():
            if "e2e/" in line and "DIRECTORY_MARKERS" not in line:
                assert "slow" in line, "e2e/ marker entry must include 'slow'"
                assert "e2e" in line, "e2e/ marker entry must include 'e2e'"
                break
        else:
            pytest.fail("Could not find e2e/ entry in DIRECTORY_MARKERS")
