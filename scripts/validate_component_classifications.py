#!/usr/bin/env python3
"""Validate component classifications registry for completeness and correctness.

Checks that:
- All active hooks have classification entries
- No orphan entries exist for removed components
- Business rules are enforced (model-limitation has removal_criteria, etc.)
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PLUGIN_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev"
REGISTRY_PATH = PLUGIN_DIR / "config" / "component_classifications.json"
HOOKS_DIR = PLUGIN_DIR / "hooks"


def load_registry(path: Path) -> dict:
    """Load and basic-validate the JSON registry.

    Args:
        path: Path to the component_classifications.json file.

    Returns:
        Parsed registry dict.

    Raises:
        SystemExit: If file is missing or invalid JSON.
    """
    if not path.exists():
        print(f"ERROR: Registry file not found: {path}")
        sys.exit(1)

    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in registry: {e}")
        sys.exit(1)

    required_keys = {"version", "last_reviewed", "classifications"}
    missing = required_keys - set(data.keys())
    if missing:
        print(f"ERROR: Registry missing top-level keys: {missing}")
        sys.exit(1)

    required_sections = {"hooks", "hard_gates", "forbidden_lists"}
    missing_sections = required_sections - set(data["classifications"].keys())
    if missing_sections:
        print(f"ERROR: Registry missing classification sections: {missing_sections}")
        sys.exit(1)

    return data


def discover_active_hooks(plugin_dir: Path) -> set:
    """Find all active hook .py files (not archived, not __init__, not __pycache__).

    Args:
        plugin_dir: Path to the plugin directory.

    Returns:
        Set of hook names (without .py extension).
    """
    hooks_dir = plugin_dir / "hooks"
    if not hooks_dir.exists():
        return set()

    hooks = set()
    for f in hooks_dir.iterdir():
        if (
            f.is_file()
            and f.suffix == ".py"
            and f.name != "__init__.py"
            and "__pycache__" not in str(f)
        ):
            hooks.add(f.stem)
    return hooks


def discover_hard_gates(plugin_dir: Path) -> set:
    """Discover files containing HARD GATE references.

    Args:
        plugin_dir: Path to the plugin directory.

    Returns:
        Set of file stems that contain HARD GATE references.
    """
    files_with_gates = set()

    implement_path = plugin_dir / "commands" / "implement.md"
    if implement_path.exists() and "HARD GATE" in implement_path.read_text():
        files_with_gates.add("implement.md")

    agents_dir = plugin_dir / "agents"
    if agents_dir.exists():
        for f in agents_dir.iterdir():
            if f.suffix == ".md" and f.is_file():
                if "HARD GATE" in f.read_text():
                    files_with_gates.add(f.name)

    return files_with_gates


def validate_coverage(registry: dict, hooks: set) -> list:
    """Return list of active hooks missing from the registry.

    Args:
        registry: Parsed registry dict.
        hooks: Set of discovered active hook names.

    Returns:
        List of error strings for missing entries.
    """
    errors = []
    registered_hooks = set(registry["classifications"]["hooks"].keys())
    missing = hooks - registered_hooks
    if missing:
        for hook in sorted(missing):
            errors.append(f"Active hook '{hook}' has no classification entry")
    return errors


def validate_no_orphans(registry: dict, hooks: set) -> list:
    """Return list of registry hook entries that no longer exist on disk.

    Args:
        registry: Parsed registry dict.
        hooks: Set of discovered active hook names.

    Returns:
        List of error strings for orphan entries.
    """
    errors = []
    registered_hooks = set(registry["classifications"]["hooks"].keys())
    orphans = registered_hooks - hooks
    if orphans:
        for hook in sorted(orphans):
            entry = registry["classifications"]["hooks"][hook]
            if entry.get("review_status") != "removed":
                errors.append(
                    f"Hook entry '{hook}' exists in registry but no matching "
                    f"file found in hooks directory"
                )
    return errors


def validate_business_rules(registry: dict) -> list:
    """Validate classification business rules.

    Rules:
    - model-limitation entries MUST have non-null removal_criteria
    - process-requirement entries MUST have null removal_criteria
    - All entries must have non-empty rationale
    - classification must be one of the two valid values
    - review_status must be a valid enum value

    Args:
        registry: Parsed registry dict.

    Returns:
        List of error strings for business rule violations.
    """
    errors = []
    valid_classifications = {"model-limitation", "process-requirement"}
    valid_statuses = {"initial", "reviewed", "candidate-for-removal", "removed"}

    for section_name in ("hooks", "hard_gates", "forbidden_lists"):
        section = registry["classifications"].get(section_name, {})
        for entry_id, entry in section.items():
            prefix = f"{section_name}.{entry_id}"

            classification = entry.get("classification")
            if classification not in valid_classifications:
                errors.append(
                    f"{prefix}: invalid classification '{classification}' "
                    f"(must be one of {valid_classifications})"
                )
                continue

            removal_criteria = entry.get("removal_criteria")
            if classification == "model-limitation" and removal_criteria is None:
                errors.append(
                    f"{prefix}: model-limitation entries MUST have "
                    f"non-null removal_criteria"
                )
            if classification == "process-requirement" and removal_criteria is not None:
                errors.append(
                    f"{prefix}: process-requirement entries MUST have "
                    f"null removal_criteria"
                )

            rationale = entry.get("rationale", "")
            if not rationale or not rationale.strip():
                errors.append(f"{prefix}: rationale must be non-empty")

            status = entry.get("review_status")
            if status not in valid_statuses:
                errors.append(
                    f"{prefix}: invalid review_status '{status}' "
                    f"(must be one of {valid_statuses})"
                )

    return errors


def main() -> int:
    """Run all validations and print results.

    Returns:
        0 if all validations pass, 1 if any fail.
    """
    print("Validating component classifications registry...")
    print(f"  Registry: {REGISTRY_PATH}")
    print()

    registry = load_registry(REGISTRY_PATH)
    hooks = discover_active_hooks(PLUGIN_DIR)

    all_errors = []

    coverage_errors = validate_coverage(registry, hooks)
    if coverage_errors:
        all_errors.extend(coverage_errors)
        for e in coverage_errors:
            print(f"  MISSING: {e}")
    else:
        print(f"  OK: All {len(hooks)} active hooks have classification entries")

    orphan_errors = validate_no_orphans(registry, hooks)
    if orphan_errors:
        all_errors.extend(orphan_errors)
        for e in orphan_errors:
            print(f"  ORPHAN: {e}")
    else:
        print("  OK: No orphan hook entries found")

    rule_errors = validate_business_rules(registry)
    if rule_errors:
        all_errors.extend(rule_errors)
        for e in rule_errors:
            print(f"  RULE: {e}")
    else:
        print("  OK: All business rules satisfied")

    classifications = registry["classifications"]
    hook_count = len(classifications["hooks"])
    gate_count = len(classifications["hard_gates"])
    forbidden_count = len(classifications["forbidden_lists"])
    total = hook_count + gate_count + forbidden_count

    model_lim = sum(
        1
        for section in classifications.values()
        for entry in section.values()
        if entry.get("classification") == "model-limitation"
    )
    process_req = total - model_lim

    print()
    ver = registry["version"]
    reviewed = registry["last_reviewed"]
    print(f"  Registry v{ver} (last reviewed: {reviewed})")
    print(f"  Total entries: {total} ({hook_count} hooks, {gate_count} hard gates, {forbidden_count} forbidden lists)")
    print(f"  Model-limitation: {model_lim}, Process-requirement: {process_req}")

    if all_errors:
        print(f"\nFAILED: {len(all_errors)} error(s) found")
        return 1
    else:
        print("\nAll validations passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
