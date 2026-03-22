#!/usr/bin/env python3
"""
Unit tests for hook config generator integration in sync dispatcher.

Tests that the generator is invoked during sync, respects --no-generate,
and failures are non-blocking.

Issue: #553
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Add plugins directory to path for imports
sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "lib"
    ),
)

from sync_dispatcher.modes import _run_hook_config_generator


class TestRunHookConfigGenerator:
    """Tests for the _run_hook_config_generator helper function."""

    @pytest.fixture
    def mock_dispatcher(self, tmp_path: Path):
        """Create a mock dispatcher with a valid project path."""
        dispatcher = MagicMock()
        dispatcher.project_path = tmp_path
        dispatcher._no_generate = False

        # Create the required directories
        (tmp_path / "scripts").mkdir()
        (tmp_path / ".claude" / "hooks").mkdir(parents=True)
        (tmp_path / ".claude" / "config").mkdir(parents=True)

        return dispatcher

    def test_dispatch_github_invokes_generator(
        self, mock_dispatcher: MagicMock, tmp_path: Path
    ) -> None:
        """Generator script is called when it exists and _no_generate is False."""
        # Create the generator script
        script_path = tmp_path / "scripts" / "generate_hook_config.py"
        script_path.write_text("# stub generator\n")

        with patch(
            "sync_dispatcher.modes.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _run_hook_config_generator(mock_dispatcher)

            mock_run.assert_called_once()
            args = mock_run.call_args
            cmd = args[0][0]  # First positional arg is the command list
            assert str(script_path) in cmd
            assert "--write" in cmd
            assert "--hooks-dir" in cmd
            assert "--manifest-path" in cmd
            assert "--settings-path" in cmd

    def test_no_generate_flag_skips_generator(
        self, mock_dispatcher: MagicMock, tmp_path: Path
    ) -> None:
        """When _no_generate is True, generator is not called."""
        mock_dispatcher._no_generate = True

        # Create the generator script
        script_path = tmp_path / "scripts" / "generate_hook_config.py"
        script_path.write_text("# stub generator\n")

        with patch(
            "sync_dispatcher.modes.subprocess.run"
        ) as mock_run:
            _run_hook_config_generator(mock_dispatcher)
            mock_run.assert_not_called()

    def test_generator_failure_non_blocking(
        self, mock_dispatcher: MagicMock, tmp_path: Path
    ) -> None:
        """Generator returning exit code 1 does not raise or fail sync."""
        script_path = tmp_path / "scripts" / "generate_hook_config.py"
        script_path.write_text("# stub generator\n")

        with patch(
            "sync_dispatcher.modes.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Error occurred"
            )
            # Should not raise
            _run_hook_config_generator(mock_dispatcher)
            mock_run.assert_called_once()

    def test_generator_missing_non_blocking(
        self, mock_dispatcher: MagicMock, tmp_path: Path
    ) -> None:
        """When generator script doesn't exist, function returns silently."""
        # Don't create any script file
        # Should not raise
        _run_hook_config_generator(mock_dispatcher)

    def test_generator_subprocess_exception_non_blocking(
        self, mock_dispatcher: MagicMock, tmp_path: Path
    ) -> None:
        """Subprocess exceptions (e.g., timeout) are caught and don't propagate."""
        script_path = tmp_path / "scripts" / "generate_hook_config.py"
        script_path.write_text("# stub generator\n")

        with patch(
            "sync_dispatcher.modes.subprocess.run"
        ) as mock_run:
            import subprocess

            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="generate_hook_config.py", timeout=30
            )
            # Should not raise
            _run_hook_config_generator(mock_dispatcher)

    def test_generator_found_in_claude_scripts(
        self, mock_dispatcher: MagicMock, tmp_path: Path
    ) -> None:
        """Generator is found in .claude/scripts/ as fallback."""
        # Don't create in project scripts/, create in .claude/scripts/
        scripts_dir = tmp_path / ".claude" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_path = scripts_dir / "generate_hook_config.py"
        script_path.write_text("# stub generator\n")

        with patch(
            "sync_dispatcher.modes.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _run_hook_config_generator(mock_dispatcher)

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert str(script_path) in cmd


class TestDispatcherNoGenerateFlag:
    """Tests that SyncDispatcher stores the no_generate flag."""

    def test_dispatcher_stores_no_generate_flag(self, tmp_path: Path) -> None:
        """SyncDispatcher.__init__ stores no_generate as _no_generate."""
        # Create a valid project directory
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        with patch("sync_dispatcher.dispatcher.validate_path", return_value=str(project_dir)):
            from sync_dispatcher.dispatcher import SyncDispatcher

            dispatcher = SyncDispatcher(
                project_path=str(project_dir), no_generate=True
            )
            assert dispatcher._no_generate is True

    def test_dispatcher_default_no_generate_false(self, tmp_path: Path) -> None:
        """SyncDispatcher defaults _no_generate to False."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        with patch("sync_dispatcher.dispatcher.validate_path", return_value=str(project_dir)):
            from sync_dispatcher.dispatcher import SyncDispatcher

            dispatcher = SyncDispatcher(project_path=str(project_dir))
            assert dispatcher._no_generate is False
