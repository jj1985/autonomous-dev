#!/usr/bin/env python3
"""
Unit Tests for Prompt Integrity Prevention (Issue #601, #603)

Tests for prompt_integrity.py functions that provide real-time prompt
compression prevention for the batch coordinator.
"""

import json
import sys
from pathlib import Path

import pytest

# Portable project root detection
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

from prompt_integrity import (
    COMPRESSION_CRITICAL_AGENTS,
    MIN_CRITICAL_AGENT_PROMPT_WORDS,
    PromptIntegrityResult,
    clear_prompt_baselines,
    get_agent_prompt_template,
    get_prompt_baseline,
    record_prompt_baseline,
    validate_prompt_word_count,
)


class TestGetAgentPromptTemplate:
    """Tests for reading agent prompt templates from disk."""

    def test_get_agent_prompt_template_success(self, tmp_path: Path) -> None:
        """Reads existing agent file and returns its content."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        agent_file = agents_dir / "reviewer.md"
        agent_file.write_text("# Reviewer Agent\n\nYou are the reviewer agent.\n")

        result = get_agent_prompt_template("reviewer", agents_dir=agents_dir)

        assert result == "# Reviewer Agent\n\nYou are the reviewer agent.\n"

    def test_get_agent_prompt_template_missing(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError for non-existent agent file."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="Agent prompt template not found"):
            get_agent_prompt_template("nonexistent-agent", agents_dir=agents_dir)


class TestValidatePromptWordCount:
    """Tests for prompt word count validation."""

    def test_validate_no_baseline(self) -> None:
        """Passes if word count > 0 and no baseline provided."""
        prompt = "This is a test prompt with several words in it for validation"
        result = validate_prompt_word_count("implementer", prompt)

        assert result.passed is True
        assert result.should_reload is False
        assert result.shrinkage_pct == 0.0
        assert result.baseline_word_count is None
        assert result.word_count == len(prompt.split())

    def test_validate_within_threshold(self) -> None:
        """15% shrinkage with 20% threshold passes."""
        # 85 words = 15% shrinkage from 100-word baseline
        prompt = " ".join(["word"] * 85)
        result = validate_prompt_word_count("implementer", prompt, baseline_word_count=100)

        assert result.passed is True
        assert result.should_reload is False
        assert result.shrinkage_pct == 15.0

    def test_validate_exceeds_threshold(self) -> None:
        """25% shrinkage with 20% threshold fails, should_reload=True."""
        # 75 words = 25% shrinkage from 100-word baseline
        prompt = " ".join(["word"] * 75)
        result = validate_prompt_word_count("implementer", prompt, baseline_word_count=100)

        assert result.passed is False
        assert result.should_reload is True
        assert result.shrinkage_pct == 25.0
        assert "25.0%" in result.reason
        assert "threshold" in result.reason

    def test_validate_critical_agent_minimum(self) -> None:
        """Security-auditor with 50 words fails minimum check."""
        prompt = " ".join(["word"] * 50)
        result = validate_prompt_word_count("security-auditor", prompt)

        assert result.passed is False
        assert result.should_reload is True
        assert "minimum" in result.reason
        assert str(MIN_CRITICAL_AGENT_PROMPT_WORDS) in result.reason

    def test_validate_non_critical_agent_no_minimum(self) -> None:
        """Non-critical agent (implementer) with 50 words passes (no minimum)."""
        prompt = " ".join(["word"] * 50)
        result = validate_prompt_word_count("implementer", prompt)

        assert result.passed is True
        assert result.should_reload is False

    def test_validate_empty_prompt(self) -> None:
        """Empty prompt always fails."""
        result = validate_prompt_word_count("implementer", "")

        assert result.passed is False
        assert result.should_reload is True
        assert result.word_count == 0
        assert "empty" in result.reason.lower()

    def test_validate_empty_prompt_with_baseline(self) -> None:
        """Empty prompt with baseline reports 100% shrinkage."""
        result = validate_prompt_word_count("implementer", "", baseline_word_count=100)

        assert result.passed is False
        assert result.shrinkage_pct == 100.0

    def test_validate_custom_max_shrinkage(self) -> None:
        """Custom max_shrinkage threshold is respected."""
        # 15% shrinkage should fail with 10% threshold
        prompt = " ".join(["word"] * 85)
        result = validate_prompt_word_count(
            "implementer", prompt, baseline_word_count=100, max_shrinkage=0.10
        )

        assert result.passed is False
        assert result.should_reload is True

    def test_validate_growth_is_ok(self) -> None:
        """Prompt growing (negative shrinkage) always passes baseline check."""
        # 120 words vs 100 baseline = -20% shrinkage (growth)
        prompt = " ".join(["word"] * 120)
        result = validate_prompt_word_count("implementer", prompt, baseline_word_count=100)

        assert result.passed is True
        assert result.should_reload is False

    def test_validate_critical_agents_set(self) -> None:
        """Verify COMPRESSION_CRITICAL_AGENTS contains expected agents."""
        assert "security-auditor" in COMPRESSION_CRITICAL_AGENTS
        assert "reviewer" in COMPRESSION_CRITICAL_AGENTS

    def test_researcher_agents_are_critical(self) -> None:
        """Regression test for Issue #666: researcher-local and researcher must be
        in COMPRESSION_CRITICAL_AGENTS so prompt compression is detected.

        Without this, a 34% shrinkage in researcher-local goes undetected.
        """
        assert "researcher-local" in COMPRESSION_CRITICAL_AGENTS
        assert "researcher" in COMPRESSION_CRITICAL_AGENTS

    def test_researcher_local_minimum_word_count_enforced(self) -> None:
        """Regression test for Issue #666: researcher-local with <80 words fails."""
        prompt = " ".join(["word"] * 50)
        result = validate_prompt_word_count("researcher-local", prompt)

        assert result.passed is False
        assert result.should_reload is True
        assert "minimum" in result.reason

    def test_researcher_minimum_word_count_enforced(self) -> None:
        """Regression test for Issue #666: researcher with <80 words fails."""
        prompt = " ".join(["word"] * 50)
        result = validate_prompt_word_count("researcher", prompt)

        assert result.passed is False
        assert result.should_reload is True
        assert "minimum" in result.reason


