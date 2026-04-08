"""Tests for Issue #726: implementer minimum prompt violation.

Bug (#726): In implement-batch.md, the implementer example template had only
~34-45 words (well below the 80-word minimum set in the HARD GATE: Prompt
Integrity section). In implement-fix.md STEP F3, the implementer template
was ~75 words, also at risk of falling below the minimum.

Fix:
1. Expanded implement-batch.md implementer example template to >= 90 words by
   adding no-stubs requirement, test-alongside-code requirement, hard gate
   reminder, and output format requirement.
2. Expanded implement-fix.md STEP F3 template to >= 90 words by adding an
   output format line and a prompt word count validation note.

Validates:
1. implement-batch.md implementer prompt template block exists
2. implement-batch.md implementer template has >= 80 words (brackets stripped)
3. implement-batch.md implementer template contains no-stubs requirement
4. implement-batch.md implementer template contains test-alongside-code requirement
5. implement-fix.md STEP F3 implementer prompt block exists
6. implement-fix.md STEP F3 template has >= 80 words (brackets stripped)
7. implement-fix.md STEP F3 template contains hard gate language
8. implement-batch.md lists implementer in the 80-word requirement (regression guard)
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BATCH_CMD_PATH = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"
FIX_CMD_PATH = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-fix.md"

MIN_CRITICAL_AGENT_PROMPT_WORDS = 80


def _extract_implementer_prompt_block(content: str) -> str | None:
    """Extract the implementer prompt template text from a file.

    Finds the first implementer prompt block and returns the template text
    excluding placeholder markers (content inside square brackets).

    Args:
        content: Full file content.

    Returns:
        Template text with bracket placeholders removed, or None if not found.
    """
    prompt_blocks = re.findall(
        r'subagent_type:\s*"implementer".*?prompt:\s*"(.*?)"',
        content,
        re.DOTALL,
    )
    if not prompt_blocks:
        return None
    # Remove placeholder markers: [any text inside brackets]
    template_text = re.sub(r"\[.*?\]", "", prompt_blocks[0])
    return template_text


def _count_words(text: str) -> int:
    """Count non-empty words in text.

    Args:
        text: Input text.

    Returns:
        Number of words.
    """
    return len([w for w in text.split() if w.strip()])


class TestImplementerBatchTemplateMinimum:
    """Regression test: Issue #726 — implementer prompt in implement-batch.md must have >= 80 words.

    Bug: The implementer example template in implement-batch.md had only ~34-45
    words. The 80-word minimum from the HARD GATE section was not being met by
    the example template itself.
    Fix: Expanded template with no-stubs requirement, test requirement, hard
    gate reminder, and output format line.
    """

    @pytest.fixture
    def batch_content(self) -> str:
        """Read implement-batch.md content."""
        assert BATCH_CMD_PATH.exists(), f"implement-batch.md not found at {BATCH_CMD_PATH}"
        return BATCH_CMD_PATH.read_text(encoding="utf-8")

    def test_implementer_prompt_block_exists_in_batch_template(self, batch_content: str) -> None:
        """implement-batch.md must have an implementer prompt template block.

        The example agent invocation section must contain a structured prompt
        block for the implementer agent.
        """
        block = _extract_implementer_prompt_block(batch_content)
        assert block is not None, (
            "implement-batch.md does not contain an implementer prompt template block. "
            "Issue #726: the example invocation section must have a structured template."
        )

    def test_implementer_batch_template_meets_minimum(self, batch_content: str) -> None:
        """Implementer prompt template in implement-batch.md must have >= 80 words.

        This is the regression test for Issue #726. Without the fix, the template
        had only ~34-45 words of template text. With the fix, it has >= 80.
        """
        block = _extract_implementer_prompt_block(batch_content)
        assert block is not None, "No implementer prompt template block found in implement-batch.md."

        word_count = _count_words(block)
        assert word_count >= MIN_CRITICAL_AGENT_PROMPT_WORDS, (
            f"Implementer prompt template in implement-batch.md has only {word_count} words "
            f"(minimum: {MIN_CRITICAL_AGENT_PROMPT_WORDS}). "
            f"Issue #726: the template must be self-sufficient (>= 80 words)."
        )

    def test_implementer_batch_template_contains_no_stubs_requirement(self, batch_content: str) -> None:
        """Implementer batch template must explicitly forbid stubs and NotImplementedError.

        Issue #726 fix adds a no-stubs requirement to ensure the implementer
        writes working code, not placeholders.
        """
        block = _extract_implementer_prompt_block(batch_content)
        assert block is not None, "No implementer prompt template block found in implement-batch.md."

        block_lower = block.lower()
        has_no_stubs = "no stub" in block_lower or "no notimplementederror" in block_lower or "notimplementederror" in block_lower
        assert has_no_stubs, (
            "Implementer batch template does not contain a no-stubs requirement. "
            "Issue #726: the template must forbid stubs and NotImplementedError placeholders."
        )

    def test_implementer_batch_template_contains_test_requirement(self, batch_content: str) -> None:
        """Implementer batch template must require writing tests alongside implementation.

        Issue #726 fix adds a test-alongside-code requirement to enforce TDD
        behavior from the implementer agent.
        """
        block = _extract_implementer_prompt_block(batch_content)
        assert block is not None, "No implementer prompt template block found in implement-batch.md."

        block_lower = block.lower()
        has_test_requirement = "unit test" in block_lower or "write test" in block_lower or "test-driven" in block_lower
        assert has_test_requirement, (
            "Implementer batch template does not contain a test-alongside-code requirement. "
            "Issue #726: the template must require writing tests alongside implementation."
        )


class TestImplementerFixTemplateMinimum:
    """Regression test: Issue #726 — implementer prompt in implement-fix.md STEP F3 must have >= 80 words.

    Bug: The STEP F3 implementer template in implement-fix.md was ~75 words,
    close to but at risk of the 80-word minimum.
    Fix: Expanded template with output format requirement and prompt word count
    validation note.
    """

    @pytest.fixture
    def fix_content(self) -> str:
        """Read implement-fix.md content."""
        assert FIX_CMD_PATH.exists(), f"implement-fix.md not found at {FIX_CMD_PATH}"
        return FIX_CMD_PATH.read_text(encoding="utf-8")

    def test_implementer_fix_prompt_block_exists(self, fix_content: str) -> None:
        """implement-fix.md must have an implementer prompt template block in STEP F3.

        STEP F3 must contain a structured implementer prompt block with
        clear instructions for the fix-mode implementation task.
        """
        block = _extract_implementer_prompt_block(fix_content)
        assert block is not None, (
            "implement-fix.md does not contain an implementer prompt template block. "
            "Issue #726: STEP F3 must have a structured implementer prompt template."
        )

    def test_implementer_fix_template_meets_minimum(self, fix_content: str) -> None:
        """Implementer prompt template in implement-fix.md must have >= 80 words.

        This is the regression test for Issue #726. The STEP F3 template must
        be self-sufficient with >= 80 words of template text excluding
        placeholder markers.
        """
        block = _extract_implementer_prompt_block(fix_content)
        assert block is not None, "No implementer prompt template block found in implement-fix.md."

        word_count = _count_words(block)
        assert word_count >= MIN_CRITICAL_AGENT_PROMPT_WORDS, (
            f"Implementer prompt template in implement-fix.md has only {word_count} words "
            f"(minimum: {MIN_CRITICAL_AGENT_PROMPT_WORDS}). "
            f"Issue #726: STEP F3 template must be self-sufficient (>= 80 words)."
        )

    def test_implementer_fix_template_contains_hard_gate(self, fix_content: str) -> None:
        """Implementer fix template must contain HARD GATE language for 0 failures.

        Issue #726 fix requires explicit hard gate language to prevent
        implementers from returning with failing tests.
        """
        block = _extract_implementer_prompt_block(fix_content)
        assert block is not None, "No implementer prompt template block found in implement-fix.md."

        block_upper = block.upper()
        has_hard_gate = "HARD GATE" in block_upper or "0 FAILURES" in block_upper or "ZERO FAILURES" in block_upper
        # Also accept the pattern "0 failures" in lower case
        has_zero_failures = "0 failures" in block.lower()
        assert has_hard_gate or has_zero_failures, (
            "Implementer fix template does not contain HARD GATE or 0-failures language. "
            "Issue #726: STEP F3 template must enforce that all tests pass."
        )


class TestImplementerListedInBatchRequirement:
    """Regression guard: implement-batch.md must list implementer in 80-word requirement.

    Issue #725 added doc-master and others to the list. Issue #726 ensures
    implementer is listed (it already was, but this test guards against removal).
    """

    @pytest.fixture
    def batch_content(self) -> str:
        """Read implement-batch.md content."""
        assert BATCH_CMD_PATH.exists(), f"implement-batch.md not found at {BATCH_CMD_PATH}"
        return BATCH_CMD_PATH.read_text(encoding="utf-8")

    def test_implementer_listed_in_80_word_requirement(self, batch_content: str) -> None:
        """implement-batch.md must list implementer in the 80-word minimum requirement.

        This is a regression guard. The 80-word minimum requirement line
        must include implementer so prompt compression is blocked.
        """
        lines_with_80_words = [
            line for line in batch_content.splitlines()
            if "80 words" in line.lower() and "must receive" in line.lower()
        ]
        assert lines_with_80_words, (
            "implement-batch.md does not contain a line requiring agents to receive 80 words. "
            "Issue #726: The 80-word minimum requirement line must exist."
        )

        requirement_line = " ".join(lines_with_80_words)
        assert "implementer" in requirement_line, (
            f"The 80-word minimum requirement line does not include 'implementer'. "
            f"Found: {lines_with_80_words[0]!r}. "
            f"Issue #726: implementer must be listed in the 80-word minimum requirement."
        )
