"""Regression tests for expanded SECURITY_SENSITIVE_PATTERNS (Issue #845).

Validates that:
1. Infrastructure patterns (pre-existing) still match.
2. Application-domain patterns (auth, financial, schema, env) now match.
3. Test files starting with 'tests/' are explicitly handled as non-sensitive
   by callers (pattern presence vs caller exclusion separation of concerns).
4. Clearly non-sensitive paths do NOT match any pattern.
"""

import sys
from pathlib import Path

import pytest

# Portable project root detection
_current = Path(__file__).resolve()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

from pipeline_intent_validator import SECURITY_SENSITIVE_PATTERNS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def matches_any_pattern(file_path: str) -> bool:
    """Return True if file_path matches any security-sensitive pattern."""
    return any(pattern in file_path for pattern in SECURITY_SENSITIVE_PATTERNS)


def matches_excluding_tests(file_path: str) -> bool:
    """Return True if file_path matches a pattern AND is not a test file.

    Mirrors the exclusion rule documented in implement-fix.md: paths starting
    with 'tests/' are excluded because test files that reference security
    topics do not themselves pose a security risk.
    """
    if file_path.startswith("tests/"):
        return False
    return matches_any_pattern(file_path)


# ---------------------------------------------------------------------------
# Infrastructure patterns (pre-existing — must not regress)
# ---------------------------------------------------------------------------


class TestInfrastructurePatterns:
    """Pre-existing infrastructure patterns MUST still match after expansion."""

    def test_hooks_directory_matches(self) -> None:
        assert matches_any_pattern("hooks/unified_pre_tool.py")

    def test_auto_approval_engine_matches(self) -> None:
        assert matches_any_pattern("lib/auto_approval_engine.py")

    def test_tool_validator_matches(self) -> None:
        assert matches_any_pattern("lib/tool_validator.py")

    def test_auto_approve_policy_matches(self) -> None:
        assert matches_any_pattern("config/auto_approve_policy.json")

    def test_lib_security_matches(self) -> None:
        assert matches_any_pattern("lib/security_utils.py")


# ---------------------------------------------------------------------------
# Auth / access-control patterns (new in Issue #845)
# ---------------------------------------------------------------------------


class TestAuthPatterns:
    """Application-domain auth patterns MUST match."""

    def test_auth_directory_matches(self) -> None:
        assert matches_any_pattern("auth/login.py")

    def test_auth_in_filename_matches(self) -> None:
        assert matches_any_pattern("src/auth_middleware.py")

    def test_crypto_module_matches(self) -> None:
        assert matches_any_pattern("lib/crypto/hash.py")

    def test_permission_module_matches(self) -> None:
        assert matches_any_pattern("permissions/rbac.py")

    def test_session_handler_matches(self) -> None:
        assert matches_any_pattern("session/manager.py")

    def test_token_service_matches(self) -> None:
        assert matches_any_pattern("services/token_service.py")

    def test_secret_store_matches(self) -> None:
        assert matches_any_pattern("secret_store.py")

    def test_credential_provider_matches(self) -> None:
        assert matches_any_pattern("providers/credential_provider.py")

    def test_password_reset_matches(self) -> None:
        assert matches_any_pattern("views/password_reset.py")

    def test_oauth_client_matches(self) -> None:
        assert matches_any_pattern("integrations/oauth_client.py")

    def test_sso_handler_matches(self) -> None:
        assert matches_any_pattern("sso/handler.py")

    def test_jwt_utils_matches(self) -> None:
        assert matches_any_pattern("utils/jwt_utils.py")

    def test_rbac_engine_matches(self) -> None:
        assert matches_any_pattern("rbac/engine.py")


# ---------------------------------------------------------------------------
# Financial / transactional patterns (new in Issue #845)
# ---------------------------------------------------------------------------


class TestFinancialPatterns:
    """Application-domain financial patterns MUST match."""

    def test_trading_daemon_matches(self) -> None:
        assert matches_any_pattern("trading/daemon.py")

    def test_trading_in_filename_matches(self) -> None:
        assert matches_any_pattern("trading_engine.py")

    def test_payment_processor_matches(self) -> None:
        assert matches_any_pattern("payment/processor.py")

    def test_billing_invoice_matches(self) -> None:
        assert matches_any_pattern("billing/invoice.py")

    def test_financial_report_matches(self) -> None:
        assert matches_any_pattern("reports/financial_report.py")

    def test_transaction_log_matches(self) -> None:
        assert matches_any_pattern("models/transaction_log.py")

    def test_wallet_service_matches(self) -> None:
        assert matches_any_pattern("services/wallet_service.py")