class TestPromptBaselinePersistence:
    """Tests for recording and retrieving prompt baselines."""

    def test_record_and_get_baseline(self, tmp_path: Path) -> None:
        """Record issue 1 baseline, retrieve it."""
        record_prompt_baseline("reviewer", issue_number=1, word_count=500, state_dir=tmp_path)
        baseline = get_prompt_baseline("reviewer", state_dir=tmp_path)

        assert baseline == 500

    def test_get_baseline_no_data(self, tmp_path: Path) -> None:
        """Returns None if no baseline exists."""
        baseline = get_prompt_baseline("reviewer", state_dir=tmp_path)

        assert baseline is None

    def test_record_multiple_issues_baseline_uses_first(self, tmp_path: Path) -> None:
        """Baseline is the word count from the first (lowest number) issue."""
        record_prompt_baseline("reviewer", issue_number=5, word_count=400, state_dir=tmp_path)
        record_prompt_baseline("reviewer", issue_number=2, word_count=500, state_dir=tmp_path)
        record_prompt_baseline("reviewer", issue_number=10, word_count=350, state_dir=tmp_path)

        baseline = get_prompt_baseline("reviewer", state_dir=tmp_path)
        assert baseline == 500  # Issue #2 has the lowest number

    def test_clear_baselines(self, tmp_path: Path) -> None:
        """Clear removes all baseline data."""
        record_prompt_baseline("reviewer", issue_number=1, word_count=500, state_dir=tmp_path)
        record_prompt_baseline("implementer", issue_number=1, word_count=300, state_dir=tmp_path)

        clear_prompt_baselines(state_dir=tmp_path)

        assert get_prompt_baseline("reviewer", state_dir=tmp_path) is None
        assert get_prompt_baseline("implementer", state_dir=tmp_path) is None

    def test_clear_nonexistent_baselines(self, tmp_path: Path) -> None:
        """Clearing when no baselines file exists does not raise."""
        clear_prompt_baselines(state_dir=tmp_path)  # Should not raise

    def test_record_multiple_agents(self, tmp_path: Path) -> None:
        """Multiple agents can be recorded independently."""
        record_prompt_baseline("reviewer", issue_number=1, word_count=500, state_dir=tmp_path)
        record_prompt_baseline(
            "security-auditor", issue_number=1, word_count=600, state_dir=tmp_path
        )

        assert get_prompt_baseline("reviewer", state_dir=tmp_path) == 500
        assert get_prompt_baseline("security-auditor", state_dir=tmp_path) == 600

    def test_baseline_persists_to_json(self, tmp_path: Path) -> None:
        """Verify the baselines file is valid JSON with expected structure."""
        record_prompt_baseline("reviewer", issue_number=1, word_count=500, state_dir=tmp_path)

        baselines_path = tmp_path / "prompt_baselines.json"
        assert baselines_path.exists()

        data = json.loads(baselines_path.read_text())
        assert data == {"reviewer": {"1": 500}}


class TestPromptIntegrityResult:
    """Tests for the PromptIntegrityResult dataclass."""

    def test_prompt_integrity_result_fields(self) -> None:
        """Dataclass fields are accessible and correct."""
        result = PromptIntegrityResult(
            agent_type="reviewer",
            word_count=450,
            baseline_word_count=500,
            shrinkage_pct=10.0,
            passed=True,
            reason="Prompt for reviewer OK (450 words).",
            should_reload=False,
        )

        assert result.agent_type == "reviewer"
        assert result.word_count == 450
        assert result.baseline_word_count == 500
        assert result.shrinkage_pct == 10.0
        assert result.passed is True
        assert result.reason == "Prompt for reviewer OK (450 words)."
        assert result.should_reload is False
