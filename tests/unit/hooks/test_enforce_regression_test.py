"""Unit tests for enforce_regression_test.py pre-commit hook — Issue #737.

Tests the pre-commit hook that blocks bug fix commits without regression tests.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"))
sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib"))

from enforce_regression_test import get_staged_files, has_test_files, main


class TestHasTestFiles:
    """Tests for has_test_files() function."""

    def test_test_prefix_file(self):
        assert has_test_files(["tests/unit/test_example.py"]) is True

    def test_test_suffix_file(self):
        assert has_test_files(["src/example_test.py"]) is True

    def test_file_under_tests_dir(self):
        assert has_test_files(["tests/conftest.py"]) is True

    def test_nested_tests_dir(self):
        assert has_test_files(["src/tests/helpers.py"]) is True

    def test_no_test_files(self):
        assert has_test_files(["src/main.py", "lib/utils.py"]) is False

    def test_empty_list(self):
        assert has_test_files([]) is False

    def test_test_in_filename_not_dir(self):
        """test_ in filename should match."""
        assert has_test_files(["src/test_helper.py"]) is True


class TestMain:
    """Tests for the main() hook entry point."""

    def _mock_commit_msg(self, tmp_path: Path, message: str) -> Path:
        """Create a mock COMMIT_EDITMSG file."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir(exist_ok=True)
        msg_file = git_dir / "COMMIT_EDITMSG"
        msg_file.write_text(message)
        return git_dir

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_fix_commit_no_tests_blocked(self, mock_staged, mock_msg):
        """fix: commit with no test files should be blocked."""
        mock_msg.return_value = "fix: resolve crash in parser"
        mock_staged.return_value = ["src/parser.py"]
        assert main() == 2

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_fix_commit_with_tests_allowed(self, mock_staged, mock_msg):
        """fix: commit with test files should be allowed."""
        mock_msg.return_value = "fix: resolve crash in parser"
        mock_staged.return_value = ["src/parser.py", "tests/test_parser.py"]
        assert main() == 0

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_non_fix_commit_no_tests_allowed(self, mock_staged, mock_msg):
        """feat: commit without tests should be allowed (not a fix)."""
        mock_msg.return_value = "feat: add new dashboard"
        mock_staged.return_value = ["src/dashboard.py"]
        assert main() == 0

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_bugfix_prefix_blocked(self, mock_staged, mock_msg):
        mock_msg.return_value = "bugfix: correct format issue"
        mock_staged.return_value = ["src/format.py"]
        assert main() == 2

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_hotfix_prefix_blocked(self, mock_staged, mock_msg):
        mock_msg.return_value = "hotfix: urgent patch"
        mock_staged.return_value = ["src/critical.py"]
        assert main() == 2

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_fix_with_scope_blocked(self, mock_staged, mock_msg):
        mock_msg.return_value = "fix(hooks): prevent null reference"
        mock_staged.return_value = ["hooks/validator.py"]
        assert main() == 2

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_docs_prefix_allowed(self, mock_staged, mock_msg):
        mock_msg.return_value = "docs: update readme"
        mock_staged.return_value = ["README.md"]
        assert main() == 0

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_refactor_prefix_allowed(self, mock_staged, mock_msg):
        mock_msg.return_value = "refactor: clean up code"
        mock_staged.return_value = ["src/utils.py"]
        assert main() == 0

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_chore_prefix_allowed(self, mock_staged, mock_msg):
        mock_msg.return_value = "chore: update dependencies"
        mock_staged.return_value = ["requirements.txt"]
        assert main() == 0

    @patch("enforce_regression_test.get_commit_message")
    def test_empty_commit_message_allowed(self, mock_msg):
        mock_msg.return_value = ""
        assert main() == 0

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_fix_in_body_not_prefix_allowed(self, mock_staged, mock_msg):
        """'fix' in body but not as prefix line should NOT trigger block."""
        mock_msg.return_value = "feat: add feature\n\nThis will fix the issue"
        mock_staged.return_value = ["src/feature.py"]
        assert main() == 0

    @patch("enforce_regression_test.get_commit_message")
    @patch("enforce_regression_test.get_staged_files")
    def test_blocking_message_contains_required_next_action(self, mock_staged, mock_msg, capsys):
        """Blocking message must contain REQUIRED NEXT ACTION (stick+carrot pattern)."""
        mock_msg.return_value = "fix: something"
        mock_staged.return_value = ["src/file.py"]
        main()
        captured = capsys.readouterr()
        assert "REQUIRED NEXT ACTION" in captured.err
