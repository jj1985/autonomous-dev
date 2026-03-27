"""Unit tests for reviewer_benchmark library.

Tests dataset loading, prompt construction, verdict parsing, scoring,
and benchmark store persistence. All tests use mocked data (no API calls).

GitHub Issue: #567
"""

import json
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
