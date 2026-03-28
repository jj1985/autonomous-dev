"""Unit tests for runtime_verification_classifier.

Tests classification of changed files into runtime verification
categories: frontend, API, and CLI targets.

Issue: #564
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add lib to path so we can import the classifier
_LIB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "plugins" / "autonomous-dev" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from runtime_verification_classifier import (
    ApiTarget,
    CliTarget,
    FrontendTarget,
    RuntimeVerificationPlan,
    classify_runtime_targets,
    _detect_api_targets,
    _detect_cli_targets,
    _detect_frontend_targets,
    _is_test_file,
)


# ============================================================
# Frontend detection tests
# ============================================================


class TestFrontendDetection:
    """Test detection of frontend files."""

    def test_html_file_detected(self):
        targets = _detect_frontend_targets(["public/index.html"])
        assert len(targets) == 1
        assert targets[0].framework == "html"

    def test_tsx_file_detected_as_react(self):
        targets = _detect_frontend_targets(["src/App.tsx"])
        assert len(targets) == 1
        assert targets[0].framework == "react"

    def test_jsx_file_detected_as_react(self):
        targets = _detect_frontend_targets(["src/Component.jsx"])
        assert len(targets) == 1
        assert targets[0].framework == "react"

    def test_vue_file_detected(self):
        targets = _detect_frontend_targets(["src/views/Home.vue"])
        assert len(targets) == 1
        assert targets[0].framework == "vue"

    def test_svelte_file_detected(self):
        targets = _detect_frontend_targets(["src/routes/+page.svelte"])
        assert len(targets) == 1
        assert targets[0].framework == "svelte"

    def test_suggested_checks_populated(self):
        targets = _detect_frontend_targets(["index.html"])
        assert len(targets[0].suggested_checks) > 0

    def test_test_tsx_file_excluded(self):
        targets = _detect_frontend_targets(["src/App.test.tsx"])
        assert len(targets) == 0

    def test_test_directory_tsx_excluded(self):
        targets = _detect_frontend_targets(["tests/components/Button.tsx"])
        assert len(targets) == 0

    def test_non_frontend_file_ignored(self):
        targets = _detect_frontend_targets(["src/utils.py", "README.md"])
        assert len(targets) == 0


# ============================================================
# API detection tests
# ============================================================


class TestApiDetection:
    """Test detection of API route/endpoint files."""

    def test_routes_directory_detected(self):
        targets = _detect_api_targets(["src/routes/users.py"])
        assert len(targets) == 1

    def test_api_directory_detected(self):
        targets = _detect_api_targets(["backend/api/handlers.py"])
        assert len(targets) == 1

    def test_endpoints_directory_detected(self):
        targets = _detect_api_targets(["app/endpoints/auth.py"])
        assert len(targets) == 1

    def test_views_directory_detected(self):
        targets = _detect_api_targets(["myapp/views/user_views.py"])
        assert len(targets) == 1

    def test_app_py_detected(self):
        targets = _detect_api_targets(["app.py"])
        assert len(targets) == 1

    def test_server_py_detected(self):
        targets = _detect_api_targets(["server.py"])
        assert len(targets) == 1

    def test_main_py_detected(self):
        targets = _detect_api_targets(["main.py"])
        assert len(targets) == 1

    def test_fastapi_framework_hint(self):
        targets = _detect_api_targets(["src/fastapi/routes/users.py"])
        assert len(targets) == 1
        assert targets[0].framework == "fastapi"

    def test_flask_framework_hint(self):
        targets = _detect_api_targets(["flask_app/routes/index.py"])
        assert len(targets) == 1
        assert targets[0].framework == "flask"

    def test_js_file_in_routes_detected_as_express(self):
        targets = _detect_api_targets(["src/routes/users.js"])
        assert len(targets) == 1
        assert targets[0].framework == "express"

    def test_test_routes_file_excluded(self):
        targets = _detect_api_targets(["tests/routes/test_users.py"])
        assert len(targets) == 0

    def test_test_prefix_routes_excluded(self):
        targets = _detect_api_targets(["test_routes.py"])
        assert len(targets) == 0

    def test_markdown_files_excluded(self):
        targets = _detect_api_targets(["api/README.md"])
        assert len(targets) == 0

    def test_plain_library_not_detected(self):
        targets = _detect_api_targets(["src/utils/helpers.py"])
        assert len(targets) == 0


# ============================================================
# CLI detection tests
# ============================================================


class TestCliDetection:
    """Test detection of CLI tools and scripts."""

    def test_shell_script_detected(self):
        targets = _detect_cli_targets(["deploy.sh"])
        assert len(targets) == 1
        assert targets[0].tool_name == "deploy"

    def test_bin_directory_detected(self):
        targets = _detect_cli_targets(["bin/mytool"])
        assert len(targets) == 1
        assert targets[0].tool_name == "mytool"

    def test_scripts_directory_detected(self):
        targets = _detect_cli_targets(["scripts/run_migration.py"])
        assert len(targets) == 1

    def test_cli_directory_detected(self):
        targets = _detect_cli_targets(["cli/main.py"])
        assert len(targets) == 1

    def test_cli_suffix_py_detected(self):
        targets = _detect_cli_targets(["tools/deploy_cli.py"])
        assert len(targets) == 1

    def test_cli_prefix_py_detected(self):
        targets = _detect_cli_targets(["cli_deploy.py"])
        assert len(targets) == 1

    def test_suggested_commands_for_sh(self):
        targets = _detect_cli_targets(["deploy.sh"])
        assert any("bash" in cmd for cmd in targets[0].suggested_commands)

    def test_suggested_commands_for_py(self):
        targets = _detect_cli_targets(["scripts/run.py"])
        assert any("python3" in cmd for cmd in targets[0].suggested_commands)

    def test_suggested_commands_have_timeout(self):
        targets = _detect_cli_targets(["scripts/run.py"])
        assert any("timeout 30" in cmd for cmd in targets[0].suggested_commands)

    def test_markdown_commands_excluded(self):
        """This project's Markdown commands must NOT be classified as CLI."""
        targets = _detect_cli_targets([
            "plugins/autonomous-dev/commands/implement.md",
            "plugins/autonomous-dev/commands/audit.md",
            "commands/setup.md",
        ])
        assert len(targets) == 0

    def test_markdown_agents_excluded(self):
        """This project's agent prompts must NOT be classified as CLI."""
        targets = _detect_cli_targets([
            "plugins/autonomous-dev/agents/reviewer.md",
            "agents/implementer.md",
        ])
        assert len(targets) == 0

    def test_test_scripts_excluded(self):
        targets = _detect_cli_targets(["tests/scripts/test_deploy.sh"])
        assert len(targets) == 0


