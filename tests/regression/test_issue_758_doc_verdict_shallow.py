"""Regression tests for Issue #758: doc-master output too brief.

Validates that validate_doc_verdict correctly detects shallow output
(below MIN_DOC_VERDICT_WORDS threshold) via the word_count and is_shallow fields.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure lib is importable (regression -> tests -> repo root = parents[2])
LIB_PATH = Path(__file__).resolve().parents[2] / "plugins" / "autonomous-dev" / "lib"
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from doc_verdict_validator import (
    MIN_DOC_VERDICT_WORDS,
    DocVerdictResult,
    validate_doc_verdict,
)


class TestIssue758DocVerdictShallow:
    """Regression tests for shallow doc-master output detection."""

    def test_short_output_is_shallow(self):
        """54-word output with valid verdict is flagged as shallow.

        Reproduces the bug: doc-master produced only 54 words in a real
        invocation, which was too brief to be useful.
        """
        # "DOC-DRIFT-VERDICT: PASS" counts as 2 words, so 52 filler + 2 verdict = 54
        filler = " ".join(f"word{i}" for i in range(52))
        output = f"{filler}\nDOC-DRIFT-VERDICT: PASS"
        result = validate_doc_verdict(output)

        assert result.is_shallow is True
        assert result.word_count == 54
        assert result.found is True
        assert result.verdict == "PASS"

    def test_adequate_output_not_shallow(self):
        """150-word output with valid verdict is not flagged as shallow."""
        # 148 filler + 2 verdict = 150
        filler = " ".join(f"word{i}" for i in range(148))
        output = f"{filler}\nDOC-DRIFT-VERDICT: PASS"
        result = validate_doc_verdict(output)

        assert result.is_shallow is False
        assert result.word_count == 150
        assert result.found is True
        assert result.verdict == "PASS"

    def test_empty_output_is_shallow(self):
        """Empty string produces is_shallow=True with word_count=0."""
        result = validate_doc_verdict("")

        assert result.is_shallow is True
        assert result.word_count == 0
        assert result.found is False

    def test_exactly_100_words_not_shallow(self):
        """Boundary: exactly 100 words is not shallow (>= threshold)."""
        # 98 filler + 2 verdict = 100
        filler = " ".join(f"word{i}" for i in range(98))
        output = f"{filler}\nDOC-DRIFT-VERDICT: PASS"
        result = validate_doc_verdict(output)

        assert result.is_shallow is False
        assert result.word_count == 100

    def test_99_words_is_shallow(self):
        """Boundary: 99 words is shallow (< threshold)."""
        # 97 filler + 2 verdict = 99
        filler = " ".join(f"word{i}" for i in range(97))
        output = f"{filler}\nDOC-DRIFT-VERDICT: PASS"
        result = validate_doc_verdict(output)

        assert result.is_shallow is True
        assert result.word_count == 99

    def test_min_doc_verdict_words_constant(self):
        """MIN_DOC_VERDICT_WORDS is set to 100."""
        assert MIN_DOC_VERDICT_WORDS == 100
