"""Regression test: Verify PreCompact/PostCompact hooks are registered in all settings templates.

Issue #464: PreCompact/PostCompact hooks for batch state preservation.

Ensures that the compaction hooks are wired into all 6 settings templates
and the global settings template, preventing silent deregistration.
"""

import json
from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = WORKTREE / "plugins" / "autonomous-dev" / "templates"
CONFIG_DIR = WORKTREE / "plugins" / "autonomous-dev" / "config"

SETTINGS_TEMPLATES = [
    "settings.autonomous-dev.json",
    "settings.default.json",
    "settings.local.json",
    "settings.granular-bash.json",
    "settings.permission-batching.json",
    "settings.strict-mode.json",
]


class TestPreCompactHookRegistration:
    """Verify PreCompact hook is registered in all settings templates."""

    @pytest.mark.parametrize("template_name", SETTINGS_TEMPLATES)
    def test_template_has_pre_compact_hook(self, template_name: str):
        """Each settings template must have a PreCompact hook entry."""
        template_path = TEMPLATES_DIR / template_name
        assert template_path.exists(), f"Template not found: {template_path}"

        settings = json.loads(template_path.read_text())
        hooks = settings.get("hooks", {})
        assert "PreCompact" in hooks, (
            f"{template_name} missing PreCompact hook section"
        )

        pre_compact = hooks["PreCompact"]
        assert len(pre_compact) > 0, f"{template_name} PreCompact has no entries"

        # Verify matcher and command reference the correct script
        entry = pre_compact[0]
        assert entry["matcher"] == "*"
        hook_list = entry.get("hooks", [])
        assert len(hook_list) > 0
        assert "pre_compact_batch_saver.sh" in hook_list[0]["command"]

    def test_global_settings_has_pre_compact_hook(self):
        """Global settings template must have PreCompact hook."""
        path = CONFIG_DIR / "global_settings_template.json"
        assert path.exists()

        settings = json.loads(path.read_text())
        hooks = settings.get("hooks", {})
        assert "PreCompact" in hooks
        assert "pre_compact_batch_saver.sh" in hooks["PreCompact"][0]["hooks"][0]["command"]


class TestPostCompactHookRegistration:
    """Verify PostCompact hook is registered in all settings templates."""

    @pytest.mark.parametrize("template_name", SETTINGS_TEMPLATES)
    def test_template_has_post_compact_hook(self, template_name: str):
        """Each settings template must have a PostCompact hook entry."""
        template_path = TEMPLATES_DIR / template_name
        assert template_path.exists(), f"Template not found: {template_path}"

        settings = json.loads(template_path.read_text())
        hooks = settings.get("hooks", {})
        assert "PostCompact" in hooks, (
            f"{template_name} missing PostCompact hook section"
        )

        post_compact = hooks["PostCompact"]
        assert len(post_compact) > 0, f"{template_name} PostCompact has no entries"

        entry = post_compact[0]
        assert entry["matcher"] == "*"
        hook_list = entry.get("hooks", [])
        assert len(hook_list) > 0
        assert "post_compact_enricher.sh" in hook_list[0]["command"]

    def test_global_settings_has_post_compact_hook(self):
        """Global settings template must have PostCompact hook."""
        path = CONFIG_DIR / "global_settings_template.json"
        assert path.exists()

        settings = json.loads(path.read_text())
        hooks = settings.get("hooks", {})
        assert "PostCompact" in hooks
        assert "post_compact_enricher.sh" in hooks["PostCompact"][0]["hooks"][0]["command"]


class TestInstallManifestRegistration:
    """Verify hook files are listed in install_manifest.json."""

    def test_pre_compact_in_manifest(self):
        """pre_compact_batch_saver.sh must be in install manifest."""
        manifest_path = CONFIG_DIR / "install_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        hook_files = manifest["components"]["hooks"]["files"]
        assert any("pre_compact_batch_saver.sh" in f for f in hook_files)

    def test_post_compact_in_manifest(self):
        """post_compact_enricher.sh must be in install manifest."""
        manifest_path = CONFIG_DIR / "install_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        hook_files = manifest["components"]["hooks"]["files"]
        assert any("post_compact_enricher.sh" in f for f in hook_files)
