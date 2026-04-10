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
    compute_template_baselines,
    get_agent_prompt_template,
    get_prompt_baseline,
    record_prompt_baseline,
    seed_baselines_from_templates,
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
        """Passes if word count > minimum and no baseline provided."""
        prompt = " ".join(["word"] * (MIN_CRITICAL_AGENT_PROMPT_WORDS + 10))
        result = validate_prompt_word_count("implementer", prompt)

        assert result.passed is True
        assert result.should_reload is False
        assert result.shrinkage_pct == 0.0
        assert result.baseline_word_count is None
        assert result.word_count == len(prompt.split())

    def test_validate_within_threshold(self) -> None:
        """10% shrinkage with 15% default threshold passes."""
        # 90 words = 10% shrinkage from 100-word baseline
        prompt = " ".join(["word"] * 90)
        result = validate_prompt_word_count("implementer", prompt, baseline_word_count=100)

        assert result.passed is True
        assert result.should_reload is False
        assert result.shrinkage_pct == 10.0

    def test_validate_exceeds_threshold(self) -> None:
        """25% shrinkage with 15% default threshold fails, should_reload=True."""
        # 150 words = 25% shrinkage from 200-word baseline (above minimum of 80)
        prompt = " ".join(["word"] * 150)
        result = validate_prompt_word_count("implementer", prompt, baseline_word_count=200)

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
        """Non-critical agent (e.g., 'test-helper') with 50 words passes (no minimum)."""
        prompt = " ".join(["word"] * 50)
        result = validate_prompt_word_count("test-helper", prompt)

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


class TestIssue696RegressionImplementerCompression:
    """Regression tests for Issue #696: 41% implementer prompt compression undetected.

    Bug: COMPRESSION_CRITICAL_AGENTS was missing implementer, planner, and doc-master,
    so their prompts could shrink without triggering validation. max_shrinkage default
    was 0.20 (20%), now tightened to 0.15 (15%).
    """

    def test_implementer_in_critical_agents(self) -> None:
        """Regression: implementer was missing, allowing 41% shrinkage undetected."""
        assert "implementer" in COMPRESSION_CRITICAL_AGENTS

    def test_planner_in_critical_agents(self) -> None:
        """Regression: planner was missing from critical agents."""
        assert "planner" in COMPRESSION_CRITICAL_AGENTS

    def test_doc_master_in_critical_agents(self) -> None:
        """Regression: doc-master was missing from critical agents."""
        assert "doc-master" in COMPRESSION_CRITICAL_AGENTS

    def test_default_max_shrinkage_is_015(self) -> None:
        """Regression: default was 0.20, now 0.15 to catch compression earlier."""
        import inspect

        sig = inspect.signature(validate_prompt_word_count)
        default = sig.parameters["max_shrinkage"].default
        assert default == 0.15, f"Expected default 0.15, got {default}"

    def test_implementer_below_minimum_fails(self) -> None:
        """Implementer with fewer than MIN_CRITICAL_AGENT_PROMPT_WORDS should fail."""
        short_prompt = " ".join(["word"] * (MIN_CRITICAL_AGENT_PROMPT_WORDS - 1))
        result = validate_prompt_word_count("implementer", short_prompt)
        assert result.passed is False
        assert result.should_reload is True
        assert "implementer" in result.reason

    def test_implementer_41pct_shrinkage_caught(self) -> None:
        """The exact bug scenario: 41% shrinkage from 200-word baseline is caught."""
        baseline = 200
        shrunk_prompt = " ".join(["word"] * 118)  # ~41% shrinkage
        result = validate_prompt_word_count("implementer", shrunk_prompt, baseline)
        assert result.passed is False
        assert result.should_reload is True
        assert "shrank" in result.reason

    @pytest.mark.parametrize("agent_type", ["planner", "doc-master"])
    def test_planner_docmaster_below_minimum_fails(self, agent_type: str) -> None:
        """Planner and doc-master below minimum word count should fail."""
        short_prompt = " ".join(["word"] * (MIN_CRITICAL_AGENT_PROMPT_WORDS - 1))
        result = validate_prompt_word_count(agent_type, short_prompt)
        assert result.passed is False
        assert result.should_reload is True
        assert agent_type in result.reason

    def test_pipeline_intent_validator_mirrors_critical_agents(self) -> None:
        """Both modules must have identical COMPRESSION_CRITICAL_AGENTS."""
        from pipeline_intent_validator import (
            COMPRESSION_CRITICAL_AGENTS as VALIDATOR_AGENTS,
        )

        assert COMPRESSION_CRITICAL_AGENTS == VALIDATOR_AGENTS, (
            f"Mismatch between prompt_integrity and pipeline_intent_validator.\n"
            f"prompt_integrity: {COMPRESSION_CRITICAL_AGENTS}\n"
            f"pipeline_intent_validator: {VALIDATOR_AGENTS}"
        )


