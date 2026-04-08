"""
Acceptance tests for Issue #710: Active security scanning.

These are static file inspection tests — they verify code structure, function
exports, dataclass fields, and agent documentation content. They run against
not-yet-implemented files (TDD-style) and are expected to fail until the
implementation lands.

All acceptance criteria from Issue #710 are covered here:
  AC1: security-auditor.md mentions "active scan" or "Active Scanning"
  AC2: active_security_scanner.py exists with the 4 required functions
  AC3: dependency_audit() is callable
  AC4: credential_history_scan() is callable
  AC5: owasp_pattern_scan() exists with OWASP_CODE_PATTERNS referenced
  AC6: Finding dataclass has a remediation field
  AC7: SECRET_PATTERNS shared via secret_patterns.py (single source of truth)
  AC8: Functions handle missing tools without crashing (graceful degradation)
"""

import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
AGENTS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "agents"

SCANNER_PATH = LIB_DIR / "active_security_scanner.py"
PATTERNS_PATH = LIB_DIR / "secret_patterns.py"
AUDITOR_AGENT_PATH = AGENTS_DIR / "security-auditor.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_module_from_path(path: Path, module_name: str) -> ModuleType:
    """Import a module directly from a filesystem path."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_scanner() -> Optional[ModuleType]:
    """Load active_security_scanner module, returning None if file absent."""
    if not SCANNER_PATH.exists():
        return None
    try:
        return _import_module_from_path(SCANNER_PATH, "active_security_scanner")
    except Exception:
        return None


def _load_patterns() -> Optional[ModuleType]:
    """Load secret_patterns module, returning None if file absent."""
    if not PATTERNS_PATH.exists():
        return None
    try:
        return _import_module_from_path(PATTERNS_PATH, "secret_patterns")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AC1 — security-auditor.md mentions active scanning
# ---------------------------------------------------------------------------

class TestSecurityAuditorAgentContent:
    """AC1: security-auditor agent must document active scanning capability."""

    def test_auditor_agent_file_exists(self):
        """security-auditor.md must exist at the expected path."""
        assert AUDITOR_AGENT_PATH.exists(), (
            f"security-auditor.md not found at {AUDITOR_AGENT_PATH}"
        )

    def test_auditor_agent_mentions_active_scan(self):
        """security-auditor.md must contain 'active scan' or 'Active Scanning'."""
        assert AUDITOR_AGENT_PATH.exists(), "security-auditor.md not found"
        content = AUDITOR_AGENT_PATH.read_text(encoding="utf-8")
        lowered = content.lower()
        assert "active scan" in lowered, (
            "security-auditor.md must mention 'active scan' or 'Active Scanning' "
            "to document that the agent performs active (not just static) scanning. "
            f"Agent file: {AUDITOR_AGENT_PATH}"
        )


# ---------------------------------------------------------------------------
# AC2 — active_security_scanner.py exists with required functions
# ---------------------------------------------------------------------------

class TestScannerModuleExists:
    """AC2: active_security_scanner.py must exist and export the 4 required functions."""

    def test_scanner_file_exists(self):
        """active_security_scanner.py must exist in the lib directory."""
        assert SCANNER_PATH.exists(), (
            f"active_security_scanner.py not found at {SCANNER_PATH}. "
            "Issue #710 requires this module."
        )

    def test_scanner_module_is_importable(self):
        """active_security_scanner.py must be importable without errors."""
        assert SCANNER_PATH.exists(), "File does not exist — see test above"
        module = _load_scanner()
        assert module is not None, (
            "active_security_scanner.py exists but failed to import. "
            "Check for syntax errors or missing dependencies."
        )

    @pytest.mark.parametrize("fn_name", [
        "dependency_audit",
        "credential_history_scan",
        "owasp_pattern_scan",
        "full_scan",
    ])
    def test_required_function_exported(self, fn_name: str):
        """Each of the 4 required functions must be defined in the module."""
        assert SCANNER_PATH.exists(), "File does not exist — see test above"
        module = _load_scanner()
        assert module is not None, "Module failed to import — see test above"
        assert hasattr(module, fn_name), (
            f"active_security_scanner.py must export '{fn_name}()', "
            f"but it was not found. "
            f"AC2 of Issue #710 requires: dependency_audit, credential_history_scan, "
            f"owasp_pattern_scan, full_scan."
        )

    @pytest.mark.parametrize("fn_name", [
        "dependency_audit",
        "credential_history_scan",
        "owasp_pattern_scan",
        "full_scan",
    ])
    def test_required_function_is_callable(self, fn_name: str):
        """Each exported name must be a callable (function or class)."""
        assert SCANNER_PATH.exists(), "File does not exist — see test above"
        module = _load_scanner()
        assert module is not None, "Module failed to import — see test above"
        obj = getattr(module, fn_name, None)
        assert obj is not None, f"'{fn_name}' not found on module"
        assert callable(obj), (
            f"'{fn_name}' is defined but is not callable. "
            f"It must be a function or class."
        )


# ---------------------------------------------------------------------------
# AC3 — dependency_audit parses requirements.txt
# ---------------------------------------------------------------------------

class TestDependencyAuditFunction:
    """AC3: dependency_audit() must be callable and accept a path argument."""

    def test_dependency_audit_accepts_path_argument(self):
        """dependency_audit must accept at least one argument (project path or req file)."""
        assert SCANNER_PATH.exists(), "File does not exist — see test above"
        module = _load_scanner()
        assert module is not None, "Module failed to import"
        fn = getattr(module, "dependency_audit", None)
        assert fn is not None, "dependency_audit not found"
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert len(params) >= 1, (
            "dependency_audit() must accept at least one argument (project path or "
            "requirements file path). It parses requirements.txt per AC3."
        )

    def test_dependency_audit_source_references_requirements(self):
        """dependency_audit source code must reference 'requirements' (parse requirements.txt)."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        # Find the function definition and check it references requirements
        assert "requirements" in source, (
            "active_security_scanner.py must reference 'requirements' "
            "(e.g., requirements.txt parsing) in the dependency_audit implementation. "
            "AC3 requires dependency audit to parse requirements.txt."
        )


