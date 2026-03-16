"""Tests for Issue #410: Worktree delete_worktree CWD safety.

Validates that delete_worktree() moves the process CWD out of the worktree
directory before attempting deletion, preventing shell crashes when the
directory is removed from under the running process.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LIB_DIR = PROJECT_ROOT / "plugins/autonomous-dev/lib"

# Import worktree_manager functions
import sys

sys.path.insert(0, str(LIB_DIR))


class TestDeleteWorktreeCwdSafety:
    """Validate CWD safety in delete_worktree."""

    @patch("worktree_manager.subprocess.run")
    @patch("worktree_manager._get_worktree_base_dir")
    @patch("worktree_manager._validate_feature_name")
    def test_chdir_called_when_cwd_inside_worktree(
        self, mock_validate, mock_base_dir, mock_run, tmp_path
    ):
        """When CWD is inside worktree, os.chdir should move to project root."""
        import worktree_manager

        # Setup
        mock_validate.return_value = (True, "")
        worktree_base = tmp_path / ".worktrees"
        worktree_base.mkdir()
        worktree_dir = worktree_base / "my-feature"
        worktree_dir.mkdir()

        mock_base_dir.return_value = worktree_base
        mock_run.return_value = MagicMock(returncode=0)

        # Move CWD into worktree
        original_cwd = os.getcwd()
        try:
            os.chdir(worktree_dir)

            success, msg = worktree_manager.delete_worktree("my-feature")

            # CWD should now be project root (parent of .worktrees), not worktree
            current = Path.cwd().resolve()
            assert str(current) == str(tmp_path.resolve()), (
                f"CWD should be project root {tmp_path}, got {current}"
            )
            assert success is True
        finally:
            os.chdir(original_cwd)

    @patch("worktree_manager.subprocess.run")
    @patch("worktree_manager._get_worktree_base_dir")
    @patch("worktree_manager._validate_feature_name")
    def test_no_chdir_when_cwd_outside_worktree(
        self, mock_validate, mock_base_dir, mock_run, tmp_path
    ):
        """When CWD is NOT inside worktree, CWD should not change."""
        import worktree_manager

        mock_validate.return_value = (True, "")
        worktree_base = tmp_path / ".worktrees"
        worktree_base.mkdir()
        worktree_dir = worktree_base / "my-feature"
        worktree_dir.mkdir()

        mock_base_dir.return_value = worktree_base
        mock_run.return_value = MagicMock(returncode=0)

        original_cwd = os.getcwd()
        try:
            # CWD is tmp_path, not inside worktree
            os.chdir(tmp_path)

            success, msg = worktree_manager.delete_worktree("my-feature")

            current = Path.cwd().resolve()
            assert str(current) == str(tmp_path.resolve()), (
                f"CWD should remain at {tmp_path}, got {current}"
            )
            assert success is True
        finally:
            os.chdir(original_cwd)

    @patch("worktree_manager.subprocess.run")
    @patch("worktree_manager._get_worktree_base_dir")
    @patch("worktree_manager._validate_feature_name")
    def test_chdir_to_project_root_on_nested_cwd(
        self, mock_validate, mock_base_dir, mock_run, tmp_path
    ):
        """When CWD is in a subdirectory of worktree, should still chdir out."""
        import worktree_manager

        mock_validate.return_value = (True, "")
        worktree_base = tmp_path / ".worktrees"
        worktree_base.mkdir()
        worktree_dir = worktree_base / "my-feature"
        worktree_dir.mkdir()
        nested_dir = worktree_dir / "src" / "deep"
        nested_dir.mkdir(parents=True)

        mock_base_dir.return_value = worktree_base
        mock_run.return_value = MagicMock(returncode=0)

        original_cwd = os.getcwd()
        try:
            os.chdir(nested_dir)

            success, msg = worktree_manager.delete_worktree("my-feature")

            current = Path.cwd().resolve()
            assert str(current) == str(tmp_path.resolve()), (
                f"CWD should be project root {tmp_path}, got {current}"
            )
            assert success is True
        finally:
            os.chdir(original_cwd)

    def test_invalid_feature_name_returns_error(self):
        """Invalid feature names should return error without any CWD changes."""
        import worktree_manager

        original_cwd = os.getcwd()
        try:
            success, msg = worktree_manager.delete_worktree("../../etc/passwd")
            assert success is False
            assert os.getcwd() == original_cwd
        finally:
            os.chdir(original_cwd)
