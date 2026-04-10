"""Regression test: Issue #731 — progressive prompt compression prevention.

The planner prompt shrank 44% and implementer shrank 58% across batch sessions.
The fix ships as:
  - prompt_integrity.py  (real-time prevention library)
  - HARD GATE in implement-batch.md (coordinator enforcement gate)
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_BATCH = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"


class TestPromptCompressionPrevention:
    def setup_method(self):
        self.content = IMPLEMENT_BATCH.read_text()

    def test_prompt_integrity_hard_gate_exists(self):
        """implement-batch.md must have Prompt Integrity Across Issues gate."""
        assert "Prompt Integrity Across Issues" in self.content

    def test_shrinkage_threshold_defined(self):
        """Must define a shrinkage threshold percentage."""
        assert re.search(r"\d+%.*shrink|shrink.*\d+%", self.content, re.IGNORECASE)

    def test_prompt_integrity_library_referenced(self):
        """Must reference prompt_integrity.py library."""
        assert "prompt_integrity" in self.content


class TestPromptIntegrityLibrary:
    """Verify the prompt_integrity.py library has required functions."""

    def setup_method(self):
        import sys

        lib_path = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))
        import prompt_integrity as pi

        self.pi = pi

    def test_validate_prompt_word_count_exists(self):
        """validate_prompt_word_count must be importable from prompt_integrity."""
        assert callable(self.pi.validate_prompt_word_count)

    def test_record_prompt_baseline_exists(self):
        """record_prompt_baseline must be importable from prompt_integrity."""
        assert callable(self.pi.record_prompt_baseline)

    def test_get_prompt_baseline_exists(self):
        """get_prompt_baseline must be importable from prompt_integrity."""
        assert callable(self.pi.get_prompt_baseline)

    def test_validate_detects_44_percent_planner_shrinkage(self):
        """Validates the exact regression: planner shrank 44% (above 15% threshold)."""
        baseline_words = 1000
        shrunken_words = int(baseline_words * (1 - 0.44))  # 44% shrinkage
        shrunken_prompt = " ".join(["word"] * shrunken_words)

        result = self.pi.validate_prompt_word_count(
            "planner", shrunken_prompt, baseline_words
        )

        assert not result.passed, (
            "44% planner shrinkage should fail validation (threshold is 15%)"
        )
        assert result.should_reload, "should_reload must be True when shrinkage exceeds threshold"
        assert result.shrinkage_pct > 15.0

    def test_validate_detects_58_percent_implementer_shrinkage(self):
        """Validates the exact regression: implementer shrank 58% (above 15% threshold)."""
        baseline_words = 1000
        shrunken_words = int(baseline_words * (1 - 0.58))  # 58% shrinkage
        shrunken_prompt = " ".join(["word"] * shrunken_words)

        result = self.pi.validate_prompt_word_count(
            "implementer", shrunken_prompt, baseline_words
        )

        assert not result.passed, (
            "58% implementer shrinkage should fail validation (threshold is 15%)"
        )
        assert result.should_reload, "should_reload must be True when shrinkage exceeds threshold"
        assert result.shrinkage_pct > 15.0

    def test_validate_passes_for_acceptable_shrinkage(self):
        """Small shrinkage (under 15%) must pass validation."""
        baseline_words = 1000
        prompt = " ".join(["word"] * 900)  # 10% shrinkage — under threshold

        result = self.pi.validate_prompt_word_count("planner", prompt, baseline_words)

        assert result.passed, "10% shrinkage is within acceptable threshold"
        assert not result.should_reload

    def test_validate_passes_with_no_baseline(self):
        """First issue in batch has no baseline — must always pass."""
        prompt = " ".join(["word"] * 500)

        result = self.pi.validate_prompt_word_count("planner", prompt, None)

        assert result.passed
        assert result.baseline_word_count is None

    def test_planner_and_implementer_are_critical_agents(self):
        """planner and implementer must be in COMPRESSION_CRITICAL_AGENTS set."""
        assert "planner" in self.pi.COMPRESSION_CRITICAL_AGENTS
        assert "implementer" in self.pi.COMPRESSION_CRITICAL_AGENTS

    def test_baseline_roundtrip(self, tmp_path):
        """record_prompt_baseline and get_prompt_baseline must round-trip correctly."""
        self.pi.record_prompt_baseline("planner", 1, 1200, state_dir=tmp_path)
        result = self.pi.get_prompt_baseline("planner", state_dir=tmp_path)

        assert result == 1200

    def test_baseline_returns_first_issue_not_last(self, tmp_path):
        """get_prompt_baseline must return first issue's count, not the latest."""
        self.pi.record_prompt_baseline("implementer", 5, 1200, state_dir=tmp_path)
        self.pi.record_prompt_baseline("implementer", 1, 1000, state_dir=tmp_path)
        self.pi.record_prompt_baseline("implementer", 3, 800, state_dir=tmp_path)

        result = self.pi.get_prompt_baseline("implementer", state_dir=tmp_path)

        assert result == 1000, "Baseline should be issue #1 (lowest number), not issue #3 or #5"

    def test_clear_prompt_baselines_resets_state(self, tmp_path):
        """clear_prompt_baselines must remove all recorded baselines."""
        self.pi.record_prompt_baseline("planner", 1, 1200, state_dir=tmp_path)
        self.pi.clear_prompt_baselines(state_dir=tmp_path)

        result = self.pi.get_prompt_baseline("planner", state_dir=tmp_path)

        assert result is None, "After clearing, get_prompt_baseline must return None"