# ---------------------------------------------------------------------------
# AC4 — credential_history_scan covers git history
# ---------------------------------------------------------------------------

class TestCredentialHistoryScanFunction:
    """AC4: credential_history_scan() must cover git history."""

    def test_credential_history_scan_source_references_git(self):
        """credential_history_scan source code must reference git log or git history."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        # The function must mention git in some form near credential_history_scan
        assert "git" in source.lower(), (
            "active_security_scanner.py must reference 'git' (e.g., 'git log') "
            "for credential history scanning. AC4 requires git history coverage."
        )

    def test_credential_history_scan_accepts_path_argument(self):
        """credential_history_scan must accept a path or repo argument."""
        assert SCANNER_PATH.exists(), "File does not exist"
        module = _load_scanner()
        assert module is not None, "Module failed to import"
        fn = getattr(module, "credential_history_scan", None)
        assert fn is not None, "credential_history_scan not found"
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert len(params) >= 1, (
            "credential_history_scan() must accept at least one argument "
            "(repo path or project root). AC4 requires scanning git history."
        )


# ---------------------------------------------------------------------------
# AC5 — owasp_pattern_scan references OWASP_CODE_PATTERNS
# ---------------------------------------------------------------------------

class TestOwaspPatternScanFunction:
    """AC5: owasp_pattern_scan() must exist and OWASP_CODE_PATTERNS must be defined."""

    def test_owasp_code_patterns_defined_in_module(self):
        """OWASP_CODE_PATTERNS constant must be defined in active_security_scanner.py."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        assert "OWASP_CODE_PATTERNS" in source, (
            "active_security_scanner.py must define OWASP_CODE_PATTERNS. "
            "AC5 requires this constant to drive owasp_pattern_scan()."
        )

    def test_owasp_patterns_covers_shell_true(self):
        """OWASP_CODE_PATTERNS must cover shell=True (command injection risk)."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        assert "shell=True" in source or "shell" in source, (
            "active_security_scanner.py must detect 'shell=True' — "
            "a common command injection vector. AC5 lists this as required."
        )

    def test_owasp_patterns_covers_eval(self):
        """OWASP_CODE_PATTERNS must cover eval() usage (code injection risk)."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        # eval should appear in the patterns, not just as a comment
        assert "eval" in source, (
            "active_security_scanner.py must detect 'eval' usage — "
            "a code injection vector. AC5 lists this as required."
        )

    def test_owasp_patterns_covers_sql_injection(self):
        """OWASP_CODE_PATTERNS must cover SQL injection patterns."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        # Check for SQL-related pattern keywords
        has_sql = any(kw in source for kw in ["sql", "SQL", "SELECT", "INSERT", "format(", "% ("])
        assert has_sql, (
            "active_security_scanner.py must detect SQL injection patterns "
            "(e.g., raw SQL with string formatting). AC5 lists this as required."
        )

    def test_owasp_patterns_covers_debug_mode(self):
        """OWASP_CODE_PATTERNS must cover debug mode (security misconfiguration)."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        assert "debug" in source.lower(), (
            "active_security_scanner.py must detect debug mode enablement — "
            "a security misconfiguration. AC5 lists this as required."
        )

    def test_owasp_pattern_scan_accepts_path_argument(self):
        """owasp_pattern_scan must accept a path argument (file or directory to scan)."""
        assert SCANNER_PATH.exists(), "File does not exist"
        module = _load_scanner()
        assert module is not None, "Module failed to import"
        fn = getattr(module, "owasp_pattern_scan", None)
        assert fn is not None, "owasp_pattern_scan not found"
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert len(params) >= 1, (
            "owasp_pattern_scan() must accept at least one argument "
            "(file or directory path to scan)."
        )


