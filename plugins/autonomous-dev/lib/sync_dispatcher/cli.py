#!/usr/bin/env python3
"""
Sync Dispatcher CLI - Command-line interface and convenience functions

This module contains the CLI entry point, convenience functions, and AgentInvoker.

Functions:
- dispatch_sync: Convenience function for simple sync operations
- sync_marketplace: Convenience function for marketplace sync with enhancements
- main: CLI entry point with argument parsing

Classes:
- AgentInvoker: Mock agent invoker for testing

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Import dependencies
try:
    from plugins.autonomous_dev.lib.sync_mode_detector import SyncMode
except ImportError:
    from sync_mode_detector import SyncMode  # type: ignore

# Import from package modules
from .models import SyncResult


def dispatch_sync(
    project_path: str, mode: SyncMode, create_backup: bool = True
) -> SyncResult:
    """Convenience function to dispatch sync operation.

    Args:
        project_path: Path to project root
        mode: Sync mode to execute
        create_backup: Whether to create backup before sync

    Returns:
        SyncResult with operation outcome

    Example:
        >>> result = dispatch_sync("/path/to/project", SyncMode.ENVIRONMENT)
        >>> if result.success:
        ...     print(f"Success: {result.message}")
    """
    # Import SyncDispatcher from dispatcher module
    from .dispatcher import SyncDispatcher

    dispatcher = SyncDispatcher(project_path)
    return dispatcher.dispatch(mode, create_backup=create_backup)


def sync_marketplace(
    project_root: str,
    marketplace_plugins_file: Path,
    cleanup_orphans: bool = False,
    dry_run: bool = False,
) -> SyncResult:
    """Convenience function for marketplace sync with enhancements.

    This is the high-level API for marketplace sync that includes:
    - Version detection (upgrade/downgrade detection)
    - Orphan cleanup (optional, with dry-run support)
    - Rich result object with version and cleanup details

    Args:
        project_root: Path to project root directory
        marketplace_plugins_file: Path to installed_plugins.json
        cleanup_orphans: Whether to cleanup orphaned files (default: False)
        dry_run: Whether to dry-run orphan cleanup (default: False)

    Returns:
        SyncResult with version_comparison and orphan_cleanup attributes

    Example:
        >>> from pathlib import Path
        >>> result = sync_marketplace(
        ...     project_root="/path/to/project",
        ...     marketplace_plugins_file=Path("~/.claude/plugins/installed_plugins.json"),
        ...     cleanup_orphans=True,
        ...     dry_run=True
        ... )
        >>> print(result.summary)
        >>> if result.version_comparison:
        ...     print(f"Version: {result.version_comparison.status}")
    """
    # Import SyncDispatcher from dispatcher module
    from .dispatcher import SyncDispatcher

    dispatcher = SyncDispatcher(project_root)
    return dispatcher.sync_marketplace(
        marketplace_plugins_file=marketplace_plugins_file,
        cleanup_orphans=cleanup_orphans,
        dry_run=dry_run,
    )


def _run_hook_verify() -> int:
    """Run hook sidecar consistency check via generate_hook_config.py --check.

    Locates the generator script relative to the project root and executes it
    in --check mode. Reports consistency status without deploying.

    Returns:
        0 if hook sidecars are consistent, 1 if drift detected or script not found.
    """
    import subprocess

    # Find the project root by looking for scripts/generate_hook_config.py
    project_root = Path(os.getcwd())
    generator = project_root / "scripts" / "generate_hook_config.py"

    if not generator.is_file():
        print(
            f"Hook config generator not found: {generator}\n"
            f"Expected: scripts/generate_hook_config.py in project root\n"
            f"See: docs/HOOK-SIDECAR-SCHEMA.md",
            file=sys.stderr,
        )
        return 1

    hooks_dir = project_root / "plugins" / "autonomous-dev" / "hooks"
    manifest_path = project_root / "plugins" / "autonomous-dev" / "config" / "install_manifest.json"
    settings_path = (
        project_root / "plugins" / "autonomous-dev" / "config" / "global_settings_template.json"
    )
    schema_path = (
        project_root / "plugins" / "autonomous-dev" / "config" / "hook-metadata.schema.json"
    )

    result = subprocess.run(
        [
            sys.executable, str(generator), "--check",
            "--hooks-dir", str(hooks_dir),
            "--manifest-path", str(manifest_path),
            "--settings-path", str(settings_path),
            "--schema-path", str(schema_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode == 0:
        print("Hook sidecar consistency: OK")
    else:
        print("Hook sidecar consistency: DRIFT DETECTED")
        print("Fix: python3 scripts/generate_hook_config.py --write")

    return result.returncode


def main() -> int:
    """CLI wrapper for sync_dispatcher.py.

    Parses command-line arguments and executes the appropriate sync mode.

    Arguments:
        --github: Fetch latest files from GitHub (default)
        --env: Sync environment (delegates to sync-validator agent)
        --marketplace: Copy files from installed plugin
        --plugin-dev: Sync plugin development files
        --all: Execute all sync modes in sequence

    Returns:
        Exit code: 0 for success, 1 for failure, 2 for invalid arguments

    Examples:
        # Default GitHub mode
        $ python3 sync_dispatcher.py

        # Explicit mode selection
        $ python3 sync_dispatcher.py --github
        $ python3 sync_dispatcher.py --env
        $ python3 sync_dispatcher.py --marketplace
        $ python3 sync_dispatcher.py --plugin-dev
        $ python3 sync_dispatcher.py --all
    """
    # Import SyncDispatcher from dispatcher module
    from .dispatcher import SyncDispatcher

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Sync dispatcher for autonomous-dev plugin",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default (GitHub mode)
  python3 sync_dispatcher.py

  # Explicit mode selection
  python3 sync_dispatcher.py --github
  python3 sync_dispatcher.py --env
  python3 sync_dispatcher.py --marketplace
  python3 sync_dispatcher.py --plugin-dev
  python3 sync_dispatcher.py --all

Exit Codes:
  0 - Success
  1 - Failure
  2 - Invalid arguments
"""
    )

    # Create mutually exclusive group for sync modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--github',
        action='store_true',
        help='Fetch latest files from GitHub (default)'
    )
    mode_group.add_argument(
        '--env',
        action='store_true',
        help='Sync environment via sync-validator agent'
    )
    mode_group.add_argument(
        '--marketplace',
        action='store_true',
        help='Copy files from installed plugin'
    )
    mode_group.add_argument(
        '--plugin-dev',
        action='store_true',
        help='Sync plugin development files'
    )
    mode_group.add_argument(
        '--all',
        action='store_true',
        help='Execute all sync modes in sequence'
    )
    mode_group.add_argument(
        '--uninstall',
        action='store_true',
        help='Uninstall plugin (requires --force)'
    )

    # Additional arguments (not mutually exclusive with modes)
    parser.add_argument(
        '--force',
        action='store_true',
        help='Confirm deletion for uninstall mode'
    )
    parser.add_argument(
        '--local-only',
        action='store_true',
        help='Skip global ~/.claude/ files (uninstall mode only)'
    )
    parser.add_argument(
        '--no-generate',
        action='store_true',
        help='Skip hook config generator during sync'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Run hook sidecar consistency check without syncing'
    )

    def _run_hook_verify() -> int:
        """Run hook sidecar consistency check without syncing."""
        import subprocess as _sp
        project_root = Path(os.getcwd())
        script = project_root / "scripts" / "generate_hook_config.py"
        if not script.exists():
            script = project_root / ".claude" / "scripts" / "generate_hook_config.py"
        if not script.exists():
            print("Error: generate_hook_config.py not found", file=sys.stderr)
            return 1
        result = _sp.run(
            [sys.executable, str(script), "--check",
             "--hooks-dir", str(project_root / "plugins/autonomous-dev/hooks"),
             "--manifest-path", str(project_root / "plugins/autonomous-dev/config/install_manifest.json"),
             "--settings-path", str(project_root / "plugins/autonomous-dev/config/global_settings_template.json"),
             "--schema-path", str(project_root / "plugins/autonomous-dev/config/hook-metadata.schema.json")],
            timeout=30,
        )
        return result.returncode

    try:
        args = parser.parse_args()

        # Handle --verify: run hook sidecar consistency check and exit
        if getattr(args, 'verify', False):
            return _run_hook_verify()

        # Determine sync mode (default to GITHUB)
        if args.uninstall:
            mode = SyncMode.UNINSTALL
        elif args.env:
            mode = SyncMode.ENVIRONMENT
        elif args.marketplace:
            mode = SyncMode.MARKETPLACE
        elif args.plugin_dev:
            mode = SyncMode.PLUGIN_DEV
        elif args.all:
            mode = SyncMode.ALL
        else:
            # Default to GITHUB (when no flags or --github explicitly)
            mode = SyncMode.GITHUB

        # Get project root from current working directory
        project_root = os.getcwd()

        # Execute sync
        try:
            dispatcher = SyncDispatcher(
                project_root=project_root,
                no_generate=getattr(args, 'no_generate', False),
            )

            # Handle uninstall mode with additional arguments
            if mode == SyncMode.UNINSTALL:
                result = dispatcher.sync(
                    mode=mode,
                    force=getattr(args, 'force', False),
                    local_only=getattr(args, 'local_only', False)
                )
            else:
                result = dispatcher.dispatch(mode)

            # Output result
            if result.success:
                print(result.message)
                return 0
            else:
                # Print error to stderr
                error_msg = result.error if result.error else result.message
                print(f"Error: {error_msg}", file=sys.stderr)
                return 1

        except Exception as e:
            # Handle unexpected errors
            print(f"Error: {str(e)}", file=sys.stderr)
            return 1

    except KeyboardInterrupt:
        print("\nSync cancelled by user.", file=sys.stderr)
        return 1
    except SystemExit:
        # argparse raises SystemExit for --help or invalid args
        # Re-raise to propagate exit code (0 for --help, 2 for errors)
        raise


if __name__ == "__main__":
    sys.exit(main())
