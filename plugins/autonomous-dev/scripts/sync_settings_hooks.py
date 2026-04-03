#!/usr/bin/env python3
"""
Sync settings.json hook registrations during deploy.

CLI wrapper around SettingsMerger for use by deploy-all.sh. Ensures that
settings.json in global (~/.claude/) and per-repo (.claude/) locations have
all hook lifecycle events registered from the canonical templates.

Usage:
    # Global mode: merge global_settings_template.json into ~/.claude/settings.json
    python3 sync_settings_hooks.py --global

    # Per-repo mode: merge settings.default.json into <repo>/.claude/settings.json
    python3 sync_settings_hooks.py --repo /path/to/repo

    # Dry-run (no writes)
    python3 sync_settings_hooks.py --global --dry-run

    # Count-only (output hook count)
    python3 sync_settings_hooks.py --repo /path/to/repo --count-only

Output:
    JSON to stdout: {"success": bool, "hooks_added": int, "hooks_preserved": int,
                     "hooks_migrated": int, "total_lifecycle_events": int, "message": str}
    Exit code: 0 on success, 1 on error

Issue: GitHub #648
Date: 2026-04-03
Agent: implementer
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


def _find_plugin_root() -> Path:
    """Find the plugin source directory relative to this script.

    Returns:
        Path to plugins/autonomous-dev/
    """
    return Path(__file__).resolve().parent.parent


def _setup_imports() -> None:
    """Add lib directory to sys.path for SettingsMerger import."""
    lib_path = _find_plugin_root() / "lib"
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))


# Setup imports before importing SettingsMerger
_setup_imports()

try:
    from settings_merger import SettingsMerger, MergeResult
except ImportError:
    # Fallback: try package import
    try:
        from autonomous_dev.lib.settings_merger import SettingsMerger, MergeResult
    except ImportError:
        print(json.dumps({
            "success": False,
            "hooks_added": 0,
            "hooks_preserved": 0,
            "hooks_migrated": 0,
            "total_lifecycle_events": 0,
            "message": "Failed to import SettingsMerger library",
        }))
        sys.exit(1)


def _count_lifecycle_events(settings_path: Path) -> int:
    """Count the number of lifecycle events with hooks in a settings file.

    Args:
        settings_path: Path to settings.json

    Returns:
        Number of lifecycle event keys in the hooks dict
    """
    if not settings_path.exists():
        return 0
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        return len(data.get("hooks", {}))
    except (json.JSONDecodeError, OSError):
        return 0


def sync_global(*, dry_run: bool = False, count_only: bool = False) -> Dict[str, Any]:
    """Sync global settings.json hook registrations.

    Merges config/global_settings_template.json into ~/.claude/settings.json.

    Args:
        dry_run: If True, merge without writing
        count_only: If True, only return hook count

    Returns:
        Result dict with success status and hook counts
    """
    plugin_root = _find_plugin_root()
    template_path = plugin_root / "config" / "global_settings_template.json"
    user_path = Path.home() / ".claude" / "settings.json"

    if count_only:
        count = _count_lifecycle_events(user_path)
        return {
            "success": True,
            "hooks_added": 0,
            "hooks_preserved": 0,
            "hooks_migrated": 0,
            "total_lifecycle_events": count,
            "message": f"Hook count: {count} lifecycle events",
        }

    if not template_path.exists():
        return {
            "success": False,
            "hooks_added": 0,
            "hooks_preserved": 0,
            "hooks_migrated": 0,
            "total_lifecycle_events": 0,
            "message": f"Template not found: {template_path}",
        }

    # Use Path.home() as project_root for global settings
    merger = SettingsMerger(project_root=str(Path.home()))
    result = merger.merge_settings(
        template_path=template_path,
        user_path=user_path,
        write_result=not dry_run,
    )

    total_events = _count_lifecycle_events(user_path) if not dry_run else 0

    return {
        "success": result.success,
        "hooks_added": result.hooks_added,
        "hooks_preserved": result.hooks_preserved,
        "hooks_migrated": result.hooks_migrated,
        "total_lifecycle_events": total_events,
        "message": result.message,
    }


def sync_repo(
    repo_path: str, *, dry_run: bool = False, count_only: bool = False
) -> Dict[str, Any]:
    """Sync per-repo settings.json hook registrations.

    Merges templates/settings.default.json into <repo>/.claude/settings.json.

    Args:
        repo_path: Path to the repository root
        dry_run: If True, merge without writing
        count_only: If True, only return hook count

    Returns:
        Result dict with success status and hook counts
    """
    plugin_root = _find_plugin_root()
    template_path = plugin_root / "templates" / "settings.default.json"
    repo = Path(repo_path)
    user_path = repo / ".claude" / "settings.json"

    if count_only:
        count = _count_lifecycle_events(user_path)
        return {
            "success": True,
            "hooks_added": 0,
            "hooks_preserved": 0,
            "hooks_migrated": 0,
            "total_lifecycle_events": count,
            "message": f"Hook count: {count} lifecycle events",
        }

    if not template_path.exists():
        return {
            "success": False,
            "hooks_added": 0,
            "hooks_preserved": 0,
            "hooks_migrated": 0,
            "total_lifecycle_events": 0,
            "message": f"Template not found: {template_path}",
        }

    if not repo.is_dir():
        return {
            "success": False,
            "hooks_added": 0,
            "hooks_preserved": 0,
            "hooks_migrated": 0,
            "total_lifecycle_events": 0,
            "message": f"Repository path not found: {repo_path}",
        }

    merger = SettingsMerger(project_root=str(repo))
    result = merger.merge_settings(
        template_path=template_path,
        user_path=user_path,
        write_result=not dry_run,
    )

    total_events = _count_lifecycle_events(user_path) if not dry_run else 0

    return {
        "success": result.success,
        "hooks_added": result.hooks_added,
        "hooks_preserved": result.hooks_preserved,
        "hooks_migrated": result.hooks_migrated,
        "total_lifecycle_events": total_events,
        "message": result.message,
    }


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Sync settings.json hook registrations during deploy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--global",
        dest="global_mode",
        action="store_true",
        help="Sync global ~/.claude/settings.json hooks",
    )
    mode_group.add_argument(
        "--repo",
        type=str,
        help="Sync per-repo <path>/.claude/settings.json hooks",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Merge without writing (preview changes)",
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Output registered hook count only",
    )

    args = parser.parse_args()

    try:
        if args.global_mode:
            result = sync_global(dry_run=args.dry_run, count_only=args.count_only)
        else:
            result = sync_repo(args.repo, dry_run=args.dry_run, count_only=args.count_only)

        print(json.dumps(result, indent=2))
        sys.exit(0 if result["success"] else 1)

    except Exception as e:
        error_result = {
            "success": False,
            "hooks_added": 0,
            "hooks_preserved": 0,
            "hooks_migrated": 0,
            "total_lifecycle_events": 0,
            "message": f"Unexpected error: {e}",
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
