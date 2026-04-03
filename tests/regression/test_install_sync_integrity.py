#!/usr/bin/env python3
"""
Regression tests for install/sync infrastructure integrity.

Verifies that templates, manifests, and hook registrations are consistent
and that the sync operation is idempotent (no duplicate hooks).

Issue: GitHub #648
Date: 2026-04-03
Agent: implementer
"""

import json
import re
import sys
import tempfile
from pathlib import Path

import pytest

# Repo and plugin directory constants
WORKTREE = Path(__file__).resolve().parents[2]  # repo root
PLUGIN_DIR = WORKTREE / "plugins" / "autonomous-dev"

# Add scripts and lib to path for imports
sys.path.insert(0, str(PLUGIN_DIR / "scripts"))
sys.path.insert(0, str(PLUGIN_DIR / "lib"))


def _write_json(path: Path, data: dict) -> None:
    """Helper to write JSON to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    """Helper to read JSON from a file."""
    return json.loads(path.read_text(encoding="utf-8"))


# ============================================================================
# TestSyncIdempotent - Verify no duplicate hooks on repeated sync
# ============================================================================


class TestSyncIdempotent:
    """Verify that sync operations are idempotent (no duplicate hooks)."""

    def test_sync_global_idempotent(self):
        """Run _replace_hooks twice with global template, settings identical both times."""
        from sync_settings_hooks import _replace_hooks

        template_path = PLUGIN_DIR / "config" / "global_settings_template.json"
        assert template_path.exists(), f"Global template missing: {template_path}"

        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / ".claude" / "settings.json"

            # First run
            result1 = _replace_hooks(settings_path, template_path)
            data1 = _read_json(settings_path)

            # Second run
            result2 = _replace_hooks(settings_path, template_path)
            data2 = _read_json(settings_path)

            assert result1["success"] is True
            assert result2["success"] is True
            assert data1 == data2, "Settings differ after second sync -- hooks duplicated"
            assert data1["hooks"] == data2["hooks"], "Hooks differ after second sync"

    def test_sync_repo_idempotent(self):
        """Run _replace_hooks twice with repo template, settings identical both times."""
        from sync_settings_hooks import _replace_hooks

        template_path = PLUGIN_DIR / "templates" / "settings.default.json"
        assert template_path.exists(), f"Repo template missing: {template_path}"

        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / ".claude" / "settings.json"

            # First run
            result1 = _replace_hooks(settings_path, template_path)
            data1 = _read_json(settings_path)

            # Second run
            result2 = _replace_hooks(settings_path, template_path)
            data2 = _read_json(settings_path)

            assert result1["success"] is True
            assert result2["success"] is True
            assert data1 == data2, "Settings differ after second sync -- hooks duplicated"

    def test_sync_preserves_user_config(self):
        """After sync, mcpServers/permissions/enabledPlugins are preserved."""
        from sync_settings_hooks import _replace_hooks

        template_path = PLUGIN_DIR / "config" / "global_settings_template.json"

        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"

            # Pre-populate with user config
            user_config = {
                "hooks": {},
                "mcpServers": {
                    "my-custom-server": {"url": "http://localhost:9999"}
                },
                "permissions": {
                    "allow": ["Read", "Write", "MyCustomTool"],
                    "deny": ["Bash(rm -rf /)"],
                },
                "enabledPlugins": ["my-plugin-a", "my-plugin-b"],
                "customKey": "should-survive",
            }
            _write_json(settings_path, user_config)

            result = _replace_hooks(settings_path, template_path)
            assert result["success"] is True

            data = _read_json(settings_path)

            # Hooks replaced from template
            template_data = _read_json(template_path)
            assert data["hooks"] == template_data["hooks"]

            # User config preserved
            assert data["mcpServers"]["my-custom-server"]["url"] == "http://localhost:9999"
            assert "MyCustomTool" in data["permissions"]["allow"]
            assert "my-plugin-a" in data["enabledPlugins"]
            assert "my-plugin-b" in data["enabledPlugins"]
            assert data["customKey"] == "should-survive"


# ============================================================================
# TestInstallShHooks - Verify install infrastructure includes .sh hooks
# ============================================================================


class TestInstallShHooks:
    """Verify install infrastructure handles .sh hook files."""

    def test_manifest_includes_sh_hooks(self):
        """install_manifest.json has .sh hook files listed."""
        manifest_path = PLUGIN_DIR / "install_manifest.json"
        assert manifest_path.exists(), f"Manifest missing: {manifest_path}"

        manifest = _read_json(manifest_path)
        hook_files = manifest["components"]["hooks"]["files"]

        sh_hooks = [f for f in hook_files if f.endswith(".sh")]
        assert len(sh_hooks) > 0, "No .sh hooks in manifest"

        # Specifically check the known .sh hooks
        sh_basenames = [Path(f).name for f in sh_hooks]
        assert "post_compact_enricher.sh" in sh_basenames, "post_compact_enricher.sh missing"
        assert "pre_compact_batch_saver.sh" in sh_basenames, "pre_compact_batch_saver.sh missing"

    def test_install_sh_includes_sh_pattern(self):
        """Verify that .sh hook files actually exist on disk (install would find them)."""
        hooks_dir = PLUGIN_DIR / "hooks"
        sh_files = list(hooks_dir.glob("*.sh"))

        # There should be at least 2 .sh hooks (pre_compact_batch_saver.sh, post_compact_enricher.sh)
        assert len(sh_files) >= 2, (
            f"Expected at least 2 .sh hook files, found {len(sh_files)}: "
            f"{[f.name for f in sh_files]}"
        )


# ============================================================================
# TestTemplateIntegrity - Verify template files are correct
# ============================================================================


class TestTemplateIntegrity:
    """Verify template files have correct hook configurations."""

    # The 8 standard lifecycle events
    EXPECTED_EVENTS = {
        "PreToolUse",
        "PostToolUse",
        "UserPromptSubmit",
        "PreCompact",
        "PostCompact",
        "Stop",
        "SubagentStop",
        "TaskCompleted",
    }

    def test_global_template_stop_hook_correct(self):
        """Stop hook in global template points to stop_quality_gate.py."""
        template_path = PLUGIN_DIR / "config" / "global_settings_template.json"
        data = _read_json(template_path)

        stop_hooks = data["hooks"]["Stop"]
        assert len(stop_hooks) >= 1

        # Find the command in the Stop hook
        commands = []
        for matcher_config in stop_hooks:
            for hook in matcher_config.get("hooks", []):
                commands.append(hook.get("command", ""))

        assert any("stop_quality_gate.py" in cmd for cmd in commands), (
            f"Stop hook should reference stop_quality_gate.py, "
            f"but found commands: {commands}"
        )

    def test_global_template_has_all_lifecycle_events(self):
        """Global template has all 8 standard lifecycle events."""
        template_path = PLUGIN_DIR / "config" / "global_settings_template.json"
        data = _read_json(template_path)

        hook_events = set(data.get("hooks", {}).keys())
        missing = self.EXPECTED_EVENTS - hook_events
        assert not missing, f"Global template missing lifecycle events: {missing}"

    def test_default_template_has_all_lifecycle_events(self):
        """settings.default.json has all 8 standard lifecycle events."""
        template_path = PLUGIN_DIR / "templates" / "settings.default.json"
        data = _read_json(template_path)

        hook_events = set(data.get("hooks", {}).keys())
        missing = self.EXPECTED_EVENTS - hook_events
        assert not missing, f"Default template missing lifecycle events: {missing}"

    def test_all_templates_have_consistent_hooks(self):
        """All settings.*.json templates have at least the 8 standard lifecycle events."""
        templates_dir = PLUGIN_DIR / "templates"
        template_files = sorted(templates_dir.glob("settings.*.json"))

        assert len(template_files) >= 2, (
            f"Expected at least 2 settings templates, found {len(template_files)}"
        )

        for template_file in template_files:
            data = _read_json(template_file)
            hook_events = set(data.get("hooks", {}).keys())
            missing = self.EXPECTED_EVENTS - hook_events
            assert not missing, (
                f"{template_file.name} missing lifecycle events: {missing}"
            )


# ============================================================================
# TestHookRegistration - Verify hooks are registered and exist
# ============================================================================


class TestHookRegistration:
    """Verify hook files are registered in manifest and exist on disk."""

    def test_all_hook_files_in_manifest(self):
        """Every .py and .sh in hooks/ dir is in manifest (excluding hook configs)."""
        hooks_dir = PLUGIN_DIR / "hooks"
        manifest_path = PLUGIN_DIR / "install_manifest.json"
        manifest = _read_json(manifest_path)

        manifest_hook_files = set(manifest["components"]["hooks"]["files"])
        manifest_basenames = {Path(f).name for f in manifest_hook_files}

        # Hook config files use CamelCase-hyphen naming (e.g., SessionStart-batch-recovery.sh)
        # and are NOT managed through the manifest. Only snake_case hooks are manifest-managed.
        # Also exclude .hook.json config files and coverage files.
        def _is_managed_hook(filename: str) -> bool:
            """Return True if this is a manifest-managed hook (not a config file)."""
            if filename.endswith(",cover"):
                return False
            # Hook config .sh files use CamelCase-hyphen patterns
            if "-" in filename and filename[0].isupper():
                return False
            return filename.endswith(".py") or filename.endswith(".sh")

        actual_hooks = [
            f.name for f in hooks_dir.iterdir()
            if f.is_file() and _is_managed_hook(f.name)
        ]

        missing_from_manifest = [
            name for name in actual_hooks
            if name not in manifest_basenames
        ]

        assert not missing_from_manifest, (
            f"Hook files on disk but NOT in manifest: {missing_from_manifest}"
        )

    def test_manifest_hooks_exist_on_disk(self):
        """Every hook in manifest exists as a real file.

        Known exception: batch_permission_approver.py is listed in the manifest
        but was removed from disk. This is a pre-existing manifest inconsistency
        tracked separately.
        """
        manifest_path = PLUGIN_DIR / "install_manifest.json"
        manifest = _read_json(manifest_path)

        # Pre-existing manifest inconsistencies (tracked separately)
        KNOWN_MISSING = {"batch_permission_approver.py"}

        hook_files = manifest["components"]["hooks"]["files"]
        missing = []

        for hook_rel_path in hook_files:
            hook_path = WORKTREE / hook_rel_path
            if not hook_path.exists():
                basename = Path(hook_rel_path).name
                if basename not in KNOWN_MISSING:
                    missing.append(hook_rel_path)

        assert not missing, f"Manifest hooks missing on disk: {missing}"

    def test_global_template_hooks_point_to_real_files(self):
        """Every command in global template references a file that exists in hooks/ dir."""
        template_path = PLUGIN_DIR / "config" / "global_settings_template.json"
        data = _read_json(template_path)

        hooks_dir = PLUGIN_DIR / "hooks"
        # Get basenames of all hook files on disk
        disk_hooks = {f.name for f in hooks_dir.iterdir() if f.is_file()}

        missing = []
        for event, matchers in data.get("hooks", {}).items():
            for matcher_config in matchers:
                for hook in matcher_config.get("hooks", []):
                    cmd = hook.get("command", "")
                    # Extract filename from command like "python3 ~/.claude/hooks/foo.py"
                    # or "bash ~/.claude/hooks/bar.sh"
                    # or "ENV=val python3 ~/.claude/hooks/baz.py"
                    match = re.search(r"hooks/([a-zA-Z0-9_]+\.(?:py|sh))", cmd)
                    if match:
                        hook_filename = match.group(1)
                        if hook_filename not in disk_hooks:
                            missing.append(
                                f"{event}: {hook_filename} (from cmd: {cmd})"
                            )

        assert not missing, (
            f"Global template references hooks not found on disk: {missing}"
        )
