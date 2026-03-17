"""
Regression tests for Issue #463: TaskCompleted hook event registration.

Validates that the TaskCompleted hook is properly wired:
1. Hook file exists on disk
2. Registered in all 6 settings templates
3. Registered in global_settings_template.json
4. Listed in install_manifest.json
5. TaskCompleted lifecycle constraint exists in hook_exit_codes.py

Root cause: TaskCompleted is a preparation hook for future pipeline gate checks.
If it's registered but the file is missing (or vice versa), the hook system breaks.
"""

import json
import sys
from pathlib import Path

import pytest

# Portable project root detection
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

PLUGIN_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev"
HOOKS_DIR = PLUGIN_DIR / "hooks"
TEMPLATES_DIR = PLUGIN_DIR / "templates"
CONFIG_DIR = PLUGIN_DIR / "config"
LIB_DIR = PLUGIN_DIR / "lib"

SETTINGS_TEMPLATES = [
    TEMPLATES_DIR / "settings.autonomous-dev.json",
    TEMPLATES_DIR / "settings.default.json",
    TEMPLATES_DIR / "settings.granular-bash.json",
    TEMPLATES_DIR / "settings.local.json",
    TEMPLATES_DIR / "settings.permission-batching.json",
    TEMPLATES_DIR / "settings.strict-mode.json",
]

GLOBAL_SETTINGS = CONFIG_DIR / "global_settings_template.json"
MANIFEST_PATH = CONFIG_DIR / "install_manifest.json"


class TestTaskCompletedHookFileExists:
    """Verify the hook file exists on disk."""

    def test_hook_file_exists(self):
        """task_completed_handler.py must exist in hooks directory."""
        hook_file = HOOKS_DIR / "task_completed_handler.py"
        assert hook_file.exists(), (
            f"Hook file missing: {hook_file}\n"
            f"Expected task_completed_handler.py in {HOOKS_DIR}"
        )

    def test_hook_file_is_python(self):
        """Hook file must be valid Python (parseable)."""
        hook_file = HOOKS_DIR / "task_completed_handler.py"
        import ast
        source = hook_file.read_text()
        # Should not raise SyntaxError
        ast.parse(source)


class TestTaskCompletedRegisteredInTemplates:
    """Verify TaskCompleted is registered in all settings templates."""

    @pytest.mark.parametrize("template_path", SETTINGS_TEMPLATES, ids=lambda p: p.name)
    def test_registered_in_settings_template(self, template_path):
        """TaskCompleted must be registered as a hook event in each template."""
        assert template_path.exists(), f"Template missing: {template_path}"
        settings = json.loads(template_path.read_text())
        hooks = settings.get("hooks", {})
        assert "TaskCompleted" in hooks, (
            f"TaskCompleted not registered in {template_path.name}\n"
            f"Available hook events: {list(hooks.keys())}"
        )

    @pytest.mark.parametrize("template_path", SETTINGS_TEMPLATES, ids=lambda p: p.name)
    def test_references_correct_handler(self, template_path):
        """TaskCompleted hook must reference task_completed_handler.py."""
        settings = json.loads(template_path.read_text())
        tc_hooks = settings["hooks"]["TaskCompleted"]
        # Find the command in the hook entries
        commands = []
        for entry in tc_hooks:
            for hook in entry.get("hooks", []):
                commands.append(hook.get("command", ""))
        assert any("task_completed_handler.py" in cmd for cmd in commands), (
            f"TaskCompleted hook in {template_path.name} does not reference "
            f"task_completed_handler.py. Commands found: {commands}"
        )

    def test_registered_in_global_settings(self):
        """TaskCompleted must be registered in global_settings_template.json."""
        assert GLOBAL_SETTINGS.exists(), f"Global settings missing: {GLOBAL_SETTINGS}"
        settings = json.loads(GLOBAL_SETTINGS.read_text())
        hooks = settings.get("hooks", {})
        assert "TaskCompleted" in hooks, (
            f"TaskCompleted not registered in global_settings_template.json\n"
            f"Available hook events: {list(hooks.keys())}"
        )


class TestTaskCompletedInManifest:
    """Verify hook is listed in install_manifest.json."""

    def test_in_install_manifest(self):
        """task_completed_handler.py must be in install_manifest hooks files."""
        assert MANIFEST_PATH.exists(), f"Manifest missing: {MANIFEST_PATH}"
        manifest = json.loads(MANIFEST_PATH.read_text())
        hook_files = manifest.get("components", {}).get("hooks", {}).get("files", [])
        expected = "plugins/autonomous-dev/hooks/task_completed_handler.py"
        assert expected in hook_files, (
            f"Hook not in install_manifest.json components.hooks.files\n"
            f"Expected: {expected}\n"
            f"Found: {hook_files}"
        )


class TestTaskCompletedLifecycleConstraint:
    """Verify lifecycle constraint is defined in hook_exit_codes.py."""

    def test_lifecycle_constraint_exists(self):
        """TaskCompleted must be in LIFECYCLE_CONSTRAINTS."""
        # Add lib to path for import
        sys.path.insert(0, str(LIB_DIR))
        try:
            from hook_exit_codes import LIFECYCLE_CONSTRAINTS
            assert "TaskCompleted" in LIFECYCLE_CONSTRAINTS, (
                f"TaskCompleted not in LIFECYCLE_CONSTRAINTS\n"
                f"Available lifecycles: {list(LIFECYCLE_CONSTRAINTS.keys())}"
            )
        finally:
            sys.path.pop(0)

    def test_lifecycle_cannot_block(self):
        """TaskCompleted hooks must not be able to block."""
        sys.path.insert(0, str(LIB_DIR))
        try:
            from hook_exit_codes import LIFECYCLE_CONSTRAINTS
            tc = LIFECYCLE_CONSTRAINTS["TaskCompleted"]
            assert tc["can_block"] is False, "TaskCompleted should not be able to block"
            assert tc["allowed_exits"] == [0], "TaskCompleted should only allow exit 0"
        finally:
            sys.path.pop(0)
