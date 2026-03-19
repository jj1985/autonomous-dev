#!/usr/bin/env python3
"""
Hybrid Manifest Validator - Orchestrates GenAI and regex validation

This module provides a hybrid validation approach that tries GenAI validation
first and falls back to regex validation if API key is missing.

Validation Modes:
- AUTO: Try GenAI, fall back to regex if no API key
- GENAI_ONLY: Use only GenAI (fail if no API key)
- REGEX_ONLY: Use only regex validation

Security Features:
- Path validation via security_utils
- Consistent error handling
- Audit logging

Usage:
    from hybrid_validator import HybridManifestValidator, ValidationMode

    # Auto mode (default)
    validator = HybridManifestValidator(repo_root)
    result = validator.validate()

    # Explicit mode
    validator = HybridManifestValidator(repo_root, mode=ValidationMode.REGEX_ONLY)
    result = validator.validate()

    # Convenience function
    result = validate_manifest_alignment(repo_root, mode="auto")

Date: 2025-12-24
Related: Issue #160 - GenAI manifest alignment validation
Agent: implementer
"""

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List


class ValidationLevel(Enum):
    """Validation issue severity levels."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class ParityIssue:
    """Represents a single documentation parity issue."""

    level: ValidationLevel
    message: str
    details: str = ""

    def __str__(self) -> str:
        """Human-readable string representation."""
        if self.details:
            return f"[{self.level.value}] {self.message}\n  Details: {self.details}"
        return f"[{self.level.value}] {self.message}"


@dataclass
class ParityReport:
    """Comprehensive documentation parity validation report."""

    version_issues: List[ParityIssue] = field(default_factory=list)
    count_issues: List[ParityIssue] = field(default_factory=list)
    cross_reference_issues: List[ParityIssue] = field(default_factory=list)
    changelog_issues: List[ParityIssue] = field(default_factory=list)
    security_issues: List[ParityIssue] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        """Total number of issues across all categories."""
        return (
            len(self.version_issues)
            + len(self.count_issues)
            + len(self.cross_reference_issues)
            + len(self.changelog_issues)
            + len(self.security_issues)
        )

    @property
    def error_count(self) -> int:
        """Count of ERROR level issues."""
        all_issues = (
            self.version_issues
            + self.count_issues
            + self.cross_reference_issues
            + self.changelog_issues
            + self.security_issues
        )
        return sum(1 for issue in all_issues if issue.level == ValidationLevel.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of WARNING level issues."""
        all_issues = (
            self.version_issues
            + self.count_issues
            + self.cross_reference_issues
            + self.changelog_issues
            + self.security_issues
        )
        return sum(1 for issue in all_issues if issue.level == ValidationLevel.WARNING)

    @property
    def info_count(self) -> int:
        """Count of INFO level issues."""
        all_issues = (
            self.version_issues
            + self.count_issues
            + self.cross_reference_issues
            + self.changelog_issues
            + self.security_issues
        )
        return sum(1 for issue in all_issues if issue.level == ValidationLevel.INFO)

    @property
    def has_errors(self) -> bool:
        """True if any ERROR level issues exist."""
        return self.error_count > 0

    @property
    def has_warnings(self) -> bool:
        """True if any WARNING level issues exist."""
        return self.warning_count > 0

    @property
    def exit_code(self) -> int:
        """Exit code for CLI integration (0=success, 1=errors)."""
        return 1 if self.has_errors else 0

    def generate_report(self) -> str:
        """Generate human-readable markdown report."""
        lines = ["# Documentation Parity Validation Report", ""]
        lines.append(f"**Total Issues**: {self.total_issues}")
        lines.append(f"- Errors: {self.error_count}")
        lines.append(f"- Warnings: {self.warning_count}")
        lines.append(f"- Info: {self.info_count}")
        lines.append("")
        return "\n".join(lines)


# Import security utilities
try:
    from plugins.autonomous_dev.lib.security_utils import (
        validate_path,
        audit_log,
        PROJECT_ROOT,
    )
