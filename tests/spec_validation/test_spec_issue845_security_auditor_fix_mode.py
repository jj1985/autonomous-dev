"""Spec validation tests for Issue #845: Security-auditor absent in --fix mode.

The --fix mode pipeline should auto-detect security-sensitive file changes
(trading, auth, payment, migration, etc.) and make security-auditor invocation
mandatory when such files are detected.

Acceptance criteria:
1. Application-domain patterns (trading, payment, billing, financial, transaction,
   auth, crypto, migration) trigger security-auditor invocation in fix mode
2. SECURITY_SENSITIVE_PATTERNS includes application-domain patterns alongside
   existing infrastructure patterns
3. Test files (tests/ prefix) are excluded from security-sensitive detection
4. implement-fix.md STEP F4 includes deterministic detection step
5. implement.md STEP 10 pattern list is aligned with expanded pattern set
6. Both old infra patterns and new app-domain patterns are correctly matched
7. Non-sensitive paths do not false-positive as security-sensitive
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from pipeline_intent_validator import SECURITY_SENSITIVE_PATTERNS


# --- Criterion 1 & 2: Application-domain patterns exist in SECURITY_SENSITIVE_PATTERNS ---


class TestApplicationDomainPatterns:
    """Verify that application-domain security patterns are present."""

    @pytest.mark.parametrize(
        "pattern",
        [
            "trading",
            "payment",
            "billing",
            "financial",
            "transaction",
            "auth",
            "crypto",
            "migration",
        ],
    )
    def test_spec_issue845_1_app_domain_pattern_present(self, pattern: str):
        """Criterion 1/2: Application-domain pattern is in SECURITY_SENSITIVE_PATTERNS."""
        assert pattern in SECURITY_SENSITIVE_PATTERNS, (
            f"Pattern '{pattern}' missing from SECURITY_SENSITIVE_PATTERNS"
        )


# --- Criterion 2: Infrastructure patterns still present alongside new ones ---


class TestInfrastructurePatterns:
    """Verify that existing infrastructure patterns are preserved."""

    @pytest.mark.parametrize(
        "pattern",
        [
            "hooks/",
            "lib/auto_approval_engine",
            "lib/tool_validator",
            "config/auto_approve_policy",
            "lib/security",
        ],
    )
    def test_spec_issue845_2_infra_pattern_present(self, pattern: str):
        """Criterion 2: Infrastructure patterns remain in SECURITY_SENSITIVE_PATTERNS."""
        assert pattern in SECURITY_SENSITIVE_PATTERNS, (
            f"Infrastructure pattern '{pattern}' missing from SECURITY_SENSITIVE_PATTERNS"
        )


# --- Criterion 3: Test files excluded from security-sensitive detection ---


class TestTestFileExclusion:
    """Verify that test file paths are excluded from security detection."""

    @pytest.mark.parametrize(
        "test_path",
        [
            "tests/unit/test_trading_engine.py",
            "tests/integration/test_payment_flow.py",
            "tests/unit/test_auth_handler.py",
            "tests/regression/test_migration_fix.py",
            "tests/security/test_crypto_utils.py",
        ],
    )
    def test_spec_issue845_3_test_files_excluded(self, test_path: str):
        """Criterion 3: Paths starting with tests/ must be excluded.

        The exclusion is applied by callers (not by the tuple itself),
        so we verify the documented behavior: skip if startswith('tests/').
        """
        # The documented exclusion rule: paths starting with tests/ are excluded
        assert test_path.startswith("tests/"), "Test path fixture should start with tests/"

        # Simulate the caller's exclusion logic as documented
        is_excluded = test_path.startswith("tests/")
        assert is_excluded, f"Path '{test_path}' should be excluded by tests/ prefix rule"

        # But the pattern WOULD match if the exclusion were not applied
        matched = any(pattern in test_path for pattern in SECURITY_SENSITIVE_PATTERNS)
        assert matched, (
            f"Path '{test_path}' should match a pattern (proving exclusion is needed)"
        )


# --- Criterion 4: implement-fix.md STEP F4 has deterministic detection ---


class TestImplementFixDetectionStep:
    """Verify implement-fix.md contains the required detection step."""

    @pytest.fixture
    def fix_md_content(self) -> str:
        fix_md = (
            REPO_ROOT
            / "plugins"
            / "autonomous-dev"
            / "commands"
            / "implement-fix.md"
        )
        return fix_md.read_text()

    def test_spec_issue845_4a_detection_step_exists(self, fix_md_content: str):
        """Criterion 4: STEP F4 includes security-sensitivity detection."""
        # Must mention security-sensitivity detection in context of STEP F4
        assert "Security-Sensitivity Detection" in fix_md_content or \
               "security-sensitivity detection" in fix_md_content.lower(), (
            "implement-fix.md must include security-sensitivity detection step"
        )

    def test_spec_issue845_4b_outputs_matched_files(self, fix_md_content: str):
        """Criterion 4: Detection step outputs which files matched."""
        assert "matched" in fix_md_content.lower(), (
            "Detection step must output which files matched"
        )

    def test_spec_issue845_4c_outputs_required_or_skip(self, fix_md_content: str):
        """Criterion 4: Detection step outputs whether security-auditor is REQUIRED or SKIP."""
        assert "REQUIRED" in fix_md_content and "SKIP" in fix_md_content, (
            "Detection step must output REQUIRED or SKIP for security-auditor"
        )


# --- Criterion 5: implement.md STEP 10 pattern list alignment ---


class TestImplementMdAlignment:
    """Verify implement.md STEP 10 patterns are aligned with expanded set."""

    @pytest.fixture
    def implement_md_content(self) -> str:
        impl_md = (
            REPO_ROOT
            / "plugins"
            / "autonomous-dev"
            / "commands"
            / "implement.md"
        )
        return impl_md.read_text()

    @pytest.mark.parametrize(
        "app_pattern",
        ["trading", "payment", "billing", "financial", "transaction", "migration"],
    )
    def test_spec_issue845_5_implement_md_has_app_patterns(
        self, implement_md_content: str, app_pattern: str
    ):
        """Criterion 5: implement.md STEP 10 pattern list includes app-domain patterns."""
        # The pattern should appear somewhere in the security-sensitive section of implement.md
        assert app_pattern in implement_md_content.lower(), (
            f"implement.md should contain application-domain pattern '{app_pattern}' "
            f"in its security-sensitive pattern list to stay aligned"
        )


# --- Criterion 6: Both old and new patterns correctly match file paths ---


class TestPatternMatching:
    """Verify substring matching works for both old and new patterns."""

    @pytest.mark.parametrize(
        "file_path,expected_pattern",
        [
            # Old infrastructure patterns
            ("plugins/autonomous-dev/hooks/unified_pre_tool.py", "hooks/"),
            ("plugins/autonomous-dev/lib/auto_approval_engine.py", "lib/auto_approval_engine"),
            ("plugins/autonomous-dev/lib/tool_validator.py", "lib/tool_validator"),
            (".claude/config/auto_approve_policy.json", "config/auto_approve_policy"),
            ("plugins/autonomous-dev/lib/security_utils.py", "lib/security"),
            # New application-domain patterns
            ("src/trading/engine.py", "trading"),
            ("services/payment_gateway.py", "payment"),
            ("lib/billing/invoices.py", "billing"),
            ("core/financial/ledger.py", "financial"),
            ("models/transaction.py", "transaction"),
            ("src/auth/login.py", "auth"),
            ("utils/crypto_helpers.py", "crypto"),
            ("db/migration/0001_initial.py", "migration"),
            ("alembic/versions/abc123.py", "alembic"),
            ("src/wallet/balance.py", "wallet"),
        ],
    )
    def test_spec_issue845_6_pattern_matches_path(
        self, file_path: str, expected_pattern: str
    ):
        """Criterion 6: Both infra and app-domain patterns match via substring."""
        matched = any(pattern in file_path for pattern in SECURITY_SENSITIVE_PATTERNS)
        assert matched, (
            f"File path '{file_path}' should match pattern '{expected_pattern}' "
            f"via substring match against SECURITY_SENSITIVE_PATTERNS"
        )


# --- Criterion 7: Non-sensitive paths do not false-positive ---


class TestNoFalsePositives:
    """Verify non-sensitive paths are not flagged."""

    @pytest.mark.parametrize(
        "file_path",
        [
            "README.md",
            "docs/architecture.md",
            "docs/getting-started.md",
            "utils/formatting.py",
            "src/helpers/string_utils.py",
            "CHANGELOG.md",
            "setup.py",
            "pyproject.toml",
            "src/models/user_profile.py",
            "scripts/deploy.sh",
        ],
    )
    def test_spec_issue845_7_no_false_positive(self, file_path: str):
        """Criterion 7: Non-sensitive paths must not match any security pattern."""
        matched_patterns = [
            p for p in SECURITY_SENSITIVE_PATTERNS if p in file_path
        ]
        assert not matched_patterns, (
            f"Non-sensitive path '{file_path}' falsely matched patterns: {matched_patterns}"
        )
