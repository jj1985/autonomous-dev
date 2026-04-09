"""Acceptance tests for Issue #737 — Regression Test Enforcement

Static file inspection tests that verify the enforcement infrastructure will exist
after implementation. They check file existence, content patterns, and registration.

These tests will fail until the feature is implemented.
"""

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


class TestBugfixDetectorExists:
    """Verify plugins/autonomous-dev/lib/bugfix_detector.py exists with required functions."""

    BUGFIX_DETECTOR = REPO_ROOT / "plugins/autonomous-dev/lib/bugfix_detector.py"

    def test_module_file_exists(self):
        """bugfix_detector.py module must exist."""
        assert self.BUGFIX_DETECTOR.exists(), (
            f"bugfix_detector.py not found at {self.BUGFIX_DETECTOR}\n"
            f"This file must be created as part of Issue #737 implementation."
        )

    def test_has_is_bugfix_feature_function(self):
        """Module must define is_bugfix_feature() function."""
        content = self.BUGFIX_DETECTOR.read_text()
        assert "def is_bugfix_feature(" in content, (
            "bugfix_detector.py must contain 'def is_bugfix_feature(' function.\n"
            "This function detects whether a feature description/commit is a bug fix."
        )

    def test_has_is_bugfix_commit_function(self):
        """Module must define is_bugfix_commit() function."""
        content = self.BUGFIX_DETECTOR.read_text()
        assert "def is_bugfix_commit(" in content, (
            "bugfix_detector.py must contain 'def is_bugfix_commit(' function.\n"
            "This function detects whether a git commit message is a bug fix."
        )

    def test_has_get_test_count_function(self):
        """Module must define get_test_count() function."""
        content = self.BUGFIX_DETECTOR.read_text()
        assert "def get_test_count(" in content, (
            "bugfix_detector.py must contain 'def get_test_count(' function.\n"
            "This function returns the number of tests for before/after comparison."
        )


class TestPreCommitHookExists:
    """Verify plugins/autonomous-dev/hooks/enforce_regression_test.py exists."""

    HOOK_FILE = REPO_ROOT / "plugins/autonomous-dev/hooks/enforce_regression_test.py"

    def test_hook_file_exists(self):
        """enforce_regression_test.py hook must exist."""
        assert self.HOOK_FILE.exists(), (
            f"Hook file not found at {self.HOOK_FILE}\n"
            f"This hook must be created as part of Issue #737 implementation."
        )

    def test_has_shebang_on_first_line(self):
        """Hook must have #!/usr/bin/env shebang on first line."""
        content = self.HOOK_FILE.read_text()
        first_line = content.split("\n")[0]
        assert first_line.startswith("#!/usr/bin/env"), (
            f"First line of hook must be a shebang starting with '#!/usr/bin/env'.\n"
            f"Got: {first_line!r}"
        )

    def test_contains_required_next_action(self):
        """Hook must follow stick+carrot pattern with REQUIRED NEXT ACTION."""
        content = self.HOOK_FILE.read_text()
        assert "REQUIRED NEXT ACTION" in content, (
            "enforce_regression_test.py must contain 'REQUIRED NEXT ACTION' string.\n"
            "This follows the stick+carrot enforcement pattern: every block must include "
            "a REQUIRED NEXT ACTION directive so the user knows how to proceed."
        )


class TestImplementMdHardGate:
    """Verify plugins/autonomous-dev/commands/implement.md has regression test hard gate."""

    IMPLEMENT_MD = REPO_ROOT / "plugins/autonomous-dev/commands/implement.md"

    def test_contains_regression_test_requirement(self):
        """implement.md must document the Regression Test Requirement hard gate."""
        content = self.IMPLEMENT_MD.read_text()
        assert "Regression Test Requirement" in content, (
            "implement.md must contain 'Regression Test Requirement' text.\n"
            "This hard gate ensures regression tests are added for all bug fixes."
        )

    def test_references_bugfix_detector(self):
        """implement.md must reference bugfix_detector or is_bugfix_feature."""
        content = self.IMPLEMENT_MD.read_text()
        has_bugfix_detector = "bugfix_detector" in content
        has_is_bugfix_feature = "is_bugfix_feature" in content
        assert has_bugfix_detector or has_is_bugfix_feature, (
            "implement.md must reference 'bugfix_detector' or 'is_bugfix_feature'.\n"
            "The command must instruct the implementer to use the bugfix detector library."
        )

    def test_contains_baseline_test_count(self):
        """implement.md must contain BASELINE_TEST_COUNT for before/after comparison."""
        content = self.IMPLEMENT_MD.read_text()
        assert "BASELINE_TEST_COUNT" in content, (
            "implement.md must contain 'BASELINE_TEST_COUNT'.\n"
            "This enables before/after test count comparison to verify regression tests "
            "were actually added when fixing a bug."
        )


class TestHookRegistration:
    """Verify enforce_regression_test is registered in all required locations."""

    MANIFEST = REPO_ROOT / "plugins/autonomous-dev/config/install_manifest.json"
    SETTINGS_LOCAL = REPO_ROOT / "plugins/autonomous-dev/templates/settings.local.json"
    SETTINGS_AUTONOMOUS_DEV = REPO_ROOT / "plugins/autonomous-dev/templates/settings.autonomous-dev.json"

    def test_manifest_contains_hook(self):
        """install_manifest.json must list enforce_regression_test hook."""
        content = self.MANIFEST.read_text()
        assert "enforce_regression_test" in content, (
            "install_manifest.json must contain 'enforce_regression_test'.\n"
            "All hook files must be listed in the install manifest so they are "
            "deployed correctly via scripts/deploy-all.sh."
        )

    def test_settings_local_contains_hook(self):
        """settings.local.json template must register enforce_regression_test."""
        content = self.SETTINGS_LOCAL.read_text()
        assert "enforce_regression_test" in content, (
            "settings.local.json must contain 'enforce_regression_test'.\n"
            "All hooks must be registered in ALL settings templates, not just some."
        )

    def test_settings_autonomous_dev_contains_hook(self):
        """settings.autonomous-dev.json template must register enforce_regression_test."""
        content = self.SETTINGS_AUTONOMOUS_DEV.read_text()
        assert "enforce_regression_test" in content, (
            "settings.autonomous-dev.json must contain 'enforce_regression_test'.\n"
            "All hooks must be registered in ALL settings templates, not just some."
        )


class TestNoFalsePositives:
    """Verify bugfix_detector.py uses proper regex word boundary matching."""

    BUGFIX_DETECTOR = REPO_ROOT / "plugins/autonomous-dev/lib/bugfix_detector.py"

    def test_uses_regex_word_boundary_matching(self):
        """bugfix_detector.py must use regex for word-boundary-safe matching."""
        content = self.BUGFIX_DETECTOR.read_text()
        has_word_boundary = r"\b" in content
        has_re_search = "re.search" in content
        has_re_compile = "re.compile" in content
        assert has_word_boundary or has_re_search or has_re_compile, (
            "bugfix_detector.py must use regex word boundary matching.\n"
            "Expected one of: '\\b' word boundary, 're.search(', or 're.compile('.\n"
            "Simple string matching (e.g., 'fix' in text) causes false positives on "
            "words like 'prefix', 'suffix', 'fixture' — regex boundaries prevent this."
        )
