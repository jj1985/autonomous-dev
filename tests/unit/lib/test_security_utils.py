"""Behavioral tests for security_utils.py path traversal prevention.

Regression tests for GitHub Issue #46 (CVSS 9.8, CWE-22 Path Traversal).
These tests call the real security_utils functions (no mocking) to verify
that path validation correctly blocks traversal attacks and accepts valid paths.

Date: 2026-04-14
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure the library is importable
_repo_root = Path(__file__).resolve().parents[3]  # tests/unit/lib -> repo root
sys.path.insert(0, str(_repo_root / "plugins" / "autonomous-dev" / "lib"))

from security_utils import (
    PROJECT_ROOT,
    SYSTEM_TEMP,
    CLAUDE_HOME_DIR,
    validate_path,
    validate_pytest_path,
    validate_input_length,
    validate_agent_name,
    validate_github_issue,
)


# ---------------------------------------------------------------------------
# validate_path: Path traversal prevention (CWE-22)
# ---------------------------------------------------------------------------

class TestValidatePathTraversalPrevention:
    """Tests that validate_path blocks path traversal attacks (Issue #46)."""

    def test_rejects_relative_traversal_dotdot(self) -> None:
        """Reject '../' traversal patterns."""
        with pytest.raises(ValueError, match="Path traversal attempt detected"):
            validate_path("../../etc/passwd", "test traversal")

    def test_rejects_single_dotdot(self) -> None:
        """Reject bare '..' component."""
        with pytest.raises(ValueError, match="Path traversal attempt detected"):
            validate_path("..", "test traversal")

    def test_rejects_dotdot_in_middle(self) -> None:
        """Reject '..' embedded in path."""
        with pytest.raises(ValueError, match="Path traversal attempt detected"):
            validate_path("subdir/../../etc/shadow", "test traversal")

    def test_rejects_dotdot_at_end(self) -> None:
        """Reject '..' at the end of path."""
        with pytest.raises(ValueError, match="Path traversal attempt detected"):
            validate_path("subdir/..", "test traversal")

    def test_rejects_absolute_system_path(self) -> None:
        """Reject absolute paths outside project root (e.g., /etc/passwd)."""
        with pytest.raises(ValueError, match="Path outside allowed locations"):
            validate_path("/etc/passwd", "test system path")

    def test_rejects_usr_path(self) -> None:
        """Reject /usr/ system directory."""
        with pytest.raises(ValueError, match="Path outside allowed locations"):
            validate_path("/usr/bin/python3", "test usr path")

    def test_rejects_var_log_path(self) -> None:
        """Reject /var/log/ system directory."""
        with pytest.raises(ValueError, match="Path outside allowed locations"):
            validate_path("/var/log/syslog", "test var log path")

    def test_rejects_excessively_long_path(self) -> None:
        """Reject paths exceeding MAX_PATH_LENGTH (4096)."""
        long_path = str(PROJECT_ROOT / ("a" * 5000))
        with pytest.raises(ValueError, match="Path too long"):
            validate_path(long_path, "test long path")


class TestValidatePathAcceptsValid:
    """Tests that validate_path accepts legitimate paths within project."""

    def test_accepts_project_root_file(self) -> None:
        """Accept file at project root."""
        result = validate_path(PROJECT_ROOT / "CLAUDE.md", "test project file", allow_missing=True)
        assert result == (PROJECT_ROOT / "CLAUDE.md").resolve()

    def test_accepts_project_subdirectory(self) -> None:
        """Accept path in project subdirectory."""
        result = validate_path(
            PROJECT_ROOT / "tests" / "conftest.py",
            "test subdirectory",
            allow_missing=True,
        )
        assert result == (PROJECT_ROOT / "tests" / "conftest.py").resolve()

    def test_accepts_claude_home_directory(self) -> None:
        """Accept paths in ~/.claude/ directory."""
        claude_path = CLAUDE_HOME_DIR / "settings.json"
        result = validate_path(claude_path, "test claude home", allow_missing=True)
        assert result == claude_path.resolve()

    def test_accepts_string_path(self) -> None:
        """Accept string paths (auto-converted to Path)."""
        path_str = str(PROJECT_ROOT / "README.md")
        result = validate_path(path_str, "test string path", allow_missing=True)
        assert isinstance(result, Path)

    def test_accepts_temp_dir_in_test_mode(self) -> None:
        """Accept system temp directory when test_mode=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_path(tmpdir, "test temp", test_mode=True)
            assert result == Path(tmpdir).resolve()

    def test_rejects_temp_dir_in_production_mode(self) -> None:
        """Reject system temp directory when test_mode=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Path outside allowed locations"):
                validate_path(tmpdir, "test temp", test_mode=False)


class TestValidatePathSymlinks:
    """Tests that validate_path handles symlinks correctly."""

    def test_rejects_external_symlink(self, tmp_path: Path) -> None:
        """Reject symlink pointing outside project root."""
        # Create a symlink in a temp dir pointing to /etc
        symlink = tmp_path / "evil_link"
        try:
            symlink.symlink_to("/etc")
        except OSError:
            pytest.skip("Cannot create symlinks on this system")

        with pytest.raises(ValueError):
            validate_path(symlink, "test symlink", test_mode=False)

    def test_accepts_internal_symlink(self) -> None:
        """Accept symlink that resolves within project root."""
        # Create a temporary symlink within project root
        link_path = PROJECT_ROOT / "_test_internal_symlink"
        target = PROJECT_ROOT / "CLAUDE.md"
        if not target.exists():
            pytest.skip("CLAUDE.md not found in project root")
        try:
            link_path.symlink_to(target)
            result = validate_path(link_path, "test internal symlink")
            assert result == target.resolve()
        except OSError:
            pytest.skip("Cannot create symlinks on this system")
        finally:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()


# ---------------------------------------------------------------------------
# validate_pytest_path: Pytest path format validation
# ---------------------------------------------------------------------------

class TestValidatePytestPath:
    """Tests that validate_pytest_path blocks invalid/malicious pytest paths."""

    def test_rejects_traversal_in_pytest_path(self) -> None:
        """Reject '..' in pytest path."""
        with pytest.raises(ValueError, match="Path traversal attempt"):
            validate_pytest_path("../../etc/test.py", "test traversal")

    def test_rejects_shell_injection(self) -> None:
        """Reject shell metacharacters in pytest path."""
        with pytest.raises(ValueError, match="Invalid pytest path format"):
            validate_pytest_path("test.py; rm -rf /", "test injection")

    def test_rejects_code_injection(self) -> None:
        """Reject code injection attempts."""
        with pytest.raises(ValueError, match="Invalid pytest path format"):
            validate_pytest_path("test.py::test(); os.system('cmd')", "test injection")

    def test_rejects_empty_string(self) -> None:
        """Reject empty string."""
        with pytest.raises(ValueError, match="Invalid pytest path"):
            validate_pytest_path("", "test empty")

    def test_rejects_none(self) -> None:
        """Reject None input."""
        with pytest.raises(ValueError, match="Invalid pytest path"):
            validate_pytest_path(None, "test none")  # type: ignore[arg-type]

    def test_rejects_spaces_in_path(self) -> None:
        """Reject paths with spaces (potential injection vector)."""
        with pytest.raises(ValueError, match="Invalid pytest path format"):
            validate_pytest_path("test file.py", "test spaces")

    def test_accepts_simple_test_file(self) -> None:
        """Accept simple test file path."""
        result = validate_pytest_path("tests/test_foo.py", "test simple")
        assert result == "tests/test_foo.py"

    def test_accepts_test_with_function(self) -> None:
        """Accept test file with function specifier."""
        result = validate_pytest_path("tests/test_foo.py::test_bar", "test function")
        assert result == "tests/test_foo.py::test_bar"

    def test_rejects_double_colon_class_method(self) -> None:
        """Reject double :: separator (TestClass::test_method) -- regex only allows one :: segment.

        The PYTEST_PATH_PATTERN regex '^[\\w/.-]+\\.py(?:::[\\w\\[\\],_-]+)?$' only supports
        a single :: separator. Paths like 'test.py::Class::method' contain a second ':' which
        is not in the allowed character set [\\w\\[\\],_-], so they are correctly rejected.
        """
        with pytest.raises(ValueError, match="Invalid pytest path format"):
            validate_pytest_path(
                "tests/test_foo.py::TestClass::test_method", "test class method"
            )

    def test_accepts_parametrized_test(self) -> None:
        """Accept parametrized test path."""
        result = validate_pytest_path(
            "tests/test_foo.py::test_bar[param1,param2]", "test parametrized"
        )
        assert result == "tests/test_foo.py::test_bar[param1,param2]"


# ---------------------------------------------------------------------------
# validate_input_length
# ---------------------------------------------------------------------------

class TestValidateInputLength:
    """Tests for input length validation."""

    def test_rejects_oversized_input(self) -> None:
        """Reject input exceeding max length."""
        with pytest.raises(ValueError, match="too long"):
            validate_input_length("a" * 101, 100, "test_field")

    def test_accepts_input_within_limit(self) -> None:
        """Accept input within max length."""
        result = validate_input_length("hello", 100, "test_field")
        assert result == "hello"

    def test_rejects_non_string(self) -> None:
        """Reject non-string input."""
        with pytest.raises(ValueError, match="must be string"):
            validate_input_length(123, 100, "test_field")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_agent_name
# ---------------------------------------------------------------------------

class TestValidateAgentName:
    """Tests for agent name validation."""

    def test_accepts_valid_agent_name(self) -> None:
        """Accept valid agent names."""
        assert validate_agent_name("researcher") == "researcher"
        assert validate_agent_name("test-master") == "test-master"
        assert validate_agent_name("doc_master") == "doc_master"

    def test_rejects_empty_name(self) -> None:
        """Reject empty agent name."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_agent_name("")

    def test_rejects_name_with_spaces(self) -> None:
        """Reject agent name with spaces (injection vector)."""
        with pytest.raises(ValueError, match="Invalid agent name"):
            validate_agent_name("security auditor")

    def test_rejects_name_with_semicolon(self) -> None:
        """Reject agent name with shell metacharacters."""
        with pytest.raises(ValueError, match="Invalid agent name"):
            validate_agent_name("researcher; rm -rf /")


# ---------------------------------------------------------------------------
# validate_github_issue
# ---------------------------------------------------------------------------

class TestValidateGithubIssue:
    """Tests for GitHub issue number validation."""

    def test_accepts_valid_issue_number(self) -> None:
        """Accept valid issue numbers."""
        assert validate_github_issue(1) == 1
        assert validate_github_issue(46) == 46
        assert validate_github_issue(999999) == 999999

    def test_rejects_zero(self) -> None:
        """Reject issue number 0."""
        with pytest.raises(ValueError, match="Invalid GitHub issue number"):
            validate_github_issue(0)

    def test_rejects_negative(self) -> None:
        """Reject negative issue numbers."""
        with pytest.raises(ValueError, match="Invalid GitHub issue number"):
            validate_github_issue(-1)

    def test_rejects_too_large(self) -> None:
        """Reject issue numbers over 999999."""
        with pytest.raises(ValueError, match="Invalid GitHub issue number"):
            validate_github_issue(1000000)

    def test_rejects_non_integer(self) -> None:
        """Reject non-integer input."""
        with pytest.raises(ValueError, match="must be integer"):
            validate_github_issue("46")  # type: ignore[arg-type]