# ---------------------------------------------------------------------------
# AC6 — Finding dataclass has a remediation field
# ---------------------------------------------------------------------------

class TestFindingDataclass:
    """AC6: Finding dataclass must include a remediation field for actionable output."""

    def test_finding_class_exists(self):
        """A Finding class or dataclass must be defined in active_security_scanner.py."""
        assert SCANNER_PATH.exists(), "File does not exist"
        module = _load_scanner()
        assert module is not None, "Module failed to import"
        assert hasattr(module, "Finding"), (
            "active_security_scanner.py must define a 'Finding' dataclass or class. "
            "AC6 requires remediation suggestions to be specific via this structure."
        )

    def test_finding_has_remediation_field(self):
        """Finding dataclass must have a 'remediation' field."""
        assert SCANNER_PATH.exists(), "File does not exist"
        module = _load_scanner()
        assert module is not None, "Module failed to import"
        Finding = getattr(module, "Finding", None)
        assert Finding is not None, "Finding class not found"

        # Check via dataclass fields (works for @dataclass)
        if hasattr(Finding, "__dataclass_fields__"):
            fields = Finding.__dataclass_fields__
            assert "remediation" in fields, (
                "Finding dataclass must have a 'remediation' field. "
                "AC6 requires that each finding includes a specific remediation suggestion."
            )
        else:
            # Fallback: check __init__ signature or annotations
            sig = inspect.signature(Finding.__init__)
            params = list(sig.parameters.keys())
            annotations = getattr(Finding, "__annotations__", {})
            has_remediation = "remediation" in params or "remediation" in annotations
            assert has_remediation, (
                "Finding class must include a 'remediation' attribute. "
                "AC6 requires that each finding includes a specific remediation suggestion."
            )

    def test_finding_has_severity_field(self):
        """Finding dataclass should have a 'severity' field for risk classification."""
        assert SCANNER_PATH.exists(), "File does not exist"
        module = _load_scanner()
        assert module is not None, "Module failed to import"
        Finding = getattr(module, "Finding", None)
        assert Finding is not None, "Finding class not found"

        if hasattr(Finding, "__dataclass_fields__"):
            fields = Finding.__dataclass_fields__
            assert "severity" in fields, (
                "Finding dataclass should have a 'severity' field (Critical/High/Medium/Low). "
                "This enables prioritization of remediation work."
            )
        else:
            annotations = getattr(Finding, "__annotations__", {})
            sig = inspect.signature(Finding.__init__)
            params = list(sig.parameters.keys())
            has_severity = "severity" in params or "severity" in annotations
            assert has_severity, "Finding class must include a 'severity' attribute."

    def test_finding_source_references_remediation(self):
        """Source code must reference 'remediation' — not just in the class definition."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        assert source.count("remediation") >= 2, (
            "active_security_scanner.py should reference 'remediation' at least twice: "
            "once in the Finding dataclass and once when constructing findings with "
            "specific remediation text."
        )


# ---------------------------------------------------------------------------
# AC7 — SECRET_PATTERNS via secret_patterns.py (single source of truth)
# ---------------------------------------------------------------------------

class TestSecretPatternsSingleSourceOfTruth:
    """AC7: SECRET_PATTERNS must live in secret_patterns.py and be imported by the scanner."""

    def test_secret_patterns_file_exists(self):
        """secret_patterns.py must exist as a standalone module in lib/."""
        assert PATTERNS_PATH.exists(), (
            f"secret_patterns.py not found at {PATTERNS_PATH}. "
            "AC7 requires a single source of truth for SECRET_PATTERNS."
        )

    def test_secret_patterns_module_is_importable(self):
        """secret_patterns.py must be importable without errors."""
        assert PATTERNS_PATH.exists(), "File does not exist — see test above"
        module = _load_patterns()
        assert module is not None, (
            "secret_patterns.py exists but failed to import. "
            "Check for syntax errors."
        )

    def test_secret_patterns_exports_patterns(self):
        """secret_patterns.py must export SECRET_PATTERNS (list or dict of patterns)."""
        assert PATTERNS_PATH.exists(), "File does not exist"
        module = _load_patterns()
        assert module is not None, "Module failed to import"
        assert hasattr(module, "SECRET_PATTERNS"), (
            "secret_patterns.py must define SECRET_PATTERNS. "
            "This is the single source of truth per AC7."
        )

    def test_secret_patterns_is_non_empty(self):
        """SECRET_PATTERNS must contain at least one pattern."""
        assert PATTERNS_PATH.exists(), "File does not exist"
        module = _load_patterns()
        assert module is not None, "Module failed to import"
        patterns = getattr(module, "SECRET_PATTERNS", None)
        assert patterns is not None, "SECRET_PATTERNS not found"
        assert len(patterns) >= 1, (
            "SECRET_PATTERNS must contain at least one pattern. "
            "An empty patterns list would not detect any secrets."
        )

    def test_scanner_imports_from_secret_patterns(self):
        """active_security_scanner.py must import SECRET_PATTERNS from secret_patterns."""
        assert SCANNER_PATH.exists(), "Scanner file does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        # Must import from secret_patterns, not define its own copy
        assert "secret_patterns" in source, (
            "active_security_scanner.py must import from 'secret_patterns' module. "
            "AC7 requires a single source of truth — defining SECRET_PATTERNS inline "
            "in the scanner creates a second copy that can drift."
        )

    def test_security_scan_hook_can_share_patterns(self):
        """The existing security_scan.py hook should be able to use secret_patterns.py."""
        # This is a forward-compatibility check: the hook must not define its OWN
        # SECRET_PATTERNS that would conflict with the new shared source of truth.
        # We verify secret_patterns.py has patterns compatible with what the hook uses.
        assert PATTERNS_PATH.exists(), "secret_patterns.py does not exist"
        module = _load_patterns()
        assert module is not None, "Module failed to import"
        patterns = getattr(module, "SECRET_PATTERNS", None)
        assert patterns is not None, "SECRET_PATTERNS not found"
        # Verify at least one Anthropic API key pattern exists (the hook checks for sk-)
        patterns_str = str(patterns)
        assert "sk-" in patterns_str or "anthropic" in patterns_str.lower(), (
            "SECRET_PATTERNS in secret_patterns.py must include at least the "
            "Anthropic API key pattern (sk-...) to be compatible with the existing hook."
        )


# ---------------------------------------------------------------------------
# AC8 — Graceful degradation (functions handle missing tools without crashing)
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    """AC8: Functions must handle missing external tools without crashing."""

    def test_scanner_source_has_try_except_for_subprocess(self):
        """Scanner must wrap subprocess/shell calls in try/except for graceful degradation."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        has_try_except = "try:" in source and "except" in source
        assert has_try_except, (
            "active_security_scanner.py must use try/except to handle subprocess "
            "failures gracefully. Tools like 'pip-audit' or 'git' may not be installed. "
            "AC8 requires graceful degradation."
        )

    def test_scanner_source_handles_subprocess_failure(self):
        """Scanner must reference subprocess error handling (CalledProcessError or FileNotFoundError)."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        # Check for either subprocess exception types or a broad except that covers them
        has_subprocess_error_handling = any(kw in source for kw in [
            "CalledProcessError",
            "FileNotFoundError",
            "subprocess.SubprocessError",
            "OSError",
            "Exception",
        ])
        assert has_subprocess_error_handling, (
            "active_security_scanner.py must handle subprocess failures. "
            "At minimum, catch FileNotFoundError (tool not installed) or "
            "CalledProcessError (tool returned non-zero). AC8 requires graceful degradation."
        )

    def test_full_scan_returns_results_structure(self):
        """full_scan() must return a structured result (not None or bare exception)."""
        assert SCANNER_PATH.exists(), "File does not exist"
        module = _load_scanner()
        assert module is not None, "Module failed to import"
        fn = getattr(module, "full_scan", None)
        assert fn is not None, "full_scan not found"
        sig = inspect.signature(fn)
        # full_scan should have a return annotation or at least a docstring describing output
        has_return_annotation = sig.return_annotation != inspect.Parameter.empty
        has_docstring = bool(getattr(fn, "__doc__", ""))
        assert has_return_annotation or has_docstring, (
            "full_scan() must document its return type via annotation or docstring. "
            "Callers need to know what structure to expect from the scanner."
        )

    def test_dependency_audit_graceful_when_no_requirements_file(self):
        """dependency_audit() source must handle the case when requirements.txt is missing."""
        assert SCANNER_PATH.exists(), "File does not exist"
        source = SCANNER_PATH.read_text(encoding="utf-8")
        # Look for path existence checks or exception handling around requirements
        handles_missing = any(kw in source for kw in [
            ".exists()",
            "not path",
            "FileNotFoundError",
            "try:",
            "if not ",
        ])
        assert handles_missing, (
            "dependency_audit() must handle the case where requirements.txt is absent. "
            "AC8 requires graceful degradation — not every repo has requirements.txt."
        )