# ============================================================
# Integration: classify_runtime_targets
# ============================================================


class TestClassifyRuntimeTargets:
    """Test the main classification entry point."""

    def test_empty_file_list(self):
        plan = classify_runtime_targets([])
        assert plan.has_targets is False
        assert len(plan.frontend) == 0
        assert len(plan.api) == 0
        assert len(plan.cli) == 0

    def test_no_targets_for_library_code(self):
        plan = classify_runtime_targets([
            "src/utils/helpers.py",
            "src/models/user.py",
            "README.md",
        ])
        assert plan.has_targets is False
        assert "No runtime verification targets" in plan.summary

    def test_frontend_only(self):
        plan = classify_runtime_targets(["src/App.tsx", "public/index.html"])
        assert plan.has_targets is True
        assert len(plan.frontend) == 2
        assert len(plan.api) == 0
        assert len(plan.cli) == 0
        assert "Frontend: 2 target(s)" in plan.summary

    def test_api_only(self):
        plan = classify_runtime_targets(["src/routes/users.py"])
        assert plan.has_targets is True
        assert len(plan.api) == 1
        assert "API: 1 target(s)" in plan.summary

    def test_cli_only(self):
        plan = classify_runtime_targets(["scripts/deploy.sh"])
        assert plan.has_targets is True
        assert len(plan.cli) == 1
        assert "CLI: 1 target(s)" in plan.summary

    def test_mixed_targets(self):
        plan = classify_runtime_targets([
            "src/App.tsx",
            "src/routes/api.py",
            "scripts/deploy.sh",
            "src/utils/helpers.py",
        ])
        assert plan.has_targets is True
        assert len(plan.frontend) == 1
        assert len(plan.api) == 1
        assert len(plan.cli) == 1
        assert "Frontend" in plan.summary
        assert "API" in plan.summary
        assert "CLI" in plan.summary

    def test_returns_runtime_verification_plan(self):
        plan = classify_runtime_targets(["index.html"])
        assert isinstance(plan, RuntimeVerificationPlan)

    def test_frontend_target_type(self):
        plan = classify_runtime_targets(["src/App.vue"])
        assert isinstance(plan.frontend[0], FrontendTarget)

    def test_api_target_type(self):
        plan = classify_runtime_targets(["src/routes/users.py"])
        assert isinstance(plan.api[0], ApiTarget)

    def test_cli_target_type(self):
        plan = classify_runtime_targets(["bin/tool"])
        assert isinstance(plan.cli[0], CliTarget)


# ============================================================
# Helper function tests
# ============================================================


class TestIsTestFile:
    """Test the test file detection helper."""

    def test_test_prefix(self):
        assert _is_test_file("test_something.py") is True

    def test_test_suffix(self):
        assert _is_test_file("something_test.py") is True

    def test_test_tsx(self):
        assert _is_test_file("Component.test.tsx") is True

    def test_test_js(self):
        assert _is_test_file("module.test.js") is True

    def test_spec_ts(self):
        assert _is_test_file("service.spec.ts") is True

    def test_tests_directory(self):
        assert _is_test_file("tests/unit/test_foo.py") is True

    def test_dunder_tests_directory(self):
        assert _is_test_file("src/__tests__/App.tsx") is True

    def test_regular_file(self):
        assert _is_test_file("src/utils.py") is False

    def test_regular_html(self):
        assert _is_test_file("public/index.html") is False
