"""Acceptance tests for Issue #769: Expand Hypothesis PBT to all pure lib functions.

Static file inspection tests verifying PBT infrastructure and coverage.
"""

import ast
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PROPERTY_DIR = REPO_ROOT / "tests" / "property"


class TestHypothesisConfiguration:
    """Acceptance: Hypothesis profiles configured."""

    def test_conftest_has_ci_profile(self):
        conftest = PROPERTY_DIR / "conftest.py"
        content = conftest.read_text()
        assert "register_profile" in content, "conftest.py missing profile registration"
        assert '"ci"' in content or "'ci'" in content, "Missing CI profile"

    def test_conftest_has_default_profile(self):
        conftest = PROPERTY_DIR / "conftest.py"
        content = conftest.read_text()
        assert '"default"' in content or "'default'" in content, "Missing default profile"

    def test_conftest_loads_from_env(self):
        conftest = PROPERTY_DIR / "conftest.py"
        content = conftest.read_text()
        assert "HYPOTHESIS_PROFILE" in content, "Missing HYPOTHESIS_PROFILE env var"

    def test_ci_profile_max_examples_200(self):
        conftest = PROPERTY_DIR / "conftest.py"
        content = conftest.read_text()
        assert "max_examples=200" in content, "CI profile should use max_examples=200"

    def test_default_profile_max_examples_50(self):
        conftest = PROPERTY_DIR / "conftest.py"
        content = conftest.read_text()
        assert "max_examples=50" in content, "Default profile should use max_examples=50"


class TestNewPropertyTestFiles:
    """Acceptance: at least 10 new property test files."""

    def test_at_least_10_new_files(self):
        existing = {
            "test_pipeline_state_properties.py",
            "test_security_utils_properties.py",
            "test_tool_validator_properties.py",
            "conftest.py",
            "__init__.py",
        }
        all_files = {f.name for f in PROPERTY_DIR.glob("test_*_properties.py")}
        new_files = all_files - existing
        assert len(new_files) >= 10, (
            f"Expected >= 10 new property test files, found {len(new_files)}: {sorted(new_files)}"
        )


class TestModuleLevelStrategies:
    """Acceptance: all strategies defined at module level."""

    def test_no_inline_strategies(self):
        """Check that st.* calls are not inside test functions."""
        for test_file in PROPERTY_DIR.glob("test_*_properties.py"):
            tree = ast.parse(test_file.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    # Check for st.something() calls inside test functions
                    for child in ast.walk(node):
                        if (isinstance(child, ast.Call)
                            and isinstance(child.func, ast.Attribute)
                            and isinstance(child.func.value, ast.Name)
                            and child.func.value.id == "st"
                            and child.func.attr not in ("data",)):
                            # Allow st.data() which is draw-based
                            pytest.fail(
                                f"{test_file.name}:{node.name} has inline strategy "
                                f"st.{child.func.attr}() — should be module-level"
                            )


class TestExampleDecorators:
    """Acceptance: @example on every @given test."""

    def test_every_given_has_example(self):
        for test_file in PROPERTY_DIR.glob("test_*_properties.py"):
            content = test_file.read_text()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    decorators = [
                        d for d in node.decorator_list
                        if isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Name)
                        and d.func.id == "given"
                    ]
                    if decorators:
                        examples = [
                            d for d in node.decorator_list
                            if isinstance(d, ast.Call)
                            and isinstance(d.func, ast.Name)
                            and d.func.id == "example"
                        ]
                        assert len(examples) >= 1, (
                            f"{test_file.name}:{node.name} has @given but no @example"
                        )


class TestNoAssumeUsage:
    """Acceptance: no assume() calls anywhere."""

    def test_no_assume_calls(self):
        for test_file in PROPERTY_DIR.glob("test_*_properties.py"):
            content = test_file.read_text()
            assert "assume(" not in content, (
                f"{test_file.name} uses assume() — should use .filter() instead"
            )


class TestCoverageCategories:
    """Acceptance: PBT covers key categories."""

    def test_roundtrip_tests_exist(self):
        """Serialize/deserialize roundtrip tests."""
        files = [f.name for f in PROPERTY_DIR.glob("test_*_properties.py")]
        has_settings = "test_settings_generator_properties.py" in files
        has_quality = "test_quality_enforcer_properties.py" in files
        assert has_settings or has_quality, (
            "Missing roundtrip property tests (settings_generator or quality_enforcer)"
        )

    def test_validation_tests_exist(self):
        """Input validation property tests."""
        files = [f.name for f in PROPERTY_DIR.glob("test_*_properties.py")]
        validation_files = [f for f in files if "validation" in f or "prompt_integrity" in f or "sanitiz" in f]
        assert len(validation_files) >= 1, "Missing input validation property tests"

    def test_set_operation_tests_exist(self):
        """Set operation / approval engine tests."""
        files = [f.name for f in PROPERTY_DIR.glob("test_*_properties.py")]
        set_files = [f for f in files if "auto_approval" in f or "approval" in f]
        assert len(set_files) >= 1, "Missing set operation property tests"


class TestDocumentation:
    """Acceptance: SKILL.md updated."""

    def test_skill_md_has_pbt_candidate_guidance(self):
        skill_md = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "skills"
            / "testing-guide" / "SKILL.md"
        )
        content = skill_md.read_text()
        assert "candidate" in content.lower() or "when to use" in content.lower(), (
            "SKILL.md missing PBT candidate selection guidance"
        )

    def test_skill_md_has_hypothesis_profile(self):
        skill_md = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "skills"
            / "testing-guide" / "SKILL.md"
        )
        content = skill_md.read_text()
        assert "HYPOTHESIS_PROFILE" in content, (
            "SKILL.md missing Hypothesis profile configuration"
        )
