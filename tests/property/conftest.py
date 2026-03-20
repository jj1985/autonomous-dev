"""Shared fixtures for property-based tests."""

import sys
from pathlib import Path

import pytest

# Add plugins lib to sys.path for direct imports
_lib_path = str(Path(__file__).parent.parent.parent / "plugins" / "autonomous-dev" / "lib")
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def tmp_project_with_git(tmp_path: Path) -> Path:
    """Create a temporary directory with a .git marker for project detection."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path
