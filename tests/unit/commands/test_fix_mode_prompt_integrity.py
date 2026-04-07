"""Tests for Issue #687: Fix mode reviewer/security-auditor prompt minimum word count.

Bug: In --fix mode, reviewer and security-auditor received prompts below the
80-word minimum. The STEP F4 reviewer prompt template in implement-fix.md was
too short (~20 words without implementer output). When the coordinator truncated
or summarized implementer output, the final prompt fell below 80 words.

Validates:
1. STEP F4 reviewer prompt template contains >= 80 words of template text
   (excluding placeholder markers like [paste ... here])
2. STEP F4 security-auditor prompt template contains >= 80 words of template text
3. Verbatim passing requirement is documented in STEP F4
4. Prompt integrity gate instructions exist in STEP F4
5. FORBIDDEN list covers summarization and minimum word count violations
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FIX_CMD_PATH = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-fix.md"

# Minimum word count for critical agent prompts, matching prompt_integrity.py
MIN_CRITICAL_AGENT_PROMPT_WORDS = 80


def _extract_prompt_template_words(content: str, agent_type: str) -> list[str]:
    """Extract template words from a prompt block, excluding placeholder markers.

    Finds the prompt block for the given agent_type and strips out content inside
    square brackets (e.g., [paste implementer output]) which are placeholders
    that the coordinator replaces with dynamic content.

    Args:
        content: Full file content of implement-fix.md.
        agent_type: Agent type string (e.g., 'reviewer', 'security-auditor').

    Returns:
        List of words in the template text excluding placeholder markers.
    """
    # Find prompt blocks: content between ```\n and \n```
    # Look for the agent-specific prompt block
    prompt_blocks = re.findall(
        r'subagent_type:\s*"' + re.escape(agent_type) + r'".*?prompt:\s*"(.*?)"',
        content,
        re.DOTALL,
    )
    if not prompt_blocks:
        return []

    template_text = prompt_blocks[0]

    # Remove placeholder markers: [any text inside brackets]
    template_text = re.sub(r"\[.*?\]", "", template_text)

    # Split into words, filtering empty strings
    words = [w for w in template_text.split() if w.strip()]
    return words


class TestFixModeReviewerPromptMinimum:
    """Regression test: STEP F4 reviewer prompt template must have >= 80 words.

    Bug (Issue #687): Reviewer received only 78 words because the template
    itself was ~20 words and coordinator summarized the implementer output.
    Fix: Expanded template to >= 80 words of template text alone.
    """

    @pytest.fixture
    def fix_content(self) -> str:
        """Read implement-fix.md content."""
        assert FIX_CMD_PATH.exists(), f"implement-fix.md not found at {FIX_CMD_PATH}"
        return FIX_CMD_PATH.read_text(encoding="utf-8")

    def test_reviewer_prompt_template_meets_minimum(self, fix_content: str) -> None:
        """Reviewer prompt template must contain >= 80 words excluding placeholders.

        This is the regression test for Issue #687. Without the fix, the template
        had only ~20 words of template text. With the fix, it has >= 80.
        """
        words = _extract_prompt_template_words(fix_content, "reviewer")
        word_count = len(words)

        assert word_count >= MIN_CRITICAL_AGENT_PROMPT_WORDS, (
            f"Reviewer prompt template has only {word_count} words "
            f"(minimum: {MIN_CRITICAL_AGENT_PROMPT_WORDS}). "
            f"This was the root cause of Issue #687 — the template must be "
            f"self-sufficient (>= 80 words) even without implementer output."
        )

    def test_security_auditor_prompt_template_meets_minimum(self, fix_content: str) -> None:
        """Security-auditor prompt template must contain >= 80 words excluding placeholders.

        Issue #687 also affected security-auditor (52 words). The template must
        be self-sufficient.
        """
        words = _extract_prompt_template_words(fix_content, "security-auditor")
        word_count = len(words)

        assert word_count >= MIN_CRITICAL_AGENT_PROMPT_WORDS, (
            f"Security-auditor prompt template has only {word_count} words "
            f"(minimum: {MIN_CRITICAL_AGENT_PROMPT_WORDS}). "
            f"This was part of Issue #687 — the template must be "
            f"self-sufficient (>= 80 words) even without implementer output."
        )


class TestFixModeVerbatimPassingRequirement:
    """Validate STEP F4 requires verbatim passing of implementer output."""

    @pytest.fixture
    def fix_content(self) -> str:
        return FIX_CMD_PATH.read_text(encoding="utf-8")

    def test_verbatim_requirement_documented(self, fix_content: str) -> None:
        """STEP F4 must explicitly require verbatim passing of implementer output."""
        content_lower = fix_content.lower()
        assert "verbatim" in content_lower, (
            "STEP F4 must contain the word 'verbatim' to enforce full "
            "implementer output passing (Issue #687 fix)."
        )

    def test_no_summarize_forbidden(self, fix_content: str) -> None:
        """STEP F4 must forbid summarizing implementer output."""
        content_lower = fix_content.lower()
        assert "do not summarize" in content_lower or "do not summarise" in content_lower, (
            "STEP F4 must explicitly forbid summarizing implementer output "
            "(root cause of Issue #687)."
        )


class TestFixModePromptIntegrityGate:
    """Validate STEP F4 includes prompt integrity validation instructions."""

    @pytest.fixture
    def fix_content(self) -> str:
        return FIX_CMD_PATH.read_text(encoding="utf-8")

    def test_prompt_integrity_gate_exists(self, fix_content: str) -> None:
        """STEP F4 must reference prompt word count validation."""
        assert "validate_prompt_word_count" in fix_content or "prompt word count" in fix_content.lower(), (
            "STEP F4 must include prompt integrity validation gate "
            "referencing validate_prompt_word_count or prompt word count."
        )

    def test_80_word_minimum_documented(self, fix_content: str) -> None:
        """STEP F4 must document the 80-word minimum for critical agents."""
        assert ">= 80 words" in fix_content or "80 words" in fix_content, (
            "STEP F4 must document the 80-word minimum for reviewer and "
            "security-auditor prompts."
        )

    def test_forbidden_list_covers_summarization(self, fix_content: str) -> None:
        """STEP F4 FORBIDDEN list must cover summarization violations."""
        # Find the FORBIDDEN section in STEP F4 area
        assert "FORBIDDEN" in fix_content, "STEP F4 must have a FORBIDDEN section."

        # Check that summarizing/condensing is in the forbidden list
        content_lower = fix_content.lower()
        assert "summariz" in content_lower or "condens" in content_lower, (
            "STEP F4 FORBIDDEN list must include summarizing/condensing as forbidden actions."
        )

    def test_reviewer_prompt_has_review_checklist(self, fix_content: str) -> None:
        """Reviewer prompt must include a structured review checklist."""
        assert "checklist" in fix_content.lower() or "Review checklist" in fix_content, (
            "Reviewer prompt should include a structured review checklist "
            "to ensure thorough reviews and prevent prompt being too short."
        )
