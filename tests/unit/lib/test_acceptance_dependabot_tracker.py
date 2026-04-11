"""Acceptance tests for Issue #767: Auto-create Dependabot security issues.

Static file inspection tests verifying the dependabot tracker infrastructure.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestLibFileExists:
    """Acceptance: dependabot_tracker.py exists in lib/."""

    def test_dependabot_tracker_exists(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        assert lib_file.exists(), "lib/dependabot_tracker.py missing"

    def test_has_run_dependabot_tracker_function(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = lib_file.read_text()
        assert "def run_dependabot_tracker" in content, (
            "Missing run_dependabot_tracker entry point"
        )

    def test_has_parse_owner_repo_function(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = lib_file.read_text()
        assert "def parse_owner_repo" in content, "Missing parse_owner_repo function"


class TestSecurityInvariants:
    """Acceptance: all subprocess calls use shell=False."""

    def test_no_shell_true(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = lib_file.read_text()
        assert "shell=True" not in content, (
            "dependabot_tracker.py must not use shell=True"
        )

    def test_has_ghsa_validation(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = lib_file.read_text()
        assert "GHSA-" in content, "Missing GHSA ID validation pattern"
        assert re.search(r"re\.(compile|match|search|fullmatch)", content), (
            "GHSA validation should use regex"
        )

    def test_subprocess_run_used(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = lib_file.read_text()
        assert "subprocess.run" in content, "Should use subprocess.run"
        assert "subprocess.call" not in content, "Should not use subprocess.call"
        assert "os.system" not in content, "Should not use os.system"


class TestDeduplication:
    """Acceptance: HTML comment dedup markers used."""

    def test_ghsa_html_comment_marker(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = lib_file.read_text()
        assert "<!-- GHSA:" in content, (
            "Missing GHSA HTML comment deduplication marker"
        )

    def test_batch_comment_marker(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = lib_file.read_text()
        # Either GHSA-BATCH or DEPENDABOT_BATCH
        has_batch = "GHSA-BATCH" in content or "DEPENDABOT_BATCH" in content
        assert has_batch, "Missing batch deduplication marker for medium alerts"


class TestNonBlockingBehavior:
    """Acceptance: errors are caught, not raised."""

    def test_try_except_in_entry_point(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        tree = ast.parse(lib_file.read_text())
        # Find run_dependabot_tracker function
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run_dependabot_tracker":
                has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
                assert has_try, (
                    "run_dependabot_tracker must have try/except for non-blocking"
                )
                return
        assert False, "run_dependabot_tracker function not found"

    def test_error_prefix_in_logging(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = lib_file.read_text()
        assert "dependabot-tracker" in content, (
            "Error logging should use [dependabot-tracker] prefix"
        )


class TestSeverityHandling:
    """Acceptance: different severity levels handled differently."""

    def test_individual_for_critical_high(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = lib_file.read_text()
        assert "critical" in content, "Must handle critical severity"
        assert "high" in content, "Must handle high severity"

    def test_batch_for_medium(self):
        lib_file = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = lib_file.read_text()
        assert "medium" in content, "Must handle medium severity"


class TestPipelineIntegration:
    """Acceptance: STEP 13 integration exists."""

    def test_implement_md_references_dependabot(self):
        impl_md = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"
        )
        content = impl_md.read_text()
        assert "dependabot" in content.lower(), (
            "implement.md STEP 13 missing dependabot tracker reference"
        )


class TestUnitTests:
    """Acceptance: comprehensive unit tests exist."""

    def test_unit_test_file_exists(self):
        test_file = (
            REPO_ROOT / "tests" / "unit" / "lib" / "test_dependabot_tracker.py"
        )
        assert test_file.exists(), "test_dependabot_tracker.py missing"

    def test_at_least_15_test_functions(self):
        test_file = (
            REPO_ROOT / "tests" / "unit" / "lib" / "test_dependabot_tracker.py"
        )
        tree = ast.parse(test_file.read_text())
        test_funcs = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
        assert len(test_funcs) >= 15, (
            f"Expected >= 15 test functions, found {len(test_funcs)}"
        )
