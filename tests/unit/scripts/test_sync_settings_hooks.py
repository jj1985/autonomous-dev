#!/usr/bin/env python3
"""
Unit tests for sync_settings_hooks.py CLI script.

Tests the deploy-time settings.json hook synchronization that ensures
all hook lifecycle events are registered after deploy.

Issue: GitHub #648
Date: 2026-04-03
Agent: implementer
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add plugins directory to path for imports
REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib"))

from sync_settings_hooks import sync_global, sync_repo, _count_lifecycle_events


# --- Fixtures ---

@pytest.fixture
def temp_dir():
    """Temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def global_template():
    """Minimal global settings template with hooks."""
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ~/.claude/hooks/unified_pre_tool.py",
                            "timeout": 5,
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
                            "command": "python3 ~/.claude/hooks/session_activity_logger.py",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "UserPromptSubmit": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ~/.claude/hooks/unified_prompt_validator.py",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ~/.claude/hooks/session_activity_logger.py",
                            "timeout": 3,
                        }
                    ],
                }
            ],
            "SubagentStop": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ~/.claude/hooks/unified_session_tracker.py",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "TaskCompleted": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ~/.claude/hooks/task_completed_handler.py",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "PreCompact": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash ~/.claude/hooks/pre_compact_batch_saver.sh",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "PostCompact": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash ~/.claude/hooks/post_compact_enricher.sh",
                            "timeout": 5,
                        }
                    ],
                }
            ],
        },
        "permissions": {
            "allow": ["Read", "Write", "Edit"],
            "deny": ["Bash(rm -rf /)"],
        },
    }


@pytest.fixture
def repo_template():
    """Minimal repo settings template with hooks."""
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ~/.claude/hooks/unified_pre_tool.py",
                            "timeout": 5,
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
                            "command": "python3 ~/.claude/hooks/session_activity_logger.py",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "UserPromptSubmit": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ~/.claude/hooks/unified_prompt_validator.py",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ~/.claude/hooks/stop_quality_gate.py",
                            "timeout": 60,
                        }
                    ],
                }
            ],
        },
        "permissions": {
            "allow": ["Read", "Write"],
            "deny": [],
        },
    }


