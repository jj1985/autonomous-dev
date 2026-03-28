"""Unit tests for component_classifications.json registry.

Validates:
- Registry structure and JSON validity
- All active hooks have classification entries
- Business rules (model-limitation has removal_criteria, etc.)
- No orphan entries
- Schema compliance
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PLUGIN_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev"
REGISTRY_PATH = PLUGIN_DIR / "config" / "component_classifications.json"
HOOKS_DIR = PLUGIN_DIR / "hooks"
VALIDATION_SCRIPT = PROJECT_ROOT / "scripts" / "validate_component_classifications.py"


@pytest.fixture
def registry():
    """Load the component classifications registry."""
    assert REGISTRY_PATH.exists(), f"Registry not found: {REGISTRY_PATH}"
    with open(REGISTRY_PATH) as f:
        return json.load(f)


@pytest.fixture
def active_hooks():
    """Discover active hook files on disk."""
    hooks = set()
    for f in HOOKS_DIR.iterdir():
        if (
            f.is_file()
            and f.suffix == ".py"
            and f.name != "__init__.py"
            and "__pycache__" not in str(f)
        ):
            hooks.add(f.stem)
    return hooks


class TestRegistryStructure:
    """Tests for registry JSON structure and validity."""

    def test_registry_loads_valid_json(self):
        """Registry file must be valid JSON."""
        content = REGISTRY_PATH.read_text()
        data = json.loads(content)
        assert isinstance(data, dict)

    def test_registry_has_version(self, registry):
        """Registry must have a version field."""
        assert "version" in registry
        assert isinstance(registry["version"], str)

    def test_version_is_semver(self, registry):
        """Version must follow semver format (X.Y.Z)."""
        version = registry["version"]
        pattern = r"^\d+\.\d+\.\d+$"
        assert re.match(pattern, version), (
            "Version '{}' is not valid semver (expected X.Y.Z)".format(version)
        )

    def test_registry_has_last_reviewed(self, registry):
        """Registry must have a last_reviewed date."""
        assert "last_reviewed" in registry
        pattern = r"^\d{4}-\d{2}-\d{2}$"
        assert re.match(pattern, registry["last_reviewed"])

    def test_registry_has_required_sections(self, registry):
        """Registry must have hooks, hard_gates, and forbidden_lists sections."""
        classifications = registry.get("classifications", {})
        assert "hooks" in classifications, "Missing 'hooks' section"
        assert "hard_gates" in classifications, "Missing 'hard_gates' section"
        assert "forbidden_lists" in classifications, "Missing 'forbidden_lists' section"


class TestHookCoverage:
    """Tests for hook classification coverage."""

    def test_all_active_hooks_have_entries(self, registry, active_hooks):
        """Every active hook .py file must have a classification entry."""
        registered = set(registry["classifications"]["hooks"].keys())
        missing = active_hooks - registered
        assert not missing, (
            "Active hooks missing classification entries: {}".format(sorted(missing))
        )

    def test_no_orphan_hook_entries(self, registry, active_hooks):
        """No registry hook entries should reference non-existent hook files."""
        registered = set(registry["classifications"]["hooks"].keys())
        orphans = set()
        for hook in registered:
            entry = registry["classifications"]["hooks"][hook]
            if entry.get("review_status") != "removed" and hook not in active_hooks:
                orphans.add(hook)
        assert not orphans, (
            "Orphan hook entries (no matching file): {}".format(sorted(orphans))
        )


class TestHardGateCoverage:
    """Tests for hard gate classification coverage."""

    def test_all_hard_gates_have_entries(self, registry):
        """Hard gates section must not be empty."""
        gates = registry["classifications"]["hard_gates"]
        assert len(gates) > 0, "No hard gate entries found"

    def test_implement_hard_gates_present(self, registry):
        """Key implement.md hard gates must have entries."""
        gates = registry["classifications"]["hard_gates"]
        expected_prefixes = [
            "implement.md:pre-staged-check",
            "implement.md:alignment",
            "implement.md:test-gate",
            "implement.md:no-new-skips",
            "implement.md:anti-stubbing",
        ]
        for prefix in expected_prefixes:
            assert prefix in gates, "Missing hard gate entry: {}".format(prefix)

    def test_agent_hard_gates_present(self, registry):
        """Key agent hard gates must have entries."""
        gates = registry["classifications"]["hard_gates"]
        expected = [
            "reviewer.md:test-before-approve",
            "reviewer.md:read-only",
            "security-auditor.md:owasp-checklist",
            "doc-master.md:covers-scan",
        ]
        for gate_id in expected:
            assert gate_id in gates, "Missing hard gate entry: {}".format(gate_id)

    def test_no_orphan_gate_entries(self, registry):
        """All hard gate entries must reference existing source files."""
        gates = registry["classifications"]["hard_gates"]
        for gate_id, entry in gates.items():
            location = entry.get("location", "")
            assert location, "Hard gate '{}' has no location".format(gate_id)
            # Check that the referenced file exists
            if ":" in gate_id:
                file_part = gate_id.split(":")[0]
                candidates = list(PLUGIN_DIR.rglob(file_part))
                assert len(candidates) > 0, (
                    "Hard gate '{}' references '{}' which was not found".format(
                        gate_id, file_part
                    )
                )


class TestClassificationValues:
    """Tests for classification field validity."""

    def test_classification_values_valid(self, registry):
        """All classification values must be model-limitation or process-requirement."""
        valid = {"model-limitation", "process-requirement"}
        for section_name in ("hooks", "hard_gates", "forbidden_lists"):
            section = registry["classifications"].get(section_name, {})
            for entry_id, entry in section.items():
                cls = entry.get("classification")
                assert cls in valid, (
                    "{}.{}: invalid classification '{}'".format(
                        section_name, entry_id, cls
                    )
                )

    def test_model_limitation_has_removal_criteria(self, registry):
        """model-limitation entries MUST have non-null removal_criteria."""
        for section_name in ("hooks", "hard_gates", "forbidden_lists"):
            section = registry["classifications"].get(section_name, {})
            for entry_id, entry in section.items():
                if entry.get("classification") == "model-limitation":
                    rc = entry.get("removal_criteria")
                    assert rc is not None and rc.strip(), (
                        "{}.{}: model-limitation must have non-null removal_criteria".format(
                            section_name, entry_id
                        )
                    )

    def test_process_requirement_has_null_removal_criteria(self, registry):
        """process-requirement entries MUST have null removal_criteria."""
        for section_name in ("hooks", "hard_gates", "forbidden_lists"):
            section = registry["classifications"].get(section_name, {})
            for entry_id, entry in section.items():
                if entry.get("classification") == "process-requirement":
                    rc = entry.get("removal_criteria")
                    assert rc is None, (
                        "{}.{}: process-requirement must have null removal_criteria, got '{}'".format(
                            section_name, entry_id, rc
                        )
                    )

    def test_all_entries_have_rationale(self, registry):
        """Every entry must have a non-empty rationale."""
        for section_name in ("hooks", "hard_gates", "forbidden_lists"):
            section = registry["classifications"].get(section_name, {})
            for entry_id, entry in section.items():
                rationale = entry.get("rationale", "")
                assert rationale and rationale.strip(), (
                    "{}.{}: rationale must be non-empty".format(section_name, entry_id)
                )

    def test_review_status_valid(self, registry):
        """review_status must be one of the valid enum values."""
        valid = {"initial", "reviewed", "candidate-for-removal", "removed"}
        for section_name in ("hooks", "hard_gates", "forbidden_lists"):
            section = registry["classifications"].get(section_name, {})
            for entry_id, entry in section.items():
                status = entry.get("review_status")
                assert status in valid, (
                    "{}.{}: invalid review_status '{}'".format(
                        section_name, entry_id, status
                    )
                )


class TestValidationScript:
    """Tests for the validation script itself."""

    def test_validation_script_exists(self):
        """validate_component_classifications.py must exist."""
        assert VALIDATION_SCRIPT.exists(), (
            "Validation script not found: {}".format(VALIDATION_SCRIPT)
        )

    def test_validation_script_runs_successfully(self):
        """Validation script must exit 0 on the current registry."""
        result = subprocess.run(
            [sys.executable, str(VALIDATION_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            "Validation script failed (exit {}):\nstdout: {}\nstderr: {}".format(
                result.returncode, result.stdout, result.stderr
            )
        )