# ---------------------------------------------------------------------------
# Database schema patterns (new in Issue #845)
# ---------------------------------------------------------------------------


class TestSchemaMigrationPatterns:
    """Database migration patterns MUST match."""

    def test_migrations_directory_matches(self) -> None:
        assert matches_any_pattern("migrations/001_add_users.py")

    def test_alembic_versions_matches(self) -> None:
        assert matches_any_pattern("alembic/versions/abc123_add_column.py")

    def test_alembic_env_matches(self) -> None:
        assert matches_any_pattern("alembic/env.py")


# ---------------------------------------------------------------------------
# Environment file patterns (new in Issue #845)
# ---------------------------------------------------------------------------


class TestEnvironmentFilePatterns:
    """Environment file patterns MUST match."""

    def test_dotenv_matches(self) -> None:
        assert matches_any_pattern(".env")

    def test_dotenv_production_matches(self) -> None:
        assert matches_any_pattern(".env.production")

    def test_dotenv_local_matches(self) -> None:
        assert matches_any_pattern(".env.local")


# ---------------------------------------------------------------------------
# Test-file exclusion (callers MUST exclude tests/ prefix)
# ---------------------------------------------------------------------------


class TestTestFileExclusion:
    """Callers must exclude test files even if they match a pattern."""

    def test_test_auth_excluded_by_caller(self) -> None:
        # The pattern 'auth' would match, but the caller exclusion rule applies
        assert not matches_excluding_tests("tests/unit/test_auth.py")

    def test_test_trading_excluded_by_caller(self) -> None:
        assert not matches_excluding_tests("tests/integration/test_trading.py")

    def test_test_payment_excluded_by_caller(self) -> None:
        assert not matches_excluding_tests("tests/unit/test_payment_processor.py")

    def test_non_test_auth_still_matches(self) -> None:
        # Same path without tests/ prefix MUST match
        assert matches_excluding_tests("src/auth/views.py")


# ---------------------------------------------------------------------------
# Non-sensitive paths (MUST NOT match)
# ---------------------------------------------------------------------------


class TestNonSensitivePaths:
    """Clearly non-sensitive paths MUST NOT match any pattern."""

    def test_readme_does_not_match(self) -> None:
        assert not matches_any_pattern("README.md")

    def test_formatting_utils_does_not_match(self) -> None:
        assert not matches_any_pattern("src/utils/formatting.py")

    def test_trading_docs_guide_matches(self) -> None:
        # 'trading' in docs path still matches (pattern is a substring match).
        # Callers are responsible for excluding docs paths if desired.
        # This test documents the intentional broad-matching behaviour.
        assert matches_any_pattern("docs/trading-guide.md")

    def test_generic_models_does_not_match(self) -> None:
        assert not matches_any_pattern("models/user.py")

    def test_generic_views_does_not_match(self) -> None:
        assert not matches_any_pattern("views/home.py")

    def test_setup_py_does_not_match(self) -> None:
        assert not matches_any_pattern("setup.py")

    def test_pyproject_does_not_match(self) -> None:
        assert not matches_any_pattern("pyproject.toml")


# ---------------------------------------------------------------------------
# Pattern completeness: all expected patterns are present in the tuple
# ---------------------------------------------------------------------------


class TestPatternTupleCompleteness:
    """Verify all required patterns are present in SECURITY_SENSITIVE_PATTERNS."""

    REQUIRED_PATTERNS = [
        # Infrastructure (pre-existing)
        "hooks/",
        "lib/auto_approval_engine",
        "lib/tool_validator",
        "config/auto_approve_policy",
        "lib/security",
        # Auth/access (new)
        "auth",
        "crypto",
        "permission",
        "session",
        "token",
        "secret",
        "credential",
        "password",
        "oauth",
        "sso",
        "jwt",
        "rbac",
        # Financial (new)
        "trading",
        "payment",
        "billing",
        "financial",
        "transaction",
        "wallet",
        # Schema (new)
        "migration",
        "alembic",
        # Environment (new)
        ".env",
    ]

    @pytest.mark.parametrize("pattern", REQUIRED_PATTERNS)
    def test_pattern_present_in_tuple(self, pattern: str) -> None:
        assert pattern in SECURITY_SENSITIVE_PATTERNS, (
            f"Pattern '{pattern}' is missing from SECURITY_SENSITIVE_PATTERNS. "
            f"Add it to pipeline_intent_validator.py."
        )
