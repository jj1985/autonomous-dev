"""Tests for skill_change_detector library.

Tests cover:
- detect_skill_changes: path matching, deduplication, edge cases
- get_eval_status: eval prompt detection, baseline loading
- format_skill_eval_report: PASS/WARNING/BLOCK formatting
- get_weak_skills: delta/pass_rate/staleness detection
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# Ensure lib is importable
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"),
)

from skill_change_detector import (
    detect_skill_changes,
    format_skill_eval_report,
    get_eval_status,
    get_weak_skills,
)


class TestDetectSkillChanges:
    """Tests for detect_skill_changes function."""

    def test_no_skills(self):
        """Returns empty list when no skill files in paths."""
        paths = ["src/main.py", "tests/test_foo.py", "README.md"]
        assert detect_skill_changes(paths) == []

    def test_single_skill(self):
        """Detects a single skill modification."""
        paths = [
            "plugins/autonomous-dev/skills/testing-guide/SKILL.md",
            "src/main.py",
        ]
        assert detect_skill_changes(paths) == ["testing-guide"]

    def test_multiple_skills(self):
        """Detects multiple distinct skills, sorted."""
        paths = [
            "skills/python-standards/SKILL.md",
            "skills/error-handling/SKILL.md",
            "skills/testing-guide/SKILL.md",
        ]
        result = detect_skill_changes(paths)
        assert result == ["error-handling", "python-standards", "testing-guide"]

    def test_ignores_non_skill_files(self):
        """Ignores files in skills directory that are not SKILL.md."""
        paths = [
            "skills/testing-guide/README.md",
            "skills/testing-guide/examples/test.py",
            "skills/testing-guide/SKILL.md",
        ]
        assert detect_skill_changes(paths) == ["testing-guide"]

    def test_deduplicates(self):
        """Deduplicates when same skill appears multiple times."""
        paths = [
            "skills/testing-guide/SKILL.md",
            "plugins/autonomous-dev/skills/testing-guide/SKILL.md",
        ]
        assert detect_skill_changes(paths) == ["testing-guide"]

    def test_handles_various_path_formats(self):
        """Handles both relative and prefix-heavy paths."""
        paths = [
            "skills/my-skill/SKILL.md",
            "./skills/another-skill/SKILL.md",
            "/abs/path/skills/third-skill/SKILL.md",
        ]
        result = detect_skill_changes(paths)
        assert "my-skill" in result
        assert "another-skill" in result
        assert "third-skill" in result

    def test_empty_input(self):
        """Returns empty list for empty input."""
        assert detect_skill_changes([]) == []

    def test_empty_strings(self):
        """Handles empty strings in the list."""
        assert detect_skill_changes(["", ""]) == []


class TestGetEvalStatus:
    """Tests for get_eval_status function."""

    def test_with_eval_prompts(self, tmp_path):
        """Skill with eval prompts is evaluable."""
        eval_dir = tmp_path / "tests" / "genai" / "skills" / "eval_prompts"
        eval_dir.mkdir(parents=True)
        (eval_dir / "testing-guide.json").write_text('{"prompts": []}')

        result = get_eval_status("testing-guide", repo_root=tmp_path)
        assert result["skill_name"] == "testing-guide"
        assert result["has_eval_prompts"] is True
        assert result["evaluable"] is True
        assert result["baseline"] is None

    def test_without_eval_prompts(self, tmp_path):
        """Skill without eval prompts is not evaluable."""
        result = get_eval_status("nonexistent-skill", repo_root=tmp_path)
        assert result["has_eval_prompts"] is False
        assert result["evaluable"] is False
        assert result["baseline"] is None

    def test_with_baseline(self, tmp_path):
        """Skill with baseline data returns baseline dict."""
        eval_dir = tmp_path / "tests" / "genai" / "skills" / "eval_prompts"
        eval_dir.mkdir(parents=True)
        (eval_dir / "my-skill.json").write_text("[]")

        baselines_dir = tmp_path / "tests" / "genai" / "skills" / "baselines"
        baselines_dir.mkdir(parents=True)
        (baselines_dir / "effectiveness.json").write_text(json.dumps({
            "my-skill": {
                "pass_rate_with": 0.85,
                "delta": 0.12,
                "recorded": "2026-03-15T10:00:00Z",
            }
        }))

        result = get_eval_status("my-skill", repo_root=tmp_path)
        assert result["baseline"] is not None
        assert result["baseline"]["pass_rate_with"] == 0.85
        assert result["baseline"]["delta"] == 0.12

    def test_without_baseline_entry(self, tmp_path):
        """Skill not in baselines file returns None baseline."""
        baselines_dir = tmp_path / "tests" / "genai" / "skills" / "baselines"
        baselines_dir.mkdir(parents=True)
        (baselines_dir / "effectiveness.json").write_text(json.dumps({
            "other-skill": {"pass_rate_with": 0.90, "delta": 0.15, "recorded": "2026-01-01"},
        }))

        result = get_eval_status("missing-skill", repo_root=tmp_path)
        assert result["baseline"] is None

    def test_missing_baselines_file(self, tmp_path):
        """Missing baselines file returns None baseline gracefully."""
        result = get_eval_status("any-skill", repo_root=tmp_path)
        assert result["baseline"] is None

    def test_corrupt_baselines_file(self, tmp_path):
        """Corrupt baselines file returns None baseline gracefully."""
        baselines_dir = tmp_path / "tests" / "genai" / "skills" / "baselines"
        baselines_dir.mkdir(parents=True)
        (baselines_dir / "effectiveness.json").write_text("not valid json{{{")

        result = get_eval_status("my-skill", repo_root=tmp_path)
        assert result["baseline"] is None


class TestFormatSkillEvalReport:
    """Tests for format_skill_eval_report function."""

    def test_empty_results(self):
        """Returns simple message for no changes."""
        assert format_skill_eval_report([]) == "No skill changes detected."

    def test_pass_result(self):
        """Formats passing skill correctly."""
        results = [{
            "skill_name": "testing-guide",
            "has_eval_prompts": True,
            "baseline": {"pass_rate_with": 0.90, "delta": 0.15, "recorded": "2026-01-01"},
            "evaluable": True,
        }]
        report = format_skill_eval_report(results)
        assert "PASS" in report
        assert "testing-guide" in report
        assert "VERDICT: PASS" in report

    def test_warn_no_eval_prompts(self):
        """Formats warning for skill without eval prompts."""
        results = [{
            "skill_name": "new-skill",
            "has_eval_prompts": False,
            "baseline": None,
            "evaluable": False,
        }]
        report = format_skill_eval_report(results)
        assert "WARNING" in report
        assert "new-skill" in report
        assert "no eval prompts" in report

    def test_block_delta_regression(self):
        """Formats BLOCK for delta regression below -0.10."""
        results = [{
            "skill_name": "broken-skill",
            "has_eval_prompts": True,
            "baseline": {"pass_rate_with": 0.60, "delta": -0.15, "recorded": "2026-01-01"},
            "evaluable": True,
        }]
        report = format_skill_eval_report(results)
        assert "BLOCK" in report
        assert "VERDICT: BLOCKED" in report

    def test_pass_no_baseline(self):
        """Skill with eval prompts but no baseline passes."""
        results = [{
            "skill_name": "fresh-skill",
            "has_eval_prompts": True,
            "baseline": None,
            "evaluable": True,
        }]
        report = format_skill_eval_report(results)
        assert "PASS" in report
        assert "no baseline" in report.lower()

    def test_mixed_results(self):
        """Mixed results: one pass, one warning, one block."""
        results = [
            {
                "skill_name": "good-skill",
                "has_eval_prompts": True,
                "baseline": {"pass_rate_with": 0.95, "delta": 0.20, "recorded": "2026-01-01"},
                "evaluable": True,
            },
            {
                "skill_name": "new-skill",
                "has_eval_prompts": False,
                "baseline": None,
                "evaluable": False,
            },
            {
                "skill_name": "bad-skill",
                "has_eval_prompts": True,
                "baseline": {"pass_rate_with": 0.50, "delta": -0.20, "recorded": "2026-01-01"},
                "evaluable": True,
            },
        ]
        report = format_skill_eval_report(results)
        assert "VERDICT: BLOCKED" in report
        assert "good-skill" in report
        assert "new-skill" in report
        assert "bad-skill" in report


class TestGetWeakSkills:
    """Tests for get_weak_skills function."""

    def test_missing_file(self, tmp_path):
        """Returns empty list when baselines file doesn't exist."""
        result = get_weak_skills(tmp_path / "nonexistent.json")
        assert result == []

    def test_weak_delta(self, tmp_path):
        """Identifies skills with weak delta."""
        baselines = tmp_path / "effectiveness.json"
        baselines.write_text(json.dumps({
            "weak-skill": {
                "pass_rate_with": 0.90,
                "delta": 0.05,
                "recorded": datetime.now(timezone.utc).isoformat(),
            }
        }))
        result = get_weak_skills(baselines)
        assert len(result) == 1
        assert "weak delta" in result[0]["reason"]

    def test_low_pass_rate(self, tmp_path):
        """Identifies skills with low pass rate."""
        baselines = tmp_path / "effectiveness.json"
        baselines.write_text(json.dumps({
            "low-skill": {
                "pass_rate_with": 0.70,
                "delta": 0.15,
                "recorded": datetime.now(timezone.utc).isoformat(),
            }
        }))
        result = get_weak_skills(baselines)
        assert len(result) == 1
        assert "low pass rate" in result[0]["reason"]

    def test_stale_baseline(self, tmp_path):
        """Identifies skills with stale baselines."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        baselines = tmp_path / "effectiveness.json"
        baselines.write_text(json.dumps({
            "stale-skill": {
                "pass_rate_with": 0.95,
                "delta": 0.20,
                "recorded": old_date,
            }
        }))
        result = get_weak_skills(baselines)
        assert len(result) == 1
        assert "stale baseline" in result[0]["reason"]

    def test_healthy_skill_excluded(self, tmp_path):
        """Healthy skills are not included in results."""
        baselines = tmp_path / "effectiveness.json"
        baselines.write_text(json.dumps({
            "good-skill": {
                "pass_rate_with": 0.95,
                "delta": 0.20,
                "recorded": datetime.now(timezone.utc).isoformat(),
            }
        }))
        result = get_weak_skills(baselines)
        assert result == []

    def test_sorted_by_delta(self, tmp_path):
        """Results are sorted by delta ascending (worst first)."""
        baselines = tmp_path / "effectiveness.json"
        baselines.write_text(json.dumps({
            "bad-skill": {
                "pass_rate_with": 0.50,
                "delta": -0.10,
                "recorded": datetime.now(timezone.utc).isoformat(),
            },
            "ok-skill": {
                "pass_rate_with": 0.75,
                "delta": 0.05,
                "recorded": datetime.now(timezone.utc).isoformat(),
            },
        }))
        result = get_weak_skills(baselines)
        assert len(result) == 2
        assert result[0]["skill_name"] == "bad-skill"
        assert result[1]["skill_name"] == "ok-skill"