class TestTemplateBaselineSeeding:
    """Tests for Issue #748: template-based baseline seeding.

    Verifies that compute_template_baselines() and seed_baselines_from_templates()
    establish word-count baselines derived from agent template files, so the first
    real issue in a batch is compared against the canonical template rather than
    the (potentially already-compressed) observed first invocation.
    """

    def _make_agents_dir(self, tmp_path: Path, agents: dict) -> Path:
        """Helper: create an agents directory with given agent content files.

        Args:
            tmp_path: Temporary directory to create agents dir within.
            agents: Mapping of {agent_type: content_string}.

        Returns:
            Path to the created agents directory.
        """
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        for agent_type, content in agents.items():
            (agents_dir / f"{agent_type}.md").write_text(content, encoding="utf-8")
        return agents_dir

    def test_compute_template_baselines_returns_word_counts(self, tmp_path: Path) -> None:
        """compute_template_baselines() returns correct word counts for existing agents."""
        content_implementer = "word " * 300  # 300 words
        content_reviewer = "token " * 250  # 250 words
        agents_dir = self._make_agents_dir(
            tmp_path,
            {"implementer": content_implementer, "reviewer": content_reviewer},
        )

        baselines = compute_template_baselines(agents_dir=agents_dir)

        assert baselines["implementer"] == 300
        assert baselines["reviewer"] == 250

    def test_compute_template_baselines_skips_missing_agents(self, tmp_path: Path) -> None:
        """compute_template_baselines() skips agents whose template files are absent."""
        # Only create implementer — other critical agents are absent
        agents_dir = self._make_agents_dir(
            tmp_path, {"implementer": "word " * 200}
        )

        baselines = compute_template_baselines(agents_dir=agents_dir)

        # Only implementer should be present; missing agents silently skipped
        assert "implementer" in baselines
        for agent in COMPRESSION_CRITICAL_AGENTS:
            if agent != "implementer":
                assert agent not in baselines

    def test_seed_baselines_from_templates_writes_to_disk(self, tmp_path: Path) -> None:
        """seed_baselines_from_templates() persists template word counts to JSON."""
        agents_dir = self._make_agents_dir(
            tmp_path,
            {"implementer": "word " * 400, "reviewer": "token " * 350},
        )
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        result = seed_baselines_from_templates(
            agents_dir=agents_dir, state_dir=state_dir
        )

        assert result["implementer"] == 400
        assert result["reviewer"] == 350
        # Verify baseline is retrievable
        assert get_prompt_baseline("implementer", state_dir=state_dir) == 400
        assert get_prompt_baseline("reviewer", state_dir=state_dir) == 350

    def test_seed_baselines_from_templates_baseline_used_by_validation(
        self, tmp_path: Path
    ) -> None:
        """After seeding, validate_prompt_word_count() uses template baseline for comparison."""
        # Template has 500 words
        agents_dir = self._make_agents_dir(tmp_path, {"implementer": "word " * 500})
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        seed_baselines_from_templates(agents_dir=agents_dir, state_dir=state_dir)
        baseline = get_prompt_baseline("implementer", state_dir=state_dir)

        # A first-issue prompt with 500 words — no shrinkage
        full_prompt = " ".join(["word"] * 500)
        result = validate_prompt_word_count("implementer", full_prompt, baseline)
        assert result.passed is True

        # A compressed first-issue prompt — 46% shrinkage from 500-word template
        compressed_prompt = " ".join(["word"] * 270)
        result_compressed = validate_prompt_word_count(
            "implementer", compressed_prompt, baseline, max_shrinkage=0.25
        )
        assert result_compressed.passed is False
        assert result_compressed.should_reload is True

    def test_template_baseline_catches_first_issue_compression(
        self, tmp_path: Path
    ) -> None:
        """Template baseline catches compression even on the first batch issue.

        Reproduces the core bug: without template seeding, the first issue's
        compressed prompt becomes the baseline, masking compression entirely.
        With template seeding, the compressed first-issue prompt is caught.
        """
        template_words = 600
        first_issue_words = 320  # ~47% shrinkage from template

        agents_dir = self._make_agents_dir(
            tmp_path, {"security-auditor": "word " * template_words}
        )
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Seed from template
        seed_baselines_from_templates(agents_dir=agents_dir, state_dir=state_dir)
        baseline = get_prompt_baseline("security-auditor", state_dir=state_dir)

        assert baseline == template_words

        # First-issue prompt is already compressed — should be caught
        compressed_first_issue = " ".join(["word"] * first_issue_words)
        result = validate_prompt_word_count(
            "security-auditor", compressed_first_issue, baseline, max_shrinkage=0.25
        )
        assert result.passed is False
        assert result.should_reload is True
        # shrinkage is roughly 47%
        assert result.shrinkage_pct > 40.0
