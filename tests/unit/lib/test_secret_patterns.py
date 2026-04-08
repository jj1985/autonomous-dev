"""
Unit tests for secret_patterns.py — Issue #710.

Validates pattern correctness and completeness.
"""

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from secret_patterns import (
    COMPILED_OWASP_PATTERNS,
    COMPILED_SECRET_PATTERNS,
    DEPENDENCY_ADVISORIES,
    OWASP_CODE_PATTERNS,
    SECRET_PATTERNS,
)


class TestSecretPatterns:
    """Tests for SECRET_PATTERNS correctness."""

    def test_patterns_is_non_empty_list(self):
        """SECRET_PATTERNS should be a non-empty list."""
        assert isinstance(SECRET_PATTERNS, list)
        assert len(SECRET_PATTERNS) >= 10

    def test_each_pattern_is_tuple(self):
        """Each pattern should be a (regex, description) tuple."""
        for pattern in SECRET_PATTERNS:
            assert isinstance(pattern, tuple)
            assert len(pattern) == 2
            regex_str, desc = pattern
            assert isinstance(regex_str, str)
            assert isinstance(desc, str)

    def test_patterns_compile(self):
        """All patterns should be valid regex."""
        for regex_str, desc in SECRET_PATTERNS:
            compiled = re.compile(regex_str)
            assert compiled is not None, f"Failed to compile: {desc}"

    def test_detects_anthropic_key(self):
        """Should match an Anthropic API key (sk-...)."""
        line = 'API_KEY = "sk-abcdefghijklmnopqrstuvwxyz"'
        matched = any(re.search(p, line) for p, _ in SECRET_PATTERNS)
        assert matched, "Should detect Anthropic API key"

    def test_detects_aws_key(self):
        """Should match an AWS access key ID."""
        line = "aws_key = AKIAIOSFODNN7EXAMPLE"
        matched = any(re.search(p, line) for p, _ in SECRET_PATTERNS)
        assert matched, "Should detect AWS access key"

    def test_detects_github_pat(self):
        """Should match a GitHub personal access token."""
        line = "token = ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
        matched = any(re.search(p, line) for p, _ in SECRET_PATTERNS)
        assert matched, "Should detect GitHub PAT"

    def test_detects_database_url(self):
        """Should match a database URL with credentials."""
        line = 'DB_URL = "postgres://admin:s3cret@db.example.com/mydb"'
        matched = any(re.search(p, line) for p, _ in SECRET_PATTERNS)
        assert matched, "Should detect database URL with credentials"

    def test_compiled_patterns_match(self):
        """COMPILED_SECRET_PATTERNS should work the same as raw patterns."""
        line = 'key = "sk-abcdefghijklmnopqrstuvwxyz"'
        matched = any(compiled.search(line) for compiled, _ in COMPILED_SECRET_PATTERNS)
        assert matched


class TestOwaspCodePatterns:
    """Tests for OWASP_CODE_PATTERNS correctness."""

    def test_owasp_patterns_non_empty(self):
        """OWASP_CODE_PATTERNS should have at least 5 entries."""
        assert len(OWASP_CODE_PATTERNS) >= 5

    def test_each_pattern_is_triple(self):
        """Each OWASP pattern should be (regex, category, remediation)."""
        for pattern in OWASP_CODE_PATTERNS:
            assert isinstance(pattern, tuple)
            assert len(pattern) == 3
            regex_str, category, remediation = pattern
            assert isinstance(regex_str, str)
            assert isinstance(category, str)
            assert isinstance(remediation, str)
            assert len(remediation) > 10, "Remediation should be specific"


class TestDependencyAdvisories:
    """Tests for DEPENDENCY_ADVISORIES correctness."""

    def test_advisories_non_empty(self):
        """DEPENDENCY_ADVISORIES should have entries."""
        assert len(DEPENDENCY_ADVISORIES) >= 3

    def test_advisory_structure(self):
        """Each advisory should have required fields."""
        for pkg, advisories in DEPENDENCY_ADVISORIES.items():
            assert isinstance(advisories, list)
            for adv in advisories:
                assert "affected_versions" in adv
                assert "severity" in adv
                assert "remediation" in adv
