"""Classifier for detecting recoverable-blocking signals in tool output.

Identifies whether errors encountered during implementation are recoverable
(can be fixed with a mini-replan) or structural (require escalation).

Issue #730: Adaptive replanning when implementer encounters blocking information.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

# Try to reuse sanitize_error_message from failure_classifier
try:
    from failure_classifier import sanitize_error_message as _sanitize_from_fc
except ImportError:
    _sanitize_from_fc = None


# =============================================================================
# Constants
# =============================================================================

MAX_MINI_REPLAN_CYCLES = 2
MAX_DIRECTIVE_ERROR_LENGTH = 500


# =============================================================================
# Types
# =============================================================================


class BlockingSignalType(Enum):
    """Classification of blocking signals by recoverability."""

    RECOVERABLE = "recoverable"
    STRUCTURAL = "structural"
    NOT_BLOCKING = "not_blocking"


@dataclass(frozen=True)
class BlockingSignal:
    """Result of classifying an error output for blocking signals.

    Attributes:
        signal_type: Whether the signal is recoverable, structural, or not blocking.
        error_name: Short name of the detected error (e.g. "ModuleNotFoundError").
        error_detail: Extracted detail from the error message.
        suggested_action: Recommended corrective action for the implementer.
    """

    signal_type: BlockingSignalType
    error_name: str
    error_detail: str
    suggested_action: str


# =============================================================================
# Pattern Definitions
# =============================================================================

# Maps (regex_pattern, error_name) -> suggested_action
# These are recoverable errors that can be fixed with a mini-replan cycle.
RECOVERABLE_SIGNAL_PATTERNS: Dict[Tuple[str, str], str] = {
    (r"ModuleNotFoundError:\s*No module named\s+['\"]?(\S+)['\"]?", "ModuleNotFoundError"): (
        "Install missing module or use alternative"
    ),
    (r"FileNotFoundError:.*?(?:No such file or directory:?\s*)?['\"]?([^\n'\"]+)['\"]?", "FileNotFoundError"): (
        "Verify file path or create missing file"
    ),
    (r"ImportError:\s*(.+)", "ImportError"): (
        "Fix import path or install dependency"
    ),
    (r"AttributeError:\s*(.+)", "AttributeError"): (
        "Check API compatibility or use correct attribute"
    ),
    (r"(?:command not found|exit code 127).*?(\S+)?", "CommandNotFound"): (
        "Install missing CLI tool or use alternative"
    ),
}

# Structural errors that cannot be fixed with a mini-replan
_STRUCTURAL_PATTERNS = [
    r"SyntaxError:",
    r"IndentationError:",
    r"TabError:",
]


# =============================================================================
# Classification
# =============================================================================


def classify_blocking_signal(error_output: str) -> BlockingSignal:
    """Classify an error output string into a blocking signal type.

    Examines the error output for known patterns and returns a BlockingSignal
    indicating whether the error is recoverable, structural, or not blocking.

    Args:
        error_output: Raw error output from a tool execution.

    Returns:
        BlockingSignal with classification, error name, detail, and suggested action.
    """
    if not error_output or not error_output.strip():
        return BlockingSignal(
            signal_type=BlockingSignalType.NOT_BLOCKING,
            error_name="",
            error_detail="",
            suggested_action="",
        )

    # Check structural patterns first (not recoverable)
    for pattern in _STRUCTURAL_PATTERNS:
        if re.search(pattern, error_output):
            match = re.search(pattern + r"\s*(.*)", error_output)
            detail = match.group(1).strip() if match else ""
            error_name = pattern.rstrip(":").replace(r"\\", "")
            return BlockingSignal(
                signal_type=BlockingSignalType.STRUCTURAL,
                error_name=error_name,
                error_detail=detail,
                suggested_action="Fix syntax before retrying",
            )

    # Check recoverable patterns
    for (pattern, error_name), suggested_action in RECOVERABLE_SIGNAL_PATTERNS.items():
        match = re.search(pattern, error_output)
        if match:
            detail = match.group(1).strip() if match.lastindex and match.lastindex >= 1 else ""
            return BlockingSignal(
                signal_type=BlockingSignalType.RECOVERABLE,
                error_name=error_name,
                error_detail=detail,
                suggested_action=suggested_action,
            )

    return BlockingSignal(
        signal_type=BlockingSignalType.NOT_BLOCKING,
        error_name="",
        error_detail="",
        suggested_action="",
    )


# =============================================================================
# Directive Formatting
# =============================================================================


def sanitize_error_for_directive(error_output: Optional[str]) -> str:
    """Sanitize error output for inclusion in a mini-replan directive.

    Truncates to MAX_DIRECTIVE_ERROR_LENGTH characters and removes newlines
    to prevent log injection. Delegates to failure_classifier.sanitize_error_message
    if available, otherwise implements inline.

    Args:
        error_output: Raw error string to sanitize. May be None.

    Returns:
        Sanitized error string, empty string if input is None.
    """
    if error_output is None:
        return ""

    if _sanitize_from_fc is not None:
        # Use the shared sanitizer, then apply our length limit
        sanitized = _sanitize_from_fc(error_output)
    else:
        # Inline sanitization: remove newlines
        sanitized = error_output.replace("\n", " ").replace("\r", " ")

    # Truncate to max length
    if len(sanitized) > MAX_DIRECTIVE_ERROR_LENGTH:
        sanitized = sanitized[:MAX_DIRECTIVE_ERROR_LENGTH] + "..."

    return sanitized


def format_mini_replan_directive(
    signal: BlockingSignal,
    *,
    cycle: int,
) -> str:
    """Format a mini-replan directive for the implementer agent.

    Produces a structured directive that tells the implementer what went wrong,
    what corrective action to take, and how many cycles remain.

    Args:
        signal: The classified blocking signal.
        cycle: Current mini-replan cycle number (1-based, max MAX_MINI_REPLAN_CYCLES).

    Returns:
        Formatted directive string for injection into the implementer prompt.
    """
    lines = [
        f"[MINI-REPLAN cycle {cycle}/{MAX_MINI_REPLAN_CYCLES}]",
        f"Error: {signal.error_name}",
    ]

    if signal.error_detail:
        lines.append(f"Detail: {signal.error_detail}")

    lines.append(f"Suggested action: {signal.suggested_action}")
    lines.append("")
    lines.append(
        "FORBIDDEN: Do not retry the same command without a corrective action. "
        "Apply the suggested fix or an alternative approach before re-running."
    )

    if cycle >= MAX_MINI_REPLAN_CYCLES:
        lines.append("")
        lines.append(
            "WARNING: This is the final mini-replan cycle. If this attempt does not "
            "resolve the error, escalate to the coordinator for remediation."
        )

    return "\n".join(lines)
