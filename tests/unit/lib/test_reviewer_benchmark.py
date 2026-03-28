"""Unit tests for reviewer_benchmark library.

Tests dataset loading, prompt construction, verdict parsing, scoring,
and benchmark store persistence. All tests use mocked data (no API calls).

GitHub Issue: #567
"""

import json
import os
import pytest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import sys

# Add lib to path
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"),
)

from reviewer_benchmark import (
    BenchmarkResult,
    BenchmarkSample,
    ScoringReport,
    build_reviewer_prompt,
    load_dataset,
    parse_verdict,
    score_results,
    store_benchmark_run,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_sample(**overrides: Any) -> Dict[str, Any]:
    """Create a minimal valid sample dict."""
    base = {
        "sample_id": "test-001",
        "source_repo": "test-repo",
        "issue_ref": "#1",
        "diff_text": "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new",
        "expected_verdict": "BLOCKING",
        "expected_categories": ["test-cat"],
        "category_tags": ["tag1"],
        "description": "Test sample",
    }
    base.update(overrides)
    return base


def _write_dataset(tmp_path: Path, samples: List[Dict], meta: Dict = None) -> Path:
    """Write a dataset JSON file and return its path."""
    dataset = {
        "_meta": meta or {"version": "1.0", "created": "2026-01-01", "samples": len(samples)},
        "samples": samples,
    }
    p = tmp_path / "dataset.json"
    p.write_text(json.dumps(dataset))
    return p


def _make_result(
    sample_id: str = "s1",
    predicted: str = "BLOCKING",
    expected: str = "BLOCKING",
    trial: int = 0,
) -> BenchmarkResult:
    return BenchmarkResult(
        sample_id=sample_id,
        predicted_verdict=predicted,
        expected_verdict=expected,
        findings=[],
        raw_response="",
        trial_index=trial,
    )


# ---------------------------------------------------------------------------
# Dataset Loading
# ---------------------------------------------------------------------------

class TestLoadDataset:
    def test_load_dataset_valid(self, tmp_path: Path) -> None:
        samples = [_make_sample(), _make_sample(sample_id="test-002", expected_verdict="APPROVE")]
        p = _write_dataset(tmp_path, samples)
        result = load_dataset(p)
        assert len(result) == 2
        assert result[0].sample_id == "test-001"
        assert result[1].expected_verdict == "APPROVE"

    def test_load_dataset_missing_field(self, tmp_path: Path) -> None:
        bad = _make_sample()
        del bad["diff_text"]
        p = _write_dataset(tmp_path, [bad])
        with pytest.raises(ValueError, match="missing required fields"):
            load_dataset(p)

    def test_load_dataset_invalid_verdict(self, tmp_path: Path) -> None:
        bad = _make_sample(expected_verdict="INVALID")
        p = _write_dataset(tmp_path, [bad])
        with pytest.raises(ValueError, match="invalid verdict"):
            load_dataset(p)

    def test_load_dataset_empty(self, tmp_path: Path) -> None:
        p = _write_dataset(tmp_path, [])
        with pytest.raises(ValueError, match="empty"):
            load_dataset(p)

    def test_load_dataset_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_dataset(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------

class TestBuildReviewerPrompt:
    def test_build_reviewer_prompt_contains_diff(self) -> None:
        sample = BenchmarkSample(**_make_sample())
        prompt = build_reviewer_prompt(sample, "Review carefully.")
        assert sample.diff_text in prompt

    def test_build_reviewer_prompt_contains_instructions(self) -> None:
        sample = BenchmarkSample(**_make_sample())
        instructions = "You are a code reviewer. Be thorough."
        prompt = build_reviewer_prompt(sample, instructions)
        assert instructions in prompt
        assert sample.source_repo in prompt
        assert sample.issue_ref in prompt


# ---------------------------------------------------------------------------
# Verdict Parsing
# ---------------------------------------------------------------------------

class TestParseVerdict:
    def test_parse_verdict_approve(self) -> None:
        response = "Looks good.\n\n## Verdict: APPROVE\n\nNo issues found."
        verdict, findings = parse_verdict(response)
        assert verdict == "APPROVE"

    def test_parse_verdict_request_changes(self) -> None:
        response = "Some issues.\n\n## Verdict: REQUEST_CHANGES\n\n- Fix the null check (this is important for safety)\n- Update the tests accordingly please"
        verdict, findings = parse_verdict(response)
        assert verdict == "REQUEST_CHANGES"
        assert len(findings) >= 1

    def test_parse_verdict_blocking_findings(self) -> None:
        response = (
            "Critical bug found.\n\n"
            "- The function returns hardcoded 0.85 instead of computing the actual score\n"
            "- This affects all fallthrough paths in the scorer\n\n"
            "## Verdict: BLOCKING"
        )
        verdict, findings = parse_verdict(response)
        assert verdict == "BLOCKING"
        assert len(findings) >= 2

    def test_parse_verdict_malformed(self) -> None:
        response = "This response has no verdict at all, just some random text about code."
        verdict, findings = parse_verdict(response)
        assert verdict == "PARSE_ERROR"
        assert findings == []

    def test_parse_verdict_no_verdict_line(self) -> None:
        verdict, findings = parse_verdict("")
        assert verdict == "PARSE_ERROR"
        assert findings == []

    def test_parse_verdict_fallback_bare_keyword(self) -> None:
        # Verdict keyword in last 200 chars but no heading
        padding = "x" * 300
        response = padding + "Overall this is fine. APPROVE"
        verdict, findings = parse_verdict(response)
        assert verdict == "APPROVE"

    def test_parse_verdict_case_insensitive_heading(self) -> None:
        response = "## verdict: Approve\nAll good."
        verdict, findings = parse_verdict(response)
        assert verdict == "APPROVE"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestScoreResults:
    def test_score_results_perfect(self) -> None:
        """All predictions correct -> balanced accuracy = 1.0"""
        results = [
            _make_result("s1", "BLOCKING", "BLOCKING"),
            _make_result("s2", "REQUEST_CHANGES", "REQUEST_CHANGES"),
            _make_result("s3", "APPROVE", "APPROVE"),
        ]
        report = score_results(results)
        assert report.balanced_accuracy == 1.0
        assert report.false_positive_rate == 0.0
        assert report.false_negative_rate == 0.0
        assert report.confusion_matrix["TP"] == 2
        assert report.confusion_matrix["TN"] == 1

    def test_score_results_all_wrong(self) -> None:
        """All predictions wrong -> balanced accuracy = 0.0"""
        results = [
            _make_result("s1", "APPROVE", "BLOCKING"),       # FN
            _make_result("s2", "APPROVE", "REQUEST_CHANGES"), # FN
            _make_result("s3", "BLOCKING", "APPROVE"),        # FP
        ]
        report = score_results(results)
        assert report.balanced_accuracy == 0.0
        assert report.false_positive_rate == 1.0
        assert report.false_negative_rate == 1.0

    def test_score_results_false_positives(self) -> None:
        """Clean samples flagged as defective."""
        results = [
            _make_result("s1", "BLOCKING", "APPROVE"),  # FP
            _make_result("s2", "BLOCKING", "APPROVE"),  # FP
            _make_result("s3", "BLOCKING", "BLOCKING"), # TP
        ]
        report = score_results(results)
        assert report.false_positive_rate == 1.0  # 2 FP / (2 FP + 0 TN)
        assert report.confusion_matrix["FP"] == 2
        assert report.confusion_matrix["TP"] == 1

    def test_score_results_false_negatives(self) -> None:
        """Defective samples missed."""
        results = [
            _make_result("s1", "APPROVE", "BLOCKING"),        # FN
            _make_result("s2", "APPROVE", "REQUEST_CHANGES"), # FN
            _make_result("s3", "APPROVE", "APPROVE"),         # TN
        ]
        report = score_results(results)
        assert report.false_negative_rate == 1.0  # 2 FN / (2 FN + 0 TP)
        assert report.confusion_matrix["FN"] == 2
        assert report.confusion_matrix["TN"] == 1

    def test_score_results_per_category(self) -> None:
        results = [
            _make_result("s1", "BLOCKING", "BLOCKING"),       # correct
            _make_result("s2", "APPROVE", "REQUEST_CHANGES"), # wrong
            _make_result("s3", "APPROVE", "APPROVE"),         # correct
        ]
        report = score_results(results)
        assert "BLOCKING" in report.per_category
        assert report.per_category["BLOCKING"]["accuracy"] == 1.0
        assert "APPROVE" in report.per_category
        assert report.per_category["APPROVE"]["accuracy"] == 1.0
        # REQUEST_CHANGES predicted as APPROVE (negative) but expected positive
        assert report.per_category["REQUEST_CHANGES"]["accuracy"] == 0.0

    def test_score_results_consistency(self) -> None:
        """Consistency = fraction matching majority per sample, averaged."""
        results = [
            # Sample s1: 3 BLOCKING, 2 APPROVE -> majority BLOCKING, consistency 3/5 = 0.6
            _make_result("s1", "BLOCKING", "BLOCKING", 0),
            _make_result("s1", "BLOCKING", "BLOCKING", 1),
            _make_result("s1", "BLOCKING", "BLOCKING", 2),
            _make_result("s1", "APPROVE", "BLOCKING", 3),
            _make_result("s1", "APPROVE", "BLOCKING", 4),
            # Sample s2: 5 APPROVE -> consistency 5/5 = 1.0
            _make_result("s2", "APPROVE", "APPROVE", 0),
            _make_result("s2", "APPROVE", "APPROVE", 1),
            _make_result("s2", "APPROVE", "APPROVE", 2),
            _make_result("s2", "APPROVE", "APPROVE", 3),
            _make_result("s2", "APPROVE", "APPROVE", 4),
        ]
        report = score_results(results)
        # Average: (0.6 + 1.0) / 2 = 0.8
        assert abs(report.consistency_rate - 0.8) < 1e-9

    def test_score_results_with_parse_errors(self) -> None:
        """PARSE_ERROR results excluded from accuracy but counted in consistency."""
        results = [
            _make_result("s1", "BLOCKING", "BLOCKING"),
            _make_result("s2", "PARSE_ERROR", "APPROVE"),
            _make_result("s3", "APPROVE", "APPROVE"),
        ]
        report = score_results(results)
        # Only 2 non-PARSE_ERROR results: 1 TP + 1 TN
        assert report.confusion_matrix["TP"] == 1
        assert report.confusion_matrix["TN"] == 1
        assert report.balanced_accuracy == 1.0
        assert report.total_samples == 3

    def test_score_results_empty(self) -> None:
        report = score_results([])
        assert report.balanced_accuracy == 0.0
        assert report.total_samples == 0

    def test_confusion_matrix_structure(self) -> None:
        results = [_make_result("s1", "BLOCKING", "BLOCKING")]
        report = score_results(results)
        assert set(report.confusion_matrix.keys()) == {"TP", "TN", "FP", "FN"}
        for v in report.confusion_matrix.values():
            assert isinstance(v, int)


# ---------------------------------------------------------------------------
# Store Integration
# ---------------------------------------------------------------------------

class TestLoadDatasetOptionalFields:
    """Test backward compatibility for optional fields in BenchmarkSample."""

    def test_samples_without_new_fields_get_defaults(self, tmp_path: Path) -> None:
        """Old-format samples (no difficulty/commit_sha/defect_category) get defaults."""
        samples = [_make_sample()]
        p = _write_dataset(tmp_path, samples)
        result = load_dataset(p)
        assert len(result) == 1
        assert result[0].difficulty == "medium"
        assert result[0].commit_sha == ""
        assert result[0].defect_category == ""

    def test_samples_with_new_fields_populated(self, tmp_path: Path) -> None:
        """Samples with new fields have them correctly loaded."""
        sample = _make_sample(
            difficulty="hard",
            commit_sha="abc123",
            defect_category="null-safety",
        )
        p = _write_dataset(tmp_path, [sample])
        result = load_dataset(p)
        assert result[0].difficulty == "hard"
        assert result[0].commit_sha == "abc123"
        assert result[0].defect_category == "null-safety"

    def test_mixed_old_and_new_format_samples(self, tmp_path: Path) -> None:
        """Dataset with both old-format and new-format samples loads correctly."""
        old_sample = _make_sample(sample_id="old-001")
        new_sample = _make_sample(
            sample_id="new-001",
            difficulty="easy",
            commit_sha="def456",
            defect_category="hardcoded-value",
        )
        p = _write_dataset(tmp_path, [old_sample, new_sample])
        result = load_dataset(p)
        assert len(result) == 2
        assert result[0].difficulty == "medium"  # default
        assert result[1].difficulty == "easy"  # explicit


class TestPerDifficulty:
    """Test score_results with per-difficulty breakdown."""

    def test_per_difficulty_with_samples(self) -> None:
        samples = [
            BenchmarkSample(**_make_sample(sample_id="s1", difficulty="easy")),
            BenchmarkSample(**_make_sample(
                sample_id="s2", expected_verdict="APPROVE", difficulty="hard"
            )),
        ]
        results = [
            _make_result("s1", "BLOCKING", "BLOCKING"),
            _make_result("s2", "APPROVE", "APPROVE"),
        ]
        report = score_results(results, samples=samples)
        assert "easy" in report.per_difficulty
        assert "hard" in report.per_difficulty
        assert report.per_difficulty["easy"]["accuracy"] == 1.0
        assert report.per_difficulty["hard"]["accuracy"] == 1.0

    def test_per_difficulty_without_samples(self) -> None:
        results = [_make_result("s1", "BLOCKING", "BLOCKING")]
        report = score_results(results)
        assert report.per_difficulty == {}

    def test_per_difficulty_counts(self) -> None:
        samples = [
            BenchmarkSample(**_make_sample(sample_id="s1", difficulty="medium")),
            BenchmarkSample(**_make_sample(sample_id="s2", difficulty="medium")),
        ]
        results = [
            _make_result("s1", "BLOCKING", "BLOCKING"),
            _make_result("s2", "APPROVE", "BLOCKING"),  # wrong
        ]
        report = score_results(results, samples=samples)
        assert report.per_difficulty["medium"]["total"] == 2
        assert report.per_difficulty["medium"]["correct"] == 1
        assert report.per_difficulty["medium"]["accuracy"] == 0.5


class TestPerDefectCategory:
    """Test score_results with per-defect-category breakdown."""

    def test_per_defect_category_with_samples(self) -> None:
        samples = [
            BenchmarkSample(**_make_sample(
                sample_id="s1", defect_category="null-safety"
            )),
            BenchmarkSample(**_make_sample(
                sample_id="s2", defect_category="hardcoded-value"
            )),
        ]
        results = [
            _make_result("s1", "BLOCKING", "BLOCKING"),
            _make_result("s2", "BLOCKING", "BLOCKING"),
        ]
        report = score_results(results, samples=samples)
        assert "null-safety" in report.per_defect_category
        assert "hardcoded-value" in report.per_defect_category

    def test_per_defect_category_without_samples(self) -> None:
        results = [_make_result("s1", "BLOCKING", "BLOCKING")]
        report = score_results(results)
        assert report.per_defect_category == {}

    def test_per_defect_category_skips_empty_category(self) -> None:
        samples = [
            BenchmarkSample(**_make_sample(sample_id="s1", defect_category="")),
        ]
        results = [_make_result("s1", "BLOCKING", "BLOCKING")]
        report = score_results(results, samples=samples)
        assert report.per_defect_category == {}

    def test_per_defect_category_accuracy(self) -> None:
        samples = [
            BenchmarkSample(**_make_sample(
                sample_id="s1", defect_category="null-safety"
            )),
            BenchmarkSample(**_make_sample(
                sample_id="s2", defect_category="null-safety"
            )),
        ]
        results = [
            _make_result("s1", "BLOCKING", "BLOCKING"),   # correct
            _make_result("s2", "APPROVE", "BLOCKING"),     # wrong
        ]
        report = score_results(results, samples=samples)
        assert report.per_defect_category["null-safety"]["accuracy"] == 0.5
        assert report.per_defect_category["null-safety"]["total"] == 2


class TestStoreBenchmarkRun:
    def test_store_benchmark_run(self) -> None:
        mock_store = MagicMock()
        report = ScoringReport(
            balanced_accuracy=0.85,
            false_positive_rate=0.1,
            false_negative_rate=0.15,
            per_category={"BLOCKING": {"accuracy": 0.9, "total": 10, "correct": 9}},
            confusion_matrix={"TP": 8, "TN": 4, "FP": 1, "FN": 1},
            total_samples=14,
            trials_per_sample=5,
            consistency_rate=0.92,
        )
        store_benchmark_run(mock_store, report)

        mock_store.update_baseline.assert_called_once()
        call_args = mock_store.update_baseline.call_args
        assert call_args[0][0] == "reviewer-effectiveness"
        assert call_args[1]["score"] == 0.85
        assert "confusion_matrix" in call_args[1]["metadata"]
        mock_store.save.assert_called_once()


# ---------------------------------------------------------------------------
# Regression tests for Issue #574: --validate-dataset must not require API key
# ---------------------------------------------------------------------------

class TestLoadDatasetInvalidJson:
    """Test that invalid JSON in dataset files raises ValueError with path context."""

    def test_load_dataset_invalid_json(self, tmp_path: Path) -> None:
        """Invalid JSON file -> ValueError with path in message (Bug 1 regression)."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{not valid json: }")
        with pytest.raises(ValueError, match=str(bad_json)):
            load_dataset(bad_json)

    def test_load_dataset_invalid_json_message_contains_error(self, tmp_path: Path) -> None:
        """ValueError message includes original JSON parse error context."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("definitely not json")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_dataset(bad_json)


class TestParseBareVerdictCaseInsensitive:
    """Test that bare verdict keyword matching is case-insensitive (Bug 3 regression)."""

    def test_parse_verdict_bare_keyword_lowercase(self) -> None:
        """Bare lowercase 'approve' in tail -> parsed as 'APPROVE'."""
        padding = "x" * 300
        response = padding + "Overall this looks fine. approve"
        verdict, _ = parse_verdict(response)
        assert verdict == "APPROVE"

    def test_parse_verdict_bare_keyword_mixed_case(self) -> None:
        """Bare mixed-case 'Blocking' in tail -> parsed as 'BLOCKING'."""
        padding = "x" * 300
        response = padding + "My verdict: Blocking"
        verdict, _ = parse_verdict(response)
        assert verdict == "BLOCKING"

    def test_parse_verdict_bare_keyword_request_changes_lowercase(self) -> None:
        """Bare lowercase 'request_changes' in tail -> parsed as 'REQUEST_CHANGES'."""
        padding = "x" * 300
        response = padding + " request_changes"
        verdict, _ = parse_verdict(response)
        assert verdict == "REQUEST_CHANGES"


class TestPerCategoryWithCategoryTags:
    """Test that per_category groups by category_tags when samples are provided (Bug 4 regression)."""

    def test_per_category_with_category_tags(self) -> None:
        """When samples are provided, per_category groups by category_tags not expected_verdict."""
        samples = [
            BenchmarkSample(**_make_sample(
                sample_id="s1",
                expected_verdict="BLOCKING",
                category_tags=["null-safety"],
            )),
            BenchmarkSample(**_make_sample(
                sample_id="s2",
                expected_verdict="APPROVE",
                category_tags=["style"],
            )),
        ]
        results = [
            _make_result("s1", "BLOCKING", "BLOCKING"),
            _make_result("s2", "APPROVE", "APPROVE"),
        ]
        report = score_results(results, samples=samples)
        # Should group by category_tags, not expected_verdict
        assert "null-safety" in report.per_category
        assert "style" in report.per_category
        # expected_verdict keys should NOT appear when samples with tags are provided
        assert "BLOCKING" not in report.per_category
        assert "APPROVE" not in report.per_category

    def test_per_category_multi_tag_sample(self) -> None:
        """A sample with multiple category_tags contributes to each tag bucket."""
        samples = [
            BenchmarkSample(**_make_sample(
                sample_id="s1",
                expected_verdict="BLOCKING",
                category_tags=["null-safety", "hardcoded-value"],
            )),
        ]
        results = [_make_result("s1", "BLOCKING", "BLOCKING")]
        report = score_results(results, samples=samples)
        assert "null-safety" in report.per_category
        assert "hardcoded-value" in report.per_category
        assert report.per_category["null-safety"]["accuracy"] == 1.0
        assert report.per_category["hardcoded-value"]["accuracy"] == 1.0

    def test_per_category_without_samples_falls_back_to_expected_verdict(self) -> None:
        """Without samples, per_category falls back to expected_verdict grouping."""
        results = [
            _make_result("s1", "BLOCKING", "BLOCKING"),
            _make_result("s2", "APPROVE", "APPROVE"),
        ]
        report = score_results(results)
        assert "BLOCKING" in report.per_category
        assert "APPROVE" in report.per_category


class TestValidateDatasetWithoutApiKey:
    """Regression tests: --validate-dataset should not require ANTHROPIC_API_KEY.

    Bug: API key check ran before --validate-dataset early return, so running
    `--validate-dataset` without a key caused SystemExit(1).

    Fix: Load dataset and handle --validate-dataset early return BEFORE
    checking for the API key.

    GitHub Issue: #574
    """

    def test_validate_dataset_without_api_key(self, tmp_path: Path) -> None:
        """--validate-dataset succeeds even when ANTHROPIC_API_KEY is absent.

        Regression: before the fix, this would exit with code 1 because the
        API key check ran before the --validate-dataset early return.
        """
        # Write a minimal valid dataset
        samples = [_make_sample()]
        dataset_path = _write_dataset(tmp_path, samples)

        script = (
            Path(__file__).resolve().parents[3] / "scripts" / "run_reviewer_benchmark.py"
        )

        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)  # Ensure key is absent

        import subprocess
        result = subprocess.run(
            [sys.executable, str(script), "--dataset", str(dataset_path), "--validate-dataset"],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"--validate-dataset failed without API key (exit {result.returncode}).\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_benchmark_without_api_key_fails(self, tmp_path: Path) -> None:
        """Normal benchmark run (no --validate-dataset) requires ANTHROPIC_API_KEY.

        Ensures the API key guard is still enforced when running a full benchmark.
        """
        samples = [_make_sample()]
        dataset_path = _write_dataset(tmp_path, samples)

        script = (
            Path(__file__).resolve().parents[3] / "scripts" / "run_reviewer_benchmark.py"
        )

        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)  # Ensure key is absent

        import subprocess
        result = subprocess.run(
            [sys.executable, str(script), "--dataset", str(dataset_path)],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, (
            f"Expected exit code 1 when API key is missing, got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "ANTHROPIC_API_KEY" in result.stderr
