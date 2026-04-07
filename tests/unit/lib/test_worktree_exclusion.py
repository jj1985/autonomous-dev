"""Regression tests for worktree exclusion in test discovery.

Bug: TestLifecycleManager and TestPruningAnalyzer used rglob without
excluding .worktrees/ directories, causing inflated file counts (140K+
instead of ~1K) when multiple worktrees exist.

Issue: #691
Date fixed: 2026-04-07
"""

from pathlib import Path

import pytest


class TestWorktreeExclusionLifecycleManager:
    """Verify TestLifecycleManager excludes .worktrees/ from scans."""

    def test_collect_test_paths_excludes_worktrees(self, tmp_path: Path) -> None:
        """Test files inside .worktrees/ are excluded from collection.

        This test would FAIL without the fix because _collect_test_paths
        previously did not filter .worktrees paths.
        """
        # Arrange: create a real test file and a worktree copy
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        real_test = tests_dir / "test_real.py"
        real_test.write_text("def test_example(): pass\n")

        worktree_tests = tests_dir / ".worktrees" / "batch-123" / "tests"
        worktree_tests.mkdir(parents=True)
        worktree_test = worktree_tests / "test_duplicate.py"
        worktree_test.write_text("def test_example(): pass\n")

        # Act
        from test_lifecycle_manager import TestLifecycleManager

        manager = TestLifecycleManager(project_root=tmp_path)
        paths = manager._collect_test_paths()

        # Assert: only the real test, not the worktree copy
        assert len(paths) == 1
        assert "test_real.py" in paths[0]
        assert ".worktrees" not in paths[0]

    def test_collect_test_paths_no_false_exclusion(self, tmp_path: Path) -> None:
        """Ensure normal test files are NOT excluded."""
        tests_dir = tmp_path / "tests" / "unit"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_alpha.py").write_text("pass\n")
        (tests_dir / "test_beta.py").write_text("pass\n")

        from test_lifecycle_manager import TestLifecycleManager

        manager = TestLifecycleManager(project_root=tmp_path)
        paths = manager._collect_test_paths()

        assert len(paths) == 2


class TestWorktreeExclusionPruningAnalyzer:
    """Verify TestPruningAnalyzer excludes .worktrees/ from scans."""

    def test_discover_test_files_excludes_worktrees(self, tmp_path: Path) -> None:
        """Test files inside .worktrees/ are excluded from discovery.

        This test would FAIL without the fix because .worktrees was not
        in the SKIP_DIRS set.
        """
        # Arrange
        real_test = tmp_path / "tests" / "test_real.py"
        real_test.parent.mkdir(parents=True)
        real_test.write_text("def test_example(): pass\n")

        worktree_test = tmp_path / ".worktrees" / "batch-1" / "tests" / "test_dup.py"
        worktree_test.parent.mkdir(parents=True)
        worktree_test.write_text("def test_example(): pass\n")

        # Act
        from test_pruning_analyzer import TestPruningAnalyzer

        analyzer = TestPruningAnalyzer(project_root=tmp_path)
        files = analyzer._discover_test_files()

        # Assert
        filenames = [f.name for f in files]
        assert "test_real.py" in filenames
        assert "test_dup.py" not in filenames

    def test_worktrees_in_skip_dirs(self) -> None:
        """Verify .worktrees is present in the SKIP_DIRS constant."""
        from test_pruning_analyzer import TestPruningAnalyzer

        assert ".worktrees" in TestPruningAnalyzer.SKIP_DIRS

    def test_discover_source_modules_excludes_worktrees(self, tmp_path: Path) -> None:
        """Source modules inside .worktrees/ are excluded from discovery."""
        # Arrange: create lib dir with a real module
        lib_dir = tmp_path / "plugins" / "autonomous-dev" / "lib"
        lib_dir.mkdir(parents=True)
        (lib_dir / "real_module.py").write_text("x = 1\n")

        # Create worktree copy inside lib
        worktree_lib = lib_dir / ".worktrees" / "batch-1" / "plugins" / "autonomous-dev" / "lib"
        worktree_lib.mkdir(parents=True)
        (worktree_lib / "fake_module.py").write_text("x = 1\n")

        # Act
        from test_pruning_analyzer import TestPruningAnalyzer

        analyzer = TestPruningAnalyzer(project_root=tmp_path)
        modules = analyzer._collect_source_modules()

        # Assert
        assert "real_module" in modules
        assert "fake_module" not in modules