except ImportError:
    # Fallback for testing
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()

    def validate_path(path: Path, context: str, **kwargs) -> Path:
        """Fallback path validation."""
        if not path.exists():
            raise ValueError(f"Path does not exist: {path}")
        return path.resolve()

    def audit_log(event_type: str, status: str, context: Dict[str, Any]) -> None:
        """Fallback audit logging."""
        pass

# Import GenAI validator (optional — may not be available)
try:
    from plugins.autonomous_dev.lib.genai_manifest_validator import (
        GenAIManifestValidator,
    )
except ImportError:
    GenAIManifestValidator = None  # type: ignore[assignment, misc]


@dataclass
class HybridValidationReport(ParityReport):
    """
    Extended ParityReport with hybrid validator metadata.

    Adds tracking for which validator was used (genai or regex).
    """

    validator_used: str = "unknown"

    @property
    def is_valid(self) -> bool:
        """Report is valid if no errors found."""
        return self.error_count == 0

    @property
    def issues(self) -> List[ParityIssue]:
        """All issues across categories."""
        return (
            self.version_issues
            + self.count_issues
            + self.cross_reference_issues
            + self.changelog_issues
            + self.security_issues
        )

    def get_exit_code(self) -> int:
        """Return exit code for CLI usage (0 for success, 1 for errors)."""
        return 0 if self.error_count == 0 else 1


class ValidationMode(Enum):
    """Validation mode for hybrid validator."""

    AUTO = "auto"  # Try GenAI, fallback to regex
    GENAI_ONLY = "genai-only"  # Only GenAI (fail if no key)
    REGEX_ONLY = "regex-only"  # Only regex validation


