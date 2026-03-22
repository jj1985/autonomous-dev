#!/usr/bin/env python3
"""
Unit tests for sync_validator.py hook error handling.

Tests that the validator correctly handles object-format hook settings,
escalates missing hook files to errors, and resolves tilde paths.

Issue: #553
"""

import json
import os
import sys
import tempfile
from pathlib import Path

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

from sync_validator import SyncValidator, ValidationIssue


class TestObjectFormatHookValidation:
    """Tests for object-format hook settings validation."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory with .claude structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            claude_dir = project_path / ".claude"
            claude_dir.mkdir()
            (claude_dir / "hooks").mkdir()
            (claude_dir / "agents").mkdir()
            (claude_dir / "commands").mkdir()
            yield project_path

    def test_object_format_missing_hook_is_error(self, temp_project: Path) -> None:
        """Object-format settings with nonexistent command path reports severity=error."""
        settings_path = temp_project / ".claude" / "settings.local.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "*",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 /nonexistent/path/hook.py",
                                        "timeout": 5,
                                    }
                                ],
                            }
                        ]
                    }
                }
            )
        )

        validator = SyncValidator(temp_project)
        result = validator.validate_settings()

        assert result.passed is False, "Missing hook file should cause phase to fail"
        error_issues = [i for i in result.issues if i.severity == "error"]
        assert len(error_issues) >= 1, "Should have at least one error-severity issue"
        assert any(
            "hook.py" in i.message for i in error_issues
        ), "Error message should reference the missing hook file"
        # Should NOT be auto-fixable
        assert all(
            not i.auto_fixable for i in error_issues
        ), "Missing hook errors should not be auto-fixable"

    def test_object_format_existing_hooks_pass(self, temp_project: Path) -> None:
        """All hooks exist in object format -> no errors."""
        # Create the hook file
        hook_file = temp_project / ".claude" / "hooks" / "test_hook.py"
        hook_file.write_text("pass\n")

        settings_path = temp_project / ".claude" / "settings.local.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "*",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": f"python3 {hook_file}",
                                        "timeout": 5,
                                    }
                                ],
                            }
                        ]
                    }
                }
            )
        )

        validator = SyncValidator(temp_project)
        result = validator.validate_settings()

        assert result.passed is True, "Existing hook files should pass validation"
        hook_errors = [
            i
            for i in result.issues
            if i.category == "settings" and "hook" in i.message.lower()
        ]
        assert len(hook_errors) == 0, "Should have no hook-related issues"

    def test_tilde_expansion_in_hook_path(self, temp_project: Path) -> None:
        """Tilde paths like ~/.claude/hooks/test.py are resolved correctly."""
        # Create a hook in the user's home directory simulation
        # We'll use a real temp file and reference it with ~ pattern
        home = Path.home()
        # Create a temp file in a predictable location
        test_hook = home / ".claude_test_tilde_hook.py"
        try:
            test_hook.write_text("pass\n")

            settings_path = temp_project / ".claude" / "settings.local.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "PreToolUse": [
                                {
                                    "matcher": "*",
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": f"python3 ~/.claude_test_tilde_hook.py",
                                            "timeout": 5,
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                )
            )

            validator = SyncValidator(temp_project)
            result = validator.validate_settings()

            # The file exists, so no errors
            hook_errors = [
                i
                for i in result.issues
                if "hook" in i.message.lower() and i.severity == "error"
            ]
            assert (
                len(hook_errors) == 0
            ), "Tilde-expanded path to existing file should not produce errors"
        finally:
            if test_hook.exists():
                test_hook.unlink()

    def test_bash_hook_paths_checked(self, temp_project: Path) -> None:
        """Shell script (.sh) hooks are also validated."""
        settings_path = temp_project / ".claude" / "settings.local.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {
                                "matcher": "*",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "/nonexistent/path/startup.sh",
                                        "timeout": 10,
                                    }
                                ],
                            }
                        ]
                    }
                }
            )
        )

        validator = SyncValidator(temp_project)
        result = validator.validate_settings()

        assert result.passed is False, "Missing .sh hook should cause failure"
        error_issues = [i for i in result.issues if i.severity == "error"]
        assert any(
            "startup.sh" in i.message for i in error_issues
        ), "Error should reference the missing .sh file"

    def test_multiple_events_all_checked(self, temp_project: Path) -> None:
        """Multiple lifecycle events are all validated."""
        settings_path = temp_project / ".claude" / "settings.local.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "*",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 /missing/pre_tool.py",
                                    }
                                ],
                            }
                        ],
                        "PostToolUse": [
                            {
                                "matcher": "*",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 /missing/post_tool.py",
                                    }
                                ],
                            }
                        ],
                        "SessionStart": [
                            {
                                "matcher": "*",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "bash /missing/startup.sh",
                                    }
                                ],
                            }
                        ],
                    }
                }
            )
        )

        validator = SyncValidator(temp_project)
        result = validator.validate_settings()

        assert result.passed is False
        error_issues = [i for i in result.issues if i.severity == "error"]
        # Should detect all 3 missing files
        assert len(error_issues) >= 3, (
            f"Expected at least 3 error issues for 3 missing hooks, got {len(error_issues)}: "
            f"{[i.message for i in error_issues]}"
        )


class TestExtractHookPathsHelper:
    """Tests for the _extract_hook_paths_from_object_format static method."""

    def test_extracts_python_paths(self) -> None:
        """Extracts .py file paths from command strings."""
        hooks = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ~/.claude/hooks/unified_pre_tool.py",
                        }
                    ],
                }
            ]
        }
        paths = SyncValidator._extract_hook_paths_from_object_format(hooks)
        assert len(paths) == 1
        assert "unified_pre_tool.py" in paths[0]

    def test_extracts_shell_paths(self) -> None:
        """Extracts .sh file paths from command strings."""
        hooks = {
            "SessionStart": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash ~/.claude/hooks/startup.sh",
                        }
                    ],
                }
            ]
        }
        paths = SyncValidator._extract_hook_paths_from_object_format(hooks)
        assert len(paths) == 1
        assert "startup.sh" in paths[0]

    def test_empty_hooks_returns_empty(self) -> None:
        """Empty hooks dict returns empty list."""
        assert SyncValidator._extract_hook_paths_from_object_format({}) == []

    def test_skips_non_dict_entries(self) -> None:
        """Gracefully handles malformed hook entries."""
        hooks = {
            "PreToolUse": "not a list",
            "PostToolUse": [
                "not a dict",
                {"hooks": "not a list"},
                {"hooks": [{"command": "python3 /path/to/hook.py"}]},
            ],
        }
        paths = SyncValidator._extract_hook_paths_from_object_format(hooks)
        assert len(paths) == 1
        assert "hook.py" in paths[0]
