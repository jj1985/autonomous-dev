"""Acceptance tests for Issue #770: Add mutation testing (mutmut).

These are static file inspection tests that verify the mutation testing
infrastructure is properly set up. They do NOT require LLM calls.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestMutmutSetup:
    """Acceptance: mutmut installed as dev dependency with config."""

    def test_mutmut_in_dev_requirements(self):
        req_file = REPO_ROOT / "plugins" / "autonomous-dev" / "requirements-dev.txt"
        assert req_file.exists(), "requirements-dev.txt missing"
        content = req_file.read_text()
        assert "mutmut" in content, "mutmut not listed in dev requirements"

    def test_setup_cfg_has_mutmut_section(self):
        setup_cfg = REPO_ROOT / "setup.cfg"
        assert setup_cfg.exists(), "setup.cfg not found at repo root"
        content = setup_cfg.read_text()
        assert "[mutmut]" in content, "setup.cfg missing [mutmut] section"

    def test_mutmut_config_paths_to_mutate(self):
        setup_cfg = REPO_ROOT / "setup.cfg"
        content = setup_cfg.read_text()
        assert "paths_to_mutate" in content, "Missing paths_to_mutate in [mutmut]"
        assert "plugins/autonomous-dev/lib/" in content, (
            "paths_to_mutate should target plugins/autonomous-dev/lib/"
        )

    def test_mutmut_config_runner(self):
        setup_cfg = REPO_ROOT / "setup.cfg"
        content = setup_cfg.read_text()
        assert "runner" in content, "Missing runner in [mutmut] config"
        assert "pytest" in content, "Runner should use pytest"

    def test_mutmut_cache_gitignored(self):
        gitignore = REPO_ROOT / ".gitignore"
        assert gitignore.exists(), ".gitignore missing"
        content = gitignore.read_text()
        assert ".mutmut-cache" in content, ".mutmut-cache/ not in .gitignore"


class TestRunnerScript:
    """Acceptance: runner script exists and is executable."""

    def test_runner_script_exists(self):
        script = REPO_ROOT / "scripts" / "run_mutation_tests.sh"
        assert script.exists(), "scripts/run_mutation_tests.sh missing"

    def test_runner_script_executable(self):
        import os
        script = REPO_ROOT / "scripts" / "run_mutation_tests.sh"
        assert os.access(script, os.X_OK), "run_mutation_tests.sh is not executable"

    def test_runner_script_supports_file_flag(self):
        script = REPO_ROOT / "scripts" / "run_mutation_tests.sh"
        content = script.read_text()
        assert "--file" in content, "Runner script missing --file flag support"

    def test_runner_script_supports_ci_flag(self):
        script = REPO_ROOT / "scripts" / "run_mutation_tests.sh"
        content = script.read_text()
        assert "--ci" in content, "Runner script missing --ci flag support"


class TestBaselineDocumentation:
    """Acceptance: mutation score baselines documented."""

    def test_baseline_report_exists(self):
        report = REPO_ROOT / "docs" / "reports" / "mutation-testing-baseline.md"
        assert report.exists(), "docs/reports/mutation-testing-baseline.md missing"

    def test_baseline_covers_pipeline_state(self):
        report = REPO_ROOT / "docs" / "reports" / "mutation-testing-baseline.md"
        content = report.read_text()
        assert "pipeline_state" in content, "Baseline missing pipeline_state.py scores"

    def test_baseline_covers_tool_validator(self):
        report = REPO_ROOT / "docs" / "reports" / "mutation-testing-baseline.md"
        content = report.read_text()
        assert "tool_validator" in content, "Baseline missing tool_validator.py scores"

    def test_baseline_covers_settings_generator(self):
        report = REPO_ROOT / "docs" / "reports" / "mutation-testing-baseline.md"
        content = report.read_text()
        assert "settings_generator" in content, "Baseline missing settings_generator.py scores"


class TestMutantKillerTests:
    """Acceptance: at least 5 new tests targeting boundary conditions."""

    def test_mutation_killer_test_file_exists(self):
        test_file = REPO_ROOT / "tests" / "unit" / "lib" / "test_mutation_killers.py"
        assert test_file.exists(), "test_mutation_killers.py missing"

    def test_at_least_5_test_functions(self):
        import ast
        test_file = REPO_ROOT / "tests" / "unit" / "lib" / "test_mutation_killers.py"
        tree = ast.parse(test_file.read_text())
        test_funcs = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
        assert len(test_funcs) >= 5, (
            f"Expected >= 5 test functions, found {len(test_funcs)}"
        )

    def test_tests_target_boundary_conditions(self):
        test_file = REPO_ROOT / "tests" / "unit" / "lib" / "test_mutation_killers.py"
        content = test_file.read_text()
        boundary_indicators = ["boundary", "edge", "off_by_one", "<=", ">=", "==", "!="]
        found = any(ind in content for ind in boundary_indicators)
        assert found, "Tests should target boundary conditions (conditional mutations)"


class TestDocumentation:
    """Acceptance: testing-guide SKILL.md updated."""

    def test_skill_md_has_mutation_section(self):
        skill_md = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "skills"
            / "testing-guide" / "SKILL.md"
        )
        assert skill_md.exists(), "testing-guide SKILL.md missing"
        content = skill_md.read_text()
        assert "mutation" in content.lower(), (
            "SKILL.md missing mutation testing section"
        )

    def test_skill_md_documents_score_target(self):
        skill_md = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "skills"
            / "testing-guide" / "SKILL.md"
        )
        content = skill_md.read_text()
        assert "70%" in content, "SKILL.md should document 70%+ mutation score target"

    def test_skill_md_documents_equivalent_mutants(self):
        skill_md = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "skills"
            / "testing-guide" / "SKILL.md"
        )
        content = skill_md.read_text()
        assert "equivalent" in content.lower(), (
            "SKILL.md should include equivalent mutant triage guidance"
        )
