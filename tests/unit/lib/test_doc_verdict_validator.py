"""Tests for doc_verdict_validator module (Issue #602).

Validates the reusable DOC-DRIFT-VERDICT parser that the coordinator
uses to check doc-master output.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure lib is importable
LIB_PATH = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from doc_verdict_validator import DocVerdictResult, validate_doc_verdict


class TestDocVerdictValidator:
    """Tests for validate_doc_verdict function."""

    def test_pass_verdict_found(self):
        """Output ending with DOC-DRIFT-VERDICT: PASS is correctly parsed."""
        output = (
            "Checked 5 docs, fixed 2.\n"
            "docs-checked: 5\n"
            "docs-fixed: 2\n"
            "DOC-DRIFT-VERDICT: PASS"
        )
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "PASS"
        assert result.finding_count == 0
        assert result.raw_line == "DOC-DRIFT-VERDICT: PASS"
        assert result.position_warning == ""

    def test_fail_verdict_with_count(self):
        """Output ending with DOC-DRIFT-VERDICT: FAIL(3) is correctly parsed."""
        output = (
            "Found 3 unfixable findings.\n"
            "DOC-DRIFT-VERDICT: FAIL(3)"
        )
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "FAIL"
        assert result.finding_count == 3
        assert result.raw_line == "DOC-DRIFT-VERDICT: FAIL(3)"
        assert result.position_warning == ""

    def test_fail_verdict_without_count(self):
        """DOC-DRIFT-VERDICT: FAIL (no parentheses) is treated as FAIL with count=-1."""
        output = "DOC-DRIFT-VERDICT: FAIL"
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "FAIL"
        assert result.finding_count == -1
        assert result.raw_line == "DOC-DRIFT-VERDICT: FAIL"

    def test_verdict_not_found(self):
        """Output with no verdict line returns found=False."""
        output = (
            "Checked 5 docs, fixed 2.\n"
            "All good, nothing to report.\n"
        )
        result = validate_doc_verdict(output)
        assert result.found is False
        assert result.verdict == ""
        assert result.finding_count == 0
        assert result.raw_line == ""

    def test_verdict_not_last_line(self):
        """Verdict exists but is not the last non-empty line sets position_warning."""
        output = (
            "DOC-DRIFT-VERDICT: PASS\n"
            "Some extra text after the verdict.\n"
        )
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "PASS"
        assert result.position_warning != ""
        assert "last" in result.position_warning.lower()

    def test_empty_output(self):
        """Empty string returns found=False."""
        result = validate_doc_verdict("")
        assert result.found is False
        assert result.verdict == ""
        assert result.finding_count == 0

    def test_whitespace_only_output(self):
        """Whitespace-only output returns found=False."""
        result = validate_doc_verdict("   \n\n  \t  \n")
        assert result.found is False
        assert result.verdict == ""

    def test_verdict_in_code_block(self):
        """Verdict inside a markdown code block is still found."""
        output = (
            "```\n"
            "DOC-DRIFT-VERDICT: PASS\n"
            "```"
        )
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "PASS"
        # Position warning because ``` is the last non-empty line
        assert result.position_warning != ""

    def test_multiple_verdicts(self):
        """When multiple verdict lines exist, the last one is used."""
        output = (
            "DOC-DRIFT-VERDICT: FAIL(2)\n"
            "After fixing, re-checked:\n"
            "DOC-DRIFT-VERDICT: PASS"
        )
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "PASS"
        assert result.finding_count == 0
        assert result.position_warning == ""

    def test_fail_zero_is_pass(self):
        """FAIL(0) is treated as PASS since zero findings means passing."""
        output = "DOC-DRIFT-VERDICT: FAIL(0)"
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "PASS"
        assert result.finding_count == 0

    def test_fail_non_numeric(self):
        """FAIL(abc) is treated as FAIL with finding_count=-1 (parse error)."""
        output = "DOC-DRIFT-VERDICT: FAIL(abc)"
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "FAIL"
        assert result.finding_count == -1

    def test_ansi_escape_codes(self):
        """Verdict with ANSI escape codes is stripped and parsed correctly."""
        output = "\x1b[32mDOC-DRIFT-VERDICT: PASS\x1b[0m"
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "PASS"
        assert result.finding_count == 0

    def test_trailing_whitespace(self):
        """Verdict with trailing spaces/newlines is handled correctly."""
        output = "DOC-DRIFT-VERDICT: PASS   \n\n\n"
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "PASS"
        assert result.position_warning == ""

    def test_verdict_with_leading_spaces_on_line(self):
        """Verdict line with leading spaces is still matched after strip."""
        output = "  DOC-DRIFT-VERDICT: FAIL(1)  "
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "FAIL"
        assert result.finding_count == 1

    def test_large_finding_count(self):
        """Large finding count is parsed correctly."""
        output = "DOC-DRIFT-VERDICT: FAIL(42)"
        result = validate_doc_verdict(output)
        assert result.found is True
        assert result.verdict == "FAIL"
        assert result.finding_count == 42