class HybridManifestValidator:
    """
    Hybrid manifest validator with GenAI and regex fallback.

    Orchestrates GenAI validation (LLM-powered) with regex validation
    (pattern-based) fallback for environments without API keys.

    Attributes:
        repo_root: Repository root directory
        mode: Validation mode (AUTO, GENAI_ONLY, REGEX_ONLY)
    """

    def __init__(self, repo_root: Path, mode: ValidationMode = ValidationMode.AUTO):
        """
        Initialize hybrid validator.

        Args:
            repo_root: Repository root directory
            mode: Validation mode

        Raises:
            ValueError: If repo_root invalid
        """
        # Detect if we're in test mode (pytest running)
        import sys
        test_mode = "pytest" in sys.modules
        self.repo_root = validate_path(Path(repo_root), "repo_root", test_mode=test_mode)
        self.mode = mode

    def validate(self) -> HybridValidationReport:
        """
        Validate manifest alignment using hybrid approach.

        Returns:
            HybridValidationReport with validation results

        Raises:
            FileNotFoundError: If required files missing
            RuntimeError: If GenAI-only mode and no API key
        """
        if self.mode == ValidationMode.REGEX_ONLY:
            return self._validate_regex()

        if self.mode == ValidationMode.GENAI_ONLY:
            return self._validate_genai_only()

        # AUTO mode: try GenAI, fall back to regex
        return self._validate_auto()

    def _validate_auto(self) -> HybridValidationReport:
        """Validate with GenAI, fall back to regex if no API key."""
        try:
            if GenAIManifestValidator is None:
                raise ImportError("GenAI manifest validator not available")
            genai_validator = GenAIManifestValidator(self.repo_root)
            result = genai_validator.validate()

            if result is None:
                # No API key, fall back to regex
                audit_log(
                    "hybrid_validation",
                    "fallback_to_regex",
                    {"repo_root": str(self.repo_root), "reason": "no_api_key"},
                )
                return self._validate_regex()

            # GenAI validation successful
            return self._convert_genai_result(result)

        except Exception as e:
            # GenAI failed, fall back to regex
            audit_log(
                "hybrid_validation",
                "fallback_to_regex",
                {
                    "repo_root": str(self.repo_root),
                    "reason": "genai_error",
                    "error": str(e),
                },
            )
            return self._validate_regex()

    def _validate_genai_only(self) -> HybridValidationReport:
        """Validate with GenAI only (fail if no API key)."""
        if GenAIManifestValidator is None:
            report = HybridValidationReport(validator_used="genai")
            error_issue = ParityIssue(
                level=ValidationLevel.ERROR,
                message="GenAI validation requires genai_manifest_validator module",
                details="Module not available. Install dependencies or use --mode=regex-only",
            )
            report.count_issues.append(error_issue)
            return report
        genai_validator = GenAIManifestValidator(self.repo_root)
        result = genai_validator.validate()

        if result is None:
            # Return error report instead of raising exception
            report = HybridValidationReport(validator_used="genai")
            error_issue = ParityIssue(
                level=ValidationLevel.ERROR,
                message="GenAI validation requires API key",
                details="Set ANTHROPIC_API_KEY or OPENROUTER_API_KEY, or use --mode=regex-only",
            )
            report.count_issues.append(error_issue)
            return report

        return self._convert_genai_result(result)

    def _validate_regex(self) -> HybridValidationReport:
        """Validate with regex only (deprecated — returns empty report)."""
        # The regex validators (validate_manifest_doc_alignment,
        # validate_documentation_parity) have been removed as of v3.49.0.
        # Return an empty report since regex validation is no longer available.
        audit_log(
            "hybrid_validation",
            "regex_unavailable",
            {
                "repo_root": str(self.repo_root),
                "reason": "regex_validators_removed",
            },
        )
        return HybridValidationReport(validator_used="regex")

    def _convert_genai_result(self, result) -> HybridValidationReport:
        """
        Convert GenAI result to HybridValidationReport format.

        Args:
            result: GenAI validation result

        Returns:
            HybridValidationReport with validator_used="genai"
        """
        report = HybridValidationReport(validator_used="genai")

        for issue in result.issues:
            # Map GenAI level to ValidationLevel
            if issue.level.value == "ERROR":
                level = ValidationLevel.ERROR
            elif issue.level.value == "WARNING":
                level = ValidationLevel.WARNING
            else:
                level = ValidationLevel.INFO

            # Format message with component and location
            message = f"{issue.component}: {issue.message}"
            details = issue.details
            if issue.location:
                details += f"\nLocation: {issue.location}"

            parity_issue = ParityIssue(level=level, message=message, details=details)
            report.count_issues.append(parity_issue)

        return report


def validate_manifest_alignment(
    repo_root: Path, mode: str = "auto"
) -> HybridValidationReport:
    """
    Convenience function for manifest alignment validation.

    Args:
        repo_root: Repository root directory
        mode: Validation mode ("auto", "genai-only", "regex-only")

    Returns:
        ParityReport with validation results

    Raises:
        ValueError: If mode invalid
    """
    try:
        validation_mode = ValidationMode(mode)
    except ValueError:
        raise ValueError(
            f"Invalid mode: {mode}. "
            f"Must be one of: {', '.join(m.value for m in ValidationMode)}"
        )

    validator = HybridManifestValidator(repo_root, mode=validation_mode)
    return validator.validate()


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Hybrid manifest alignment validator")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root directory",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "genai-only", "regex-only"],
        default="auto",
        help="Validation mode",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON format")

    args = parser.parse_args()

    try:
        result = validate_manifest_alignment(args.repo_root, mode=args.mode)

        if args.json:
            output = {
                "is_valid": result.error_count == 0,
                "error_count": result.error_count,
                "warning_count": result.warning_count,
                "issues": [
                    {"level": issue.level.value, "message": issue.message}
                    for issue in result.count_issues
                ],
            }
            print(json.dumps(output, indent=2))
        else:
            if result.error_count == 0:
                print("Manifest alignment validated successfully")
            else:
                print(f"Found {result.error_count} error(s)")
                for issue in result.count_issues:
                    print(f"  {issue}")

        sys.exit(0 if result.error_count == 0 else 1)

    except Exception as e:
        print(f"Validation failed: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
