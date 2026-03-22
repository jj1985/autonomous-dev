#!/usr/bin/env python3
"""Generate hook config from .hook.json sidecar metadata files.

Reads .hook.json sidecar files from the hooks directory and generates:
1. install_manifest.json ``components.hooks.files`` array
2. global_settings_template.json ``hooks`` object

Usage:
    python scripts/generate_hook_config.py --check     # Report drift without modifying
    python scripts/generate_hook_config.py --write      # Update config files
    python scripts/generate_hook_config.py --check -v   # Verbose drift report

Exit codes:
    0 - Success (no drift in check mode, or write succeeded)
    1 - Drift detected (check mode) or validation errors
    2 - CLI/usage errors
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# Auto-detect project root from script location
PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = PROJECT_ROOT / "plugins/autonomous-dev/hooks"
MANIFEST_PATH = PROJECT_ROOT / "plugins/autonomous-dev/config/install_manifest.json"
SETTINGS_PATH = PROJECT_ROOT / "plugins/autonomous-dev/config/global_settings_template.json"
SCHEMA_PATH = PROJECT_ROOT / "plugins/autonomous-dev/config/hook-metadata.schema.json"

# Extension mapping from interpreter to file extension
INTERPRETER_EXTENSIONS = {
    "python3": ".py",
    "bash": ".sh",
}

# Optional jsonschema support
try:
    from jsonschema import Draft202012Validator

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


def discover_sidecars(hooks_dir: Path) -> list[Path]:
    """Find all *.hook.json in hooks_dir (excluding archived/), sorted by name.

    Args:
        hooks_dir: Directory to search for sidecar files.

    Returns:
        Sorted list of Path objects for each discovered .hook.json file.

    Raises:
        FileNotFoundError: If hooks_dir does not exist.
    """
    if not hooks_dir.is_dir():
        raise FileNotFoundError(
            f"Hooks directory not found: {hooks_dir}\n"
            f"Expected: directory containing .hook.json sidecar files\n"
            f"See: docs/ARCHITECTURE-OVERVIEW.md"
        )

    sidecars = []
    for path in hooks_dir.glob("*.hook.json"):
        # Exclude anything under archived/
        if "archived" not in path.parts:
            sidecars.append(path)

    return sorted(sidecars, key=lambda p: p.name)


def load_and_validate_sidecar(path: Path, schema: dict | None = None) -> dict:
    """Load sidecar JSON and validate against schema.

    Args:
        path: Path to the .hook.json sidecar file.
        schema: JSON Schema dict for validation. If None, skips validation.

    Returns:
        Parsed sidecar data as a dict.

    Raises:
        ValueError: If JSON is invalid or schema validation fails.
    """
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON in sidecar: {path}\n"
            f"Parse error: {e}\n"
            f"Expected: valid JSON matching hook-metadata.schema.json"
        ) from e

    if not isinstance(data, dict):
        raise ValueError(
            f"Sidecar must be a JSON object: {path}\n"
            f"Got: {type(data).__name__}\n"
            f"Expected: object with 'name', 'type', 'interpreter' keys"
        )

    # Validate required fields even without jsonschema
    for field in ("name", "type", "interpreter"):
        if field not in data:
            raise ValueError(
                f"Missing required field '{field}' in sidecar: {path}\n"
                f"Required fields: name, type, interpreter\n"
                f"See: plugins/autonomous-dev/config/hook-metadata.schema.json"
            )

    # Schema validation with jsonschema if available
    if schema is not None and HAS_JSONSCHEMA:
        validator = Draft202012Validator(schema)
        errors = list(validator.iter_errors(data))
        if errors:
            error_messages = "; ".join(e.message for e in errors)
            raise ValueError(
                f"Schema validation failed for sidecar: {path}\n"
                f"Errors: {error_messages}\n"
                f"See: plugins/autonomous-dev/config/hook-metadata.schema.json"
            )
    elif schema is not None and not HAS_JSONSCHEMA:
        print(
            f"WARNING: jsonschema not installed, skipping schema validation for {path.name}",
            file=sys.stderr,
        )

    return data


def detect_orphans(hooks_dir: Path, sidecars: list[dict]) -> dict[str, list[str]]:
    """Find hooks without sidecars and sidecars without hooks.

    Args:
        hooks_dir: Directory containing hook scripts and sidecars.
        sidecars: List of loaded sidecar data dicts.

    Returns:
        Dict with 'hooks_without_sidecars' and 'sidecars_without_hooks' lists.
    """
    # Collect sidecar names
    sidecar_names = set()
    for s in sidecars:
        sidecar_names.add(s["name"])

    # Find hook scripts (excluding archived, __init__.py, __pycache__, and .hook.json files)
    hook_scripts = set()
    for path in hooks_dir.iterdir():
        if path.is_file() and not path.name.startswith("__") and "archived" not in path.parts:
            if path.suffix in (".py", ".sh") and not path.name.endswith(".hook.json"):
                hook_scripts.add(path.stem)

    hooks_without_sidecars = sorted(hook_scripts - sidecar_names)
    sidecars_without_hooks = sorted(sidecar_names - hook_scripts)

    return {
        "hooks_without_sidecars": hooks_without_sidecars,
        "sidecars_without_hooks": sidecars_without_hooks,
    }


def generate_manifest_hooks(sidecars: list[dict]) -> list[str]:
    """Generate sorted list of file paths for manifest.

    Includes BOTH hook scripts AND .hook.json files.
    Maps interpreter to extension: python3 -> .py, bash -> .sh.

    Args:
        sidecars: List of loaded sidecar data dicts.

    Returns:
        Sorted list of file paths in 'plugins/autonomous-dev/hooks/{name}.{ext}' format.
    """
    files = []
    for sidecar in sidecars:
        name = sidecar["name"]
        interpreter = sidecar["interpreter"]
        ext = INTERPRETER_EXTENSIONS.get(interpreter, ".py")

        # Add the sidecar file itself
        files.append(f"plugins/autonomous-dev/hooks/{name}.hook.json")
        # Add the hook script
        files.append(f"plugins/autonomous-dev/hooks/{name}{ext}")

    return sorted(files)


def build_command_string(sidecar: dict) -> str:
    """Build command string from sidecar metadata.

    Sorted env vars + interpreter + ~/.claude/hooks/{name}.{ext}

    Args:
        sidecar: Loaded sidecar data dict.

    Returns:
        Command string, e.g.:
        'MCP_AUTO_APPROVE=true SANDBOX_ENABLED=false python3 ~/.claude/hooks/unified_pre_tool.py'

    Examples:
        No env: 'python3 ~/.claude/hooks/name.py'
        Bash: 'bash ~/.claude/hooks/name.sh'
    """
    name = sidecar["name"]
    interpreter = sidecar["interpreter"]
    ext = INTERPRETER_EXTENSIONS.get(interpreter, ".py")
    script_path = f"~/.claude/hooks/{name}{ext}"

    env_vars = sidecar.get("env", {})
    if env_vars:
        # Sort env vars alphabetically
        sorted_env = " ".join(
            f"{key}={value}" for key, value in sorted(env_vars.items())
        )
        return f"{sorted_env} {interpreter} {script_path}"

    return f"{interpreter} {script_path}"


def generate_settings_hooks(sidecars: list[dict]) -> dict[str, list[dict]]:
    """Generate settings hooks object from LIFECYCLE sidecars only.

    Utility hooks are excluded. Inactive hooks are excluded.
    Groups by event. Builds command strings. Sorts events alphabetically.
    Within each event, specific matchers come before wildcard "*".

    Args:
        sidecars: List of loaded sidecar data dicts.

    Returns:
        Settings hooks dict matching global_settings_template.json format.
    """
    # Filter to active lifecycle hooks only
    lifecycle_sidecars = [
        s for s in sidecars
        if s.get("type") == "lifecycle" and s.get("active", True) is True
    ]

    # Group registrations by event
    events: dict[str, list[dict]] = {}
    for sidecar in lifecycle_sidecars:
        command = build_command_string(sidecar)
        for reg in sidecar.get("registrations", []):
            event = reg["event"]
            matcher = reg.get("matcher", "*")
            timeout = reg.get("timeout", 5)

            if event not in events:
                events[event] = []

            events[event].append({
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": timeout,
                    }
                ],
            })

    # Sort: events alphabetically, within each event specific matchers before wildcard
    result: dict[str, list[dict]] = {}
    for event in sorted(events.keys()):
        entries = events[event]
        # Specific matchers (non-"*") first, then wildcards
        specific = [e for e in entries if e["matcher"] != "*"]
        wildcards = [e for e in entries if e["matcher"] == "*"]
        # Sort within each group by matcher name for determinism
        specific.sort(key=lambda e: e["matcher"])
        wildcards.sort(key=lambda e: e["hooks"][0]["command"])
        result[event] = specific + wildcards

    return result


def atomic_write_json(file_path: Path, data: Any) -> None:
    """Write JSON data to file atomically.

    Uses tempfile + os.replace for atomic write to prevent corruption.

    Args:
        file_path: Target file path.
        data: Data to serialize as JSON.

    Raises:
        OSError: If file cannot be written.
    """
    temp_fd, temp_path = tempfile.mkstemp(
        dir=str(file_path.parent), suffix=".json"
    )
    try:
        with os.fdopen(temp_fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")  # trailing newline
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, str(file_path))
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def load_schema(schema_path: Path) -> dict | None:
    """Load JSON Schema from file if it exists.

    Args:
        schema_path: Path to the schema file.

    Returns:
        Parsed schema dict, or None if file does not exist.
    """
    if schema_path.is_file():
        with open(schema_path, encoding="utf-8") as f:
            return json.load(f)
    return None


def check_drift(
    *,
    hooks_dir: Path,
    manifest_path: Path,
    settings_path: Path,
    schema_path: Path,
    verbose: bool = False,
) -> int:
    """Check for drift between sidecars and config files.

    Args:
        hooks_dir: Directory containing hook scripts and sidecars.
        manifest_path: Path to install_manifest.json.
        settings_path: Path to global_settings_template.json.
        schema_path: Path to hook-metadata.schema.json.
        verbose: Print detailed comparison info.

    Returns:
        0 if no drift, 1 if drift detected.
    """
    schema = load_schema(schema_path)

    try:
        sidecar_paths = discover_sidecars(hooks_dir)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    sidecars = []
    errors = []
    for path in sidecar_paths:
        try:
            data = load_and_validate_sidecar(path, schema)
            sidecars.append(data)
        except ValueError as e:
            errors.append(str(e))

    if errors:
        print("Sidecar validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    # Check orphans
    orphans = detect_orphans(hooks_dir, sidecars)
    has_orphans = False
    if orphans["hooks_without_sidecars"]:
        has_orphans = True
        if verbose:
            print(f"Hooks without sidecars: {orphans['hooks_without_sidecars']}")
    if orphans["sidecars_without_hooks"]:
        has_orphans = True
        if verbose:
            print(f"Sidecars without hooks: {orphans['sidecars_without_hooks']}")

    # Generate expected config
    expected_manifest_hooks = generate_manifest_hooks(sidecars)
    expected_settings_hooks = generate_settings_hooks(sidecars)

    drift_found = False

    # Compare manifest
    if manifest_path.is_file():
        with open(manifest_path, encoding="utf-8") as f:
            current_manifest = json.load(f)
        current_hooks = current_manifest.get("components", {}).get("hooks", {}).get("files", [])
        if current_hooks != expected_manifest_hooks:
            drift_found = True
            if verbose:
                current_set = set(current_hooks)
                expected_set = set(expected_manifest_hooks)
                added = sorted(expected_set - current_set)
                removed = sorted(current_set - expected_set)
                if added:
                    print(f"Manifest: would add {added}")
                if removed:
                    print(f"Manifest: would remove {removed}")
            else:
                print("Manifest hooks.files: DRIFT DETECTED")
    else:
        drift_found = True
        print(f"Manifest file not found: {manifest_path}")

    # Compare settings
    if settings_path.is_file():
        with open(settings_path, encoding="utf-8") as f:
            current_settings = json.load(f)
        current_hooks_section = current_settings.get("hooks", {})
        if current_hooks_section != expected_settings_hooks:
            drift_found = True
            if verbose:
                current_events = set(current_hooks_section.keys())
                expected_events = set(expected_settings_hooks.keys())
                added_events = sorted(expected_events - current_events)
                removed_events = sorted(current_events - expected_events)
                if added_events:
                    print(f"Settings: would add events {added_events}")
                if removed_events:
                    print(f"Settings: would remove events {removed_events}")
                # Show per-event drift
                for event in sorted(expected_events & current_events):
                    if current_hooks_section[event] != expected_settings_hooks[event]:
                        print(f"Settings: event '{event}' has drift")
            else:
                print("Settings hooks: DRIFT DETECTED")
    else:
        drift_found = True
        print(f"Settings file not found: {settings_path}")

    if not drift_found and not has_orphans:
        print("No drift detected.")
        return 0

    if has_orphans and verbose:
        print("Orphan hooks/sidecars detected (not blocking).")

    if drift_found:
        print("Drift detected. Run with --write to update.")
        return 1

    return 0


def write_config(
    *,
    hooks_dir: Path,
    manifest_path: Path,
    settings_path: Path,
    schema_path: Path,
    verbose: bool = False,
) -> int:
    """Update config files from sidecar metadata.

    Only replaces the hooks sections. Preserves all other content.

    Args:
        hooks_dir: Directory containing hook scripts and sidecars.
        manifest_path: Path to install_manifest.json.
        settings_path: Path to global_settings_template.json.
        schema_path: Path to hook-metadata.schema.json.
        verbose: Print detailed update info.

    Returns:
        0 on success, 1 on validation errors.
    """
    schema = load_schema(schema_path)
    sidecar_paths = discover_sidecars(hooks_dir)

    sidecars = []
    errors = []
    for path in sidecar_paths:
        try:
            data = load_and_validate_sidecar(path, schema)
            sidecars.append(data)
        except ValueError as e:
            errors.append(str(e))

    if errors:
        print("Sidecar validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    # Generate configs
    manifest_hooks = generate_manifest_hooks(sidecars)
    settings_hooks = generate_settings_hooks(sidecars)

    # Update manifest - preserve everything except components.hooks.files
    if manifest_path.is_file():
        with open(manifest_path, encoding="utf-8") as f:
            manifest_data = json.load(f)
    else:
        manifest_data = {"components": {"hooks": {"files": []}}}

    if "components" not in manifest_data:
        manifest_data["components"] = {}
    if "hooks" not in manifest_data["components"]:
        manifest_data["components"]["hooks"] = {}

    manifest_data["components"]["hooks"]["files"] = manifest_hooks
    atomic_write_json(manifest_path, manifest_data)
    if verbose:
        print(f"Updated manifest: {manifest_path} ({len(manifest_hooks)} hook files)")

    # Update settings - preserve everything except hooks
    if settings_path.is_file():
        with open(settings_path, encoding="utf-8") as f:
            settings_data = json.load(f)
    else:
        settings_data = {}

    settings_data["hooks"] = settings_hooks
    atomic_write_json(settings_path, settings_data)
    if verbose:
        print(f"Updated settings: {settings_path} ({len(settings_hooks)} events)")

    print("Config files updated successfully.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace object.
    """
    parser = argparse.ArgumentParser(
        description="Generate hook config from .hook.json sidecars"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check",
        action="store_true",
        help="Report drift without modifying",
    )
    group.add_argument(
        "--write",
        action="store_true",
        help="Update config files",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed output",
    )
    parser.add_argument(
        "--hooks-dir",
        type=Path,
        default=None,
        help="Path to hooks directory (default: auto-detect)",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=None,
        help="Path to install_manifest.json (default: auto-detect)",
    )
    parser.add_argument(
        "--settings-path",
        type=Path,
        default=None,
        help="Path to global_settings_template.json (default: auto-detect)",
    )
    parser.add_argument(
        "--schema-path",
        type=Path,
        default=None,
        help="Path to hook-metadata.schema.json (default: auto-detect)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code: 0=success, 1=drift/errors, 2=CLI errors.
    """
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return 2 if e.code != 0 else 0

    hooks_dir = args.hooks_dir or HOOKS_DIR
    manifest_path = args.manifest_path or MANIFEST_PATH
    settings_path = args.settings_path or SETTINGS_PATH
    schema_path = args.schema_path or SCHEMA_PATH

    if args.check:
        return check_drift(
            hooks_dir=hooks_dir,
            manifest_path=manifest_path,
            settings_path=settings_path,
            schema_path=schema_path,
            verbose=args.verbose,
        )
    elif args.write:
        return write_config(
            hooks_dir=hooks_dir,
            manifest_path=manifest_path,
            settings_path=settings_path,
            schema_path=schema_path,
            verbose=args.verbose,
        )

    return 2


if __name__ == "__main__":
    sys.exit(main())