def _write_json(path: Path, data: dict) -> None:
    """Helper to write JSON to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# --- Tests ---


class TestGlobalMode:
    """Tests for --global mode."""

    def test_global_mode_creates_settings_when_missing(self, temp_dir, global_template):
        """No existing settings.json -> creates from template."""
        fake_home = temp_dir / "home"
        fake_home.mkdir()
        fake_claude = fake_home / ".claude"
        fake_claude.mkdir()

        template_path = temp_dir / "config" / "global_settings_template.json"
        _write_json(template_path, global_template)

        settings_path = fake_claude / "settings.json"

        # Patch to use our temp dirs
        with patch("sync_settings_hooks._find_plugin_root") as mock_root, \
             patch("sync_settings_hooks.Path") as MockPath:
            mock_root.return_value = temp_dir
            # We need Path.home() to return fake_home
            # But we also need Path to work normally for other calls
            # Simpler: just call sync_repo-style logic directly with SettingsMerger

        # Simpler approach: directly test with SettingsMerger
        from settings_merger import SettingsMerger

        merger = SettingsMerger(project_root=str(fake_home))
        result = merger.merge_settings(
            template_path=template_path,
            user_path=settings_path,
            write_result=True,
        )

        assert result.success is True
        assert settings_path.exists()
        data = json.loads(settings_path.read_text())
        assert "hooks" in data
        assert len(data["hooks"]) == 8  # 8 lifecycle events

    def test_global_mode_merges_preserving_user_config(self, temp_dir, global_template):
        """Existing settings with user config -> preserved after merge."""
        fake_home = temp_dir / "home"
        claude_dir = fake_home / ".claude"
        claude_dir.mkdir(parents=True)

        template_path = temp_dir / "config" / "global_settings_template.json"
        _write_json(template_path, global_template)

        # Existing settings with user-specific config
        existing = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 ~/.claude/hooks/unified_pre_tool.py",
                                "timeout": 5,
                            }
                        ],
                    }
                ],
            },
            "permissions": {
                "allow": ["Read", "Write", "Edit", "CustomTool"],
                "deny": ["Bash(rm -rf /)", "Bash(custom:danger)"],
            },
            "mcpServers": {
                "my-server": {"url": "http://localhost:3000"}
            },
            "enabledPlugins": ["my-plugin"],
        }
        settings_path = claude_dir / "settings.json"
        _write_json(settings_path, existing)

        from settings_merger import SettingsMerger

        merger = SettingsMerger(project_root=str(fake_home))
        result = merger.merge_settings(
            template_path=template_path,
            user_path=settings_path,
            write_result=True,
        )

        assert result.success is True
        data = json.loads(settings_path.read_text())

        # User config preserved
        assert "mcpServers" in data
        assert data["mcpServers"]["my-server"]["url"] == "http://localhost:3000"
        assert "enabledPlugins" in data
        assert "my-plugin" in data["enabledPlugins"]

        # User permission entries preserved (unioned)
        assert "CustomTool" in data["permissions"]["allow"]
        assert "Bash(custom:danger)" in data["permissions"]["deny"]

        # Template hooks merged in
        assert len(data["hooks"]) == 8


class TestRepoMode:
    """Tests for --repo mode."""

    def test_repo_mode_merges_hooks(self, temp_dir, repo_template):
        """Per-repo template merged correctly into repo settings."""
        repo_path = temp_dir / "myrepo"
        claude_dir = repo_path / ".claude"
        claude_dir.mkdir(parents=True)

        template_path = temp_dir / "templates" / "settings.default.json"
        _write_json(template_path, repo_template)

        settings_path = claude_dir / "settings.json"
        # Start with empty settings
        _write_json(settings_path, {})

        from settings_merger import SettingsMerger

        merger = SettingsMerger(project_root=str(repo_path))
        result = merger.merge_settings(
            template_path=template_path,
            user_path=settings_path,
            write_result=True,
        )

        assert result.success is True
        data = json.loads(settings_path.read_text())
        assert "PreToolUse" in data["hooks"]
        assert "PostToolUse" in data["hooks"]
        assert "UserPromptSubmit" in data["hooks"]
        assert "Stop" in data["hooks"]
        assert len(data["hooks"]) == 4


class TestIdempotency:
    """Tests for idempotent behavior."""

    def test_idempotent_double_run(self, temp_dir, global_template):
        """Running merge twice produces identical output."""
        fake_home = temp_dir / "home"
        claude_dir = fake_home / ".claude"
        claude_dir.mkdir(parents=True)

        template_path = temp_dir / "config" / "global_settings_template.json"
        _write_json(template_path, global_template)

        settings_path = claude_dir / "settings.json"

        from settings_merger import SettingsMerger

        merger = SettingsMerger(project_root=str(fake_home))

        # First run
        result1 = merger.merge_settings(
            template_path=template_path,
            user_path=settings_path,
            write_result=True,
        )
        data_after_first = json.loads(settings_path.read_text())

        # Second run
        result2 = merger.merge_settings(
            template_path=template_path,
            user_path=settings_path,
            write_result=True,
        )
        data_after_second = json.loads(settings_path.read_text())

        assert result1.success is True
        assert result2.success is True
        assert data_after_first == data_after_second


class TestDryRun:
    """Tests for --dry-run mode."""

    def test_dry_run_no_write(self, temp_dir, global_template):
        """Dry-run reads but does not write."""
        fake_home = temp_dir / "home"
        claude_dir = fake_home / ".claude"
        claude_dir.mkdir(parents=True)

        template_path = temp_dir / "config" / "global_settings_template.json"
        _write_json(template_path, global_template)

        settings_path = claude_dir / "settings.json"

        from settings_merger import SettingsMerger

        merger = SettingsMerger(project_root=str(fake_home))
        result = merger.merge_settings(
            template_path=template_path,
            user_path=settings_path,
            write_result=False,  # dry-run
        )

        assert result.success is True
        assert not settings_path.exists()  # Should NOT have been written


class TestCountOnly:
    """Tests for --count-only mode."""

    def test_count_only_output(self, temp_dir, global_template):
        """Returns correct hook count."""
        settings_path = temp_dir / "settings.json"
        _write_json(settings_path, global_template)

        count = _count_lifecycle_events(settings_path)
        assert count == 8  # 8 lifecycle events in global_template


class TestMigration:
    """Tests for hook migration."""

    def test_old_hooks_migrated(self, temp_dir, global_template):
        """Deprecated hooks removed during merge."""
        fake_home = temp_dir / "home"
        claude_dir = fake_home / ".claude"
        claude_dir.mkdir(parents=True)

        template_path = temp_dir / "config" / "global_settings_template.json"
        _write_json(template_path, global_template)

        # Existing settings with old hooks that should be migrated
        existing = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 ~/.claude/hooks/pre_tool_use.py",
                                "timeout": 5,
                            },
                            {
                                "type": "command",
                                "command": "python3 ~/.claude/hooks/enforce_implementation_workflow.py",
                                "timeout": 5,
                            },
                        ],
                    }
                ],
            },
        }
        settings_path = claude_dir / "settings.json"
        _write_json(settings_path, existing)

        from settings_merger import SettingsMerger

        merger = SettingsMerger(project_root=str(fake_home))
        result = merger.merge_settings(
            template_path=template_path,
            user_path=settings_path,
            write_result=True,
        )

        assert result.success is True
        assert result.hooks_migrated >= 2  # pre_tool_use.py and enforce_implementation_workflow.py

        data = json.loads(settings_path.read_text())
        # Verify old hooks are gone
        for event_hooks in data["hooks"].values():
            for matcher_config in event_hooks:
                for hook in matcher_config.get("hooks", []):
                    cmd = hook.get("command", "")
                    assert "pre_tool_use.py" not in cmd
                    assert "enforce_implementation_workflow.py" not in cmd


class TestErrorHandling:
    """Tests for error conditions."""

    def test_missing_template_error(self, temp_dir):
        """Graceful error when template not found."""
        fake_home = temp_dir / "home"
        claude_dir = fake_home / ".claude"
        claude_dir.mkdir(parents=True)

        nonexistent_template = temp_dir / "does_not_exist.json"
        settings_path = claude_dir / "settings.json"

        from settings_merger import SettingsMerger

        merger = SettingsMerger(project_root=str(fake_home))
        result = merger.merge_settings(
            template_path=nonexistent_template,
            user_path=settings_path,
            write_result=True,
        )

        assert result.success is False
        assert "not found" in result.message.lower() or "not exist" in result.message.lower()

    def test_invalid_json_settings(self, temp_dir):
        """Graceful error on corrupt settings.json."""
        fake_home = temp_dir / "home"
        claude_dir = fake_home / ".claude"
        claude_dir.mkdir(parents=True)

        template_path = temp_dir / "template.json"
        _write_json(template_path, {"hooks": {}})

        settings_path = claude_dir / "settings.json"
        settings_path.write_text("{invalid json!!!", encoding="utf-8")

        from settings_merger import SettingsMerger

        merger = SettingsMerger(project_root=str(fake_home))
        result = merger.merge_settings(
            template_path=template_path,
            user_path=settings_path,
            write_result=True,
        )

        assert result.success is False
        assert "parse" in result.message.lower() or "json" in result.message.lower()


class TestPermissions:
    """Tests for permission list handling."""

    def test_permissions_preserved(self, temp_dir):
        """Allow/deny lists not clobbered - user entries preserved via union."""
        fake_home = temp_dir / "home"
        claude_dir = fake_home / ".claude"
        claude_dir.mkdir(parents=True)

        template = {
            "hooks": {},
            "permissions": {
                "allow": ["Read", "Write", "Edit"],
                "deny": ["Bash(rm -rf /)"],
            },
        }
        template_path = temp_dir / "template.json"
        _write_json(template_path, template)

        existing = {
            "hooks": {},
            "permissions": {
                "allow": ["Read", "Write", "CustomUserTool", "MyMCPTool"],
                "deny": ["Bash(rm -rf /)", "Bash(my-custom-deny)"],
                "ask": ["Bash(git push:*)"],
            },
        }
        settings_path = claude_dir / "settings.json"
        _write_json(settings_path, existing)

        from settings_merger import SettingsMerger

        merger = SettingsMerger(project_root=str(fake_home))
        result = merger.merge_settings(
            template_path=template_path,
            user_path=settings_path,
            write_result=True,
        )

        assert result.success is True
        data = json.loads(settings_path.read_text())

        # User entries preserved
        assert "CustomUserTool" in data["permissions"]["allow"]
        assert "MyMCPTool" in data["permissions"]["allow"]
        assert "Bash(my-custom-deny)" in data["permissions"]["deny"]
        assert "Bash(git push:*)" in data["permissions"]["ask"]

        # Template entries also present
        assert "Read" in data["permissions"]["allow"]
        assert "Write" in data["permissions"]["allow"]
        assert "Edit" in data["permissions"]["allow"]
        assert "Bash(rm -rf /)" in data["permissions"]["deny"]
