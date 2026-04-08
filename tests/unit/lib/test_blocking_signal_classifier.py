"""Tests for blocking_signal_classifier module.

Issue #730: Adaptive replanning when implementer encounters blocking information.
"""

import sys
from pathlib import Path

# Add lib to path so we can import the module directly
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"))

from blocking_signal_classifier import (
    MAX_DIRECTIVE_ERROR_LENGTH,
    MAX_MINI_REPLAN_CYCLES,
    RECOVERABLE_SIGNAL_PATTERNS,
    BlockingSignal,
    BlockingSignalType,
    classify_blocking_signal,
    format_mini_replan_directive,
    sanitize_error_for_directive,
)


class TestClassifyBlockingSignal:
    """Tests for classify_blocking_signal function."""

    def test_module_not_found_error_is_recoverable(self) -> None:
        error = "ModuleNotFoundError: No module named 'requests'"
        result = classify_blocking_signal(error)
        assert result.signal_type == BlockingSignalType.RECOVERABLE
        assert result.error_name == "ModuleNotFoundError"
        assert "requests" in result.error_detail
        assert result.suggested_action == "Install missing module or use alternative"

    def test_file_not_found_error_is_recoverable(self) -> None:
        error = "FileNotFoundError: No such file or directory: '/tmp/missing.txt'"
        result = classify_blocking_signal(error)
        assert result.signal_type == BlockingSignalType.RECOVERABLE
        assert result.error_name == "FileNotFoundError"
        assert result.suggested_action == "Verify file path or create missing file"

    def test_import_error_is_recoverable(self) -> None:
        error = "ImportError: cannot import name 'foo' from 'bar'"
        result = classify_blocking_signal(error)
        assert result.signal_type == BlockingSignalType.RECOVERABLE
        assert result.error_name == "ImportError"
        assert "cannot import name" in result.error_detail
        assert result.suggested_action == "Fix import path or install dependency"

    def test_attribute_error_is_recoverable(self) -> None:
        error = "AttributeError: 'NoneType' object has no attribute 'split'"
        result = classify_blocking_signal(error)
        assert result.signal_type == BlockingSignalType.RECOVERABLE
        assert result.error_name == "AttributeError"
        assert "NoneType" in result.error_detail
        assert result.suggested_action == "Check API compatibility or use correct attribute"

    def test_command_not_found_is_recoverable(self) -> None:
        error = "bash: mycli: command not found"
        result = classify_blocking_signal(error)
        assert result.signal_type == BlockingSignalType.RECOVERABLE
        assert result.error_name == "CommandNotFound"
        assert result.suggested_action == "Install missing CLI tool or use alternative"

    def test_exit_code_127_is_recoverable(self) -> None:
        error = "Process exited with exit code 127"
        result = classify_blocking_signal(error)
        assert result.signal_type == BlockingSignalType.RECOVERABLE
        assert result.error_name == "CommandNotFound"

    def test_syntax_error_is_structural(self) -> None:
        error = "SyntaxError: invalid syntax (file.py, line 42)"
        result = classify_blocking_signal(error)
        assert result.signal_type == BlockingSignalType.STRUCTURAL
        assert "SyntaxError" in result.error_name
        assert result.suggested_action == "Fix syntax before retrying"

    def test_unrecognized_error_is_not_blocking(self) -> None:
        error = "Some random warning: everything is fine"
        result = classify_blocking_signal(error)
        assert result.signal_type == BlockingSignalType.NOT_BLOCKING
        assert result.error_name == ""

    def test_empty_input_is_not_blocking(self) -> None:
        result = classify_blocking_signal("")
        assert result.signal_type == BlockingSignalType.NOT_BLOCKING
        assert result.error_name == ""
        assert result.error_detail == ""
        assert result.suggested_action == ""

    def test_none_like_whitespace_is_not_blocking(self) -> None:
        result = classify_blocking_signal("   \n\t  ")
        assert result.signal_type == BlockingSignalType.NOT_BLOCKING


class TestFormatMiniReplanDirective:
    """Tests for format_mini_replan_directive function."""

    def _make_signal(self) -> BlockingSignal:
        return BlockingSignal(
            signal_type=BlockingSignalType.RECOVERABLE,
            error_name="ModuleNotFoundError",
            error_detail="No module named 'requests'",
            suggested_action="Install missing module or use alternative",
        )

    def test_directive_contains_cycle_number(self) -> None:
        directive = format_mini_replan_directive(self._make_signal(), cycle=1)
        assert "[MINI-REPLAN cycle 1/2]" in directive

    def test_directive_contains_error_name(self) -> None:
        directive = format_mini_replan_directive(self._make_signal(), cycle=1)
        assert "ModuleNotFoundError" in directive

    def test_directive_contains_suggested_action(self) -> None:
        directive = format_mini_replan_directive(self._make_signal(), cycle=1)
        assert "Install missing module or use alternative" in directive

    def test_directive_contains_forbidden_text(self) -> None:
        directive = format_mini_replan_directive(self._make_signal(), cycle=1)
        assert "FORBIDDEN" in directive
        assert "corrective action" in directive.lower()

    def test_directive_cycle_2_contains_escalation_warning(self) -> None:
        directive = format_mini_replan_directive(self._make_signal(), cycle=2)
        assert "WARNING" in directive
        assert "escalate" in directive.lower()

    def test_directive_cycle_1_no_escalation_warning(self) -> None:
        directive = format_mini_replan_directive(self._make_signal(), cycle=1)
        assert "final mini-replan cycle" not in directive


class TestSanitizeErrorForDirective:
    """Tests for sanitize_error_for_directive function."""

    def test_long_error_truncated(self) -> None:
        long_error = "x" * 1000
        result = sanitize_error_for_directive(long_error)
        assert len(result) <= MAX_DIRECTIVE_ERROR_LENGTH + 3  # +3 for "..."
        assert result.endswith("...")

    def test_newlines_removed(self) -> None:
        error = "line1\nline2\nline3"
        result = sanitize_error_for_directive(error)
        assert "\n" not in result

    def test_none_returns_empty(self) -> None:
        result = sanitize_error_for_directive(None)
        assert result == ""

    def test_normal_error_unchanged(self) -> None:
        error = "ModuleNotFoundError: No module named 'foo'"
        result = sanitize_error_for_directive(error)
        assert "ModuleNotFoundError" in result
        assert "foo" in result


class TestConstants:
    """Tests for module constants."""

    def test_max_mini_replan_cycles_is_2(self) -> None:
        assert MAX_MINI_REPLAN_CYCLES == 2

    def test_recoverable_patterns_count(self) -> None:
        assert len(RECOVERABLE_SIGNAL_PATTERNS) == 5
