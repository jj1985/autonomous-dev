"""Spec validation tests for Issue #812: Tightened prompt shrinkage thresholds.

Tests observable behavior against acceptance criteria ONLY.
Each test maps to a specific acceptance criterion from the issue.

Acceptance criteria:
1. A prompt with exactly 25% shrinkage from baseline MUST be blocked
2. A prompt with exactly 20% shrinkage from baseline MUST be blocked at hook level
3. The exact scenario from issue #812 (491->357-367 words, 25-27% shrinkage) MUST trigger a block
4. Cumulative drift of 15% or more across batch issues MUST trigger a block
5. Shrinkage below 20% (e.g., 19%) MUST still pass validation
6. Reinvocation contexts (remediation, re-review) MUST still get relaxed thresholds
7. All existing prompt integrity tests pass (verified by running existing suite)
8. implement-batch.md documentation reflects updated threshold values
9. A regression test file exists covering boundary conditions
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Add lib to path so we can import prompt_integrity
_lib_path = str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib")
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)

import prompt_integrity  # noqa: E402
from prompt_integrity import (  # noqa: E402
    MAX_CUMULATIVE_SHRINKAGE,
    get_cumulative_shrinkage,
    record_batch_observation,
    validate_prompt_word_count,
)


class TestSpecIssue812ShrinkageThresholds:
    """Spec validation for Issue #812 acceptance criteria."""

    # -- Criterion 1: 25% shrinkage MUST be blocked --

    def test_spec_812_1_25pct_shrinkage_blocked(self) -> None:
        """A prompt with exactly 25% shrinkage from baseline MUST be blocked."""
        # 400-word baseline, 300-word current = exactly 25.0% shrinkage
        prompt = " ".join(["word"] * 300)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=400, max_shrinkage=0.20
        )
        assert result.passed is False, (
            f"25% shrinkage must be blocked. Got passed={result.passed}, "
            f"shrinkage={result.shrinkage_pct:.1f}%"
        )

    # -- Criterion 2: 20% shrinkage MUST be blocked at hook level --

    def test_spec_812_2_20pct_shrinkage_blocked(self) -> None:
        """A prompt with exactly 20% shrinkage from baseline MUST be blocked.

        The spec says the threshold changed from 25% to 20% and the comparison
        changed from > to >=. So exactly 20% must be blocked.
        """
        # 500-word baseline, 400-word current = exactly 20.0% shrinkage
        prompt = " ".join(["word"] * 400)
        result = validate_prompt_word_count(
            "reviewer", prompt, baseline_word_count=500, max_shrinkage=0.20
        )
        assert result.passed is False, (
            f"Exactly 20% shrinkage must be blocked (>= boundary). "
            f"Got passed={result.passed}, shrinkage={result.shrinkage_pct:.1f}%"
        )

    # -- Criterion 3: Exact issue #812 scenario (491->357-367 words) --

    def test_spec_812_3a_491_to_357_words_blocked(self) -> None:
        """The exact scenario: 491->357 words (27.3% shrinkage) MUST trigger a block."""
        prompt = " ".join(["word"] * 357)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=491, max_shrinkage=0.20
        )
        assert result.passed is False, (
            f"491->357 words (27.3% shrinkage) must be blocked. "
            f"Got passed={result.passed}"
        )

    def test_spec_812_3b_491_to_367_words_blocked(self) -> None:
        """The exact scenario: 491->367 words (25.3% shrinkage) MUST trigger a block."""
        prompt = " ".join(["word"] * 367)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=491, max_shrinkage=0.20
        )
        assert result.passed is False, (
            f"491->367 words (25.3% shrinkage) must be blocked. "
            f"Got passed={result.passed}"
        )

    # -- Criterion 4: Cumulative drift of 30% or more MUST trigger a block (Issue #870) --

    def test_spec_812_4_cumulative_30pct_drift_blocked(self, tmp_path: Path) -> None:
        """Cumulative drift of 30% or more across batch issues MUST trigger a block.

        MAX_CUMULATIVE_SHRINKAGE raised to 0.30 in Issue #870 (from 0.15 in #812).
        """
        # Record observations: 200 words first, 140 words later = exactly 30%
        record_batch_observation("implementer", 1, 200, state_dir=tmp_path)
        record_batch_observation("implementer", 5, 140, state_dir=tmp_path)

        cumulative = get_cumulative_shrinkage("implementer", state_dir=tmp_path)
        assert cumulative is not None
        assert cumulative >= MAX_CUMULATIVE_SHRINKAGE * 100, (
            f"30% cumulative drift must meet or exceed threshold. "
            f"Cumulative={cumulative}%, threshold={MAX_CUMULATIVE_SHRINKAGE * 100}%"
        )

    def test_spec_812_4b_max_cumulative_shrinkage_is_030(self) -> None:
        """MAX_CUMULATIVE_SHRINKAGE constant must be 0.30 (30%) — raised in Issue #870."""
        assert MAX_CUMULATIVE_SHRINKAGE == 0.30, (
            f"Expected MAX_CUMULATIVE_SHRINKAGE=0.30, got {MAX_CUMULATIVE_SHRINKAGE}"
        )

    # -- Criterion 5: Shrinkage below 20% MUST still pass --

    def test_spec_812_5_19pct_shrinkage_passes(self) -> None:
        """Shrinkage below 20% (e.g., 19%) MUST still pass validation."""
        # 100-word baseline, 81-word current = 19.0% shrinkage
        prompt = " ".join(["word"] * 81)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=100, max_shrinkage=0.20
        )
        assert result.passed is True, (
            f"19% shrinkage must pass the 20% threshold. "
            f"Got passed={result.passed}, shrinkage={result.shrinkage_pct:.1f}%"
        )

    # -- Criterion 6: Reinvocation contexts get relaxed thresholds --

    def test_spec_812_6a_remediation_context_relaxed(self) -> None:
        """Reinvocation context 'remediation' MUST get relaxed thresholds.

        With max_shrinkage=0.20 and remediation context, the effective threshold
        should be relaxed so that 20% shrinkage passes.
        """
        prompt = " ".join(["word"] * 80)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=100,
            max_shrinkage=0.20, invocation_context="remediation",
        )
        assert result.passed is True, (
            f"Remediation context must relax threshold, allowing 20% shrinkage. "
            f"Got passed={result.passed}, shrinkage={result.shrinkage_pct:.1f}%"
        )

    def test_spec_812_6b_re_review_context_relaxed(self) -> None:
        """Reinvocation context 're-review' MUST get relaxed thresholds."""
        prompt = " ".join(["word"] * 80)
        result = validate_prompt_word_count(
            "reviewer", prompt, baseline_word_count=100,
            max_shrinkage=0.20, invocation_context="re-review",
        )
        assert result.passed is True, (
            f"Re-review context must relax threshold, allowing 20% shrinkage. "
            f"Got passed={result.passed}, shrinkage={result.shrinkage_pct:.1f}%"
        )

    # -- Criterion 8: Documentation reflects updated values --

    def test_spec_812_8_doc_reflects_20pct_threshold(self) -> None:
        """implement-batch.md documentation MUST reflect the updated 20% threshold."""
        doc_path = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"
        )
        assert doc_path.exists(), f"implement-batch.md not found at {doc_path}"
        content = doc_path.read_text(encoding="utf-8")
        # The doc should mention 20% shrinkage detection
        assert "20%" in content, (
            "implement-batch.md must mention 20% threshold for shrinkage detection"
        )

    # -- Criterion 9: Regression test file exists --

    def test_spec_812_9_regression_test_file_exists(self) -> None:
        """A regression test file covering boundary conditions MUST exist."""
        regression_file = (
            REPO_ROOT / "tests" / "regression" / "test_issue812_prompt_shrinkage_boundary.py"
        )
        assert regression_file.exists(), (
            f"Regression test file not found at {regression_file}"
        )
        content = regression_file.read_text(encoding="utf-8")
        # Should contain test classes/functions
        assert "def test_" in content, (
            "Regression test file must contain test functions"
        )
